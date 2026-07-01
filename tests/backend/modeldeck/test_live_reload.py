"""Tests for live config reload: ConfigWatcher, apply_reload, and run_loop wiring."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml

from modeldeck.service.reload import ConfigWatcher, _active_keys

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_config(path: Path, providers: dict) -> None:
    data = {
        "mqtt": {"host": "localhost", "port": 1883, "username": "", "tls": False,
                 "client_id": "md", "topic_prefix": "modeldeck",
                 "discovery_prefix": "homeassistant"},
        "service": {"poll_interval_seconds": 300, "retain_state": True,
                    "log_level": "INFO", "persist_refreshed_tokens": True},
        "providers": {"mock": {"enabled": False}, **providers},
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


# ---------------------------------------------------------------------------
# ConfigWatcher
# ---------------------------------------------------------------------------

class TestConfigWatcher:
    def test_changed_false_initially(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        sec = tmp_path / "secrets.yaml"
        cfg.write_text("x: 1", encoding="utf-8")
        sec.write_text("y: 2", encoding="utf-8")
        w = ConfigWatcher(cfg, sec)
        assert w.changed() is False

    def test_changed_true_after_modification(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        sec = tmp_path / "secrets.yaml"
        cfg.write_text("x: 1", encoding="utf-8")
        sec.write_text("y: 2", encoding="utf-8")
        w = ConfigWatcher(cfg, sec)
        time.sleep(0.01)
        cfg.write_text("x: 2", encoding="utf-8")
        assert w.changed() is True

    def test_changed_resets_after_check(self, tmp_path):
        cfg = tmp_path / "config.yaml"
        sec = tmp_path / "secrets.yaml"
        cfg.write_text("x: 1", encoding="utf-8")
        sec.write_text("y: 2", encoding="utf-8")
        w = ConfigWatcher(cfg, sec)
        time.sleep(0.01)
        cfg.write_text("x: 2", encoding="utf-8")
        assert w.changed() is True
        assert w.changed() is False  # reset after first True


class TestConfigWatcherLoad:
    def test_load_returns_config_and_keys(self, tmp_path):
        cfg = tmp_path / "modeldeck.yaml"
        sec = tmp_path / "secrets.yaml"
        _write_config(cfg, {
            "codex": [{"id": "w", "enabled": True, "auth_mode": "subscription"}],
            "claude": [],
            "cursor": [],
        })
        sec.write_text(yaml.safe_dump({"mqtt": {}, "providers": {}}), encoding="utf-8")
        w = ConfigWatcher(cfg, sec)
        config, secrets, collectors, keys = w.load()
        assert ("codex", "w") in keys
        assert isinstance(keys, set)


# ---------------------------------------------------------------------------
# _active_keys
# ---------------------------------------------------------------------------

class TestActiveKeys:
    def test_returns_enabled_accounts_only(self):
        from modeldeck.config.loader import AppConfig
        cfg = AppConfig.model_validate({
            "providers": {
                "codex": [
                    {"id": "a", "enabled": True, "auth_mode": "subscription"},
                    {"id": "b", "enabled": False, "auth_mode": "subscription"},
                ],
                "claude": [{"id": "c", "enabled": True, "auth_mode": "oauth"}],
                "cursor": [],
            }
        })
        keys = _active_keys(cfg)
        assert ("codex", "a") in keys
        assert ("codex", "b") not in keys
        assert ("claude", "c") in keys
        assert len(keys) == 2


# ---------------------------------------------------------------------------
# CollectionRunner.apply_reload
# ---------------------------------------------------------------------------

class TestApplyReload:
    @pytest.mark.asyncio
    async def test_retires_removed_accounts(self):
        from modeldeck.service.scheduler import CollectionRunner
        from modeldeck.service.state_cache import StateCache

        mqtt = MagicMock()
        mqtt.retire_account = AsyncMock()
        runner = CollectionRunner(
            collectors=[],
            mqtt=mqtt,
            cache=StateCache(),
            active_keys={("codex", "old"), ("claude", "keep")},
        )
        await runner.apply_reload([], {("claude", "keep")})
        mqtt.retire_account.assert_awaited_once_with("codex", "old")
        assert runner._active_keys == {("claude", "keep")}
        assert runner._discovery_published is False

    @pytest.mark.asyncio
    async def test_swaps_collectors(self):
        from modeldeck.service.scheduler import CollectionRunner
        from modeldeck.service.state_cache import StateCache

        mqtt = MagicMock()
        mqtt.retire_account = AsyncMock()
        collector = MagicMock()
        runner = CollectionRunner(collectors=[], mqtt=mqtt, cache=StateCache())
        await runner.apply_reload([collector], {("codex", "new")})
        assert runner._collectors == [collector]
        assert ("codex", "new") in runner._active_keys

    @pytest.mark.asyncio
    async def test_retire_mqtt_error_is_logged_not_raised(self):
        """MqttError during retire_account is logged, not re-raised (scheduler line 71-72)."""
        from modeldeck.core.exceptions import MqttError
        from modeldeck.service.scheduler import CollectionRunner
        from modeldeck.service.state_cache import StateCache

        mqtt = MagicMock()
        mqtt.retire_account = AsyncMock(side_effect=MqttError("gone"))
        runner = CollectionRunner(
            collectors=[],
            mqtt=mqtt,
            cache=StateCache(),
            active_keys={("codex", "gone")},
        )
        # Should not raise
        await runner.apply_reload([], set())
        mqtt.retire_account.assert_awaited_once()


# ---------------------------------------------------------------------------
# run_loop with watcher — covers scheduler.py lines 146-154
#
# These use a mocked watcher (changed()/load() return canned values) instead
# of real file mtimes + sleep() so they are deterministic across platforms
# and CI runner speeds (no timing flakiness).
# ---------------------------------------------------------------------------

class TestRunLoopWithWatcher:
    @pytest.mark.asyncio
    async def test_run_loop_applies_reload_on_config_change(self):
        """watcher.changed() True → load() → apply_reload is called (scheduler 146-152)."""
        from modeldeck.service.scheduler import CollectionRunner
        from modeldeck.service.state_cache import StateCache

        mqtt = MagicMock()
        mqtt.retire_account = AsyncMock()
        mqtt.publish_snapshots = AsyncMock()
        mqtt._publish_bridge_status = AsyncMock()
        mqtt.connected = True

        runner = CollectionRunner(collectors=[], mqtt=mqtt, cache=StateCache())

        stop_ev = asyncio.Event()

        watcher = MagicMock()

        def changed_then_stop():
            # Trigger reload on the first check, then stop the loop so it
            # doesn't run forever (stop_event must be set AFTER the loop body
            # has had a chance to run, not before — the while-condition is
            # checked first).
            stop_ev.set()
            return True

        watcher.changed.side_effect = changed_then_stop
        watcher.load.return_value = (None, None, [], {("codex", "new")})

        applied: list[bool] = []
        orig_apply = runner.apply_reload

        async def spy_apply(collectors, keys):
            applied.append(True)
            await orig_apply(collectors, keys)

        runner.apply_reload = spy_apply  # type: ignore[method-assign]

        await runner.run_loop(300, stop_ev, watcher=watcher, reload_check_interval=0)

        assert applied == [True]
        watcher.load.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_loop_no_change_skips_reload(self):
        """watcher.changed() False → apply_reload is never called."""
        from modeldeck.service.scheduler import CollectionRunner
        from modeldeck.service.state_cache import StateCache

        mqtt = MagicMock()
        mqtt.publish_snapshots = AsyncMock()
        mqtt._publish_bridge_status = AsyncMock()
        mqtt.connected = True

        runner = CollectionRunner(collectors=[], mqtt=mqtt, cache=StateCache())
        stop_ev = asyncio.Event()

        watcher = MagicMock()

        def not_changed_then_stop():
            stop_ev.set()
            return False

        watcher.changed.side_effect = not_changed_then_stop

        await runner.run_loop(300, stop_ev, watcher=watcher, reload_check_interval=0)

        watcher.load.assert_not_called()

    @pytest.mark.asyncio
    async def test_run_loop_reload_exception_is_logged_not_raised(self):
        """watcher.load() raising is caught and logged (scheduler 153-154)."""
        from modeldeck.service.scheduler import CollectionRunner
        from modeldeck.service.state_cache import StateCache

        mqtt = MagicMock()
        mqtt.publish_snapshots = AsyncMock()
        mqtt._publish_bridge_status = AsyncMock()
        mqtt.connected = True

        runner = CollectionRunner(collectors=[], mqtt=mqtt, cache=StateCache())
        stop_ev = asyncio.Event()

        watcher = MagicMock()

        def changed_then_stop():
            stop_ev.set()
            return True

        watcher.changed.side_effect = changed_then_stop
        watcher.load.side_effect = RuntimeError("boom")

        # Should not raise — exception is caught and logged.
        await runner.run_loop(300, stop_ev, watcher=watcher, reload_check_interval=0)
        watcher.load.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_loop_uses_instance_watcher_when_no_kwarg(self):
        """run_loop falls back to self._config_watcher when no watcher kwarg given."""
        from modeldeck.service.scheduler import CollectionRunner
        from modeldeck.service.state_cache import StateCache

        mqtt = MagicMock()
        mqtt.publish_snapshots = AsyncMock()
        mqtt._publish_bridge_status = AsyncMock()
        mqtt.connected = True

        runner = CollectionRunner(collectors=[], mqtt=mqtt, cache=StateCache())
        stop_ev = asyncio.Event()

        watcher = MagicMock()

        def changed_then_stop():
            stop_ev.set()
            return True

        watcher.changed.side_effect = changed_then_stop
        watcher.load.return_value = (None, None, [], set())
        runner._config_watcher = watcher  # type: ignore[attr-defined]

        await runner.run_loop(300, stop_ev, reload_check_interval=0)
        watcher.changed.assert_called()


# ---------------------------------------------------------------------------
# Signal handler fallback — covers runner.py lines 65-67 (Windows fallback
# when add_signal_handler raises NotImplementedError). On Linux this branch
# is never naturally reached, so we mock it deterministically for both
# platforms instead of relying on real OS behaviour.
# ---------------------------------------------------------------------------

class TestSignalHandlerFallback:
    @pytest.mark.asyncio
    async def test_add_signal_handler_not_implemented_falls_back(self, monkeypatch, tmp_path):
        """Patch the *real* running loop's add_signal_handler to raise, rather than
        replacing the loop object entirely (which would break asyncio internals
        like Event/Task that also call get_running_loop())."""
        from modeldeck.service import runner as runner_mod

        cfg = tmp_path / "modeldeck.yaml"
        sec = tmp_path / "secrets.yaml"
        _write_config(cfg, {"codex": [], "claude": [], "cursor": []})
        sec.write_text(yaml.safe_dump({"mqtt": {}, "providers": {}}), encoding="utf-8")
        monkeypatch.setattr("modeldeck.config.loader.config_path", lambda: cfg)
        monkeypatch.setattr("modeldeck.config.loader.secrets_path", lambda: sec)

        monkeypatch.setattr(runner_mod.MqttBridge, "connect", AsyncMock())
        monkeypatch.setattr(runner_mod.MqttBridge, "disconnect", AsyncMock())
        monkeypatch.setattr(runner_mod.MqttBridge, "set_offline", AsyncMock())

        async def stop_immediately(self, interval, stop_event, **_kw):
            stop_event.set()

        monkeypatch.setattr(runner_mod.CollectionRunner, "run_loop", stop_immediately)

        real_loop = asyncio.get_running_loop()

        def boom_add_signal_handler(*a, **kw):
            raise NotImplementedError("not supported on this platform")

        monkeypatch.setattr(real_loop, "add_signal_handler", boom_add_signal_handler)

        signal_calls: list[tuple] = []

        def fake_signal(sig, handler):
            signal_calls.append((sig, handler))

        monkeypatch.setattr(runner_mod.signal, "signal", fake_signal)

        await runner_mod.run_service()

        assert len(signal_calls) == 1  # fallback path was exercised
