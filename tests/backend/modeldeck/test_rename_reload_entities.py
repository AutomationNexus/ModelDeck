"""Tests for account rename, live reload, and entities endpoint."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from starlette.testclient import TestClient

from modeldeck.config.secrets_writer import move_account_secrets
from modeldeck.service.reload import ConfigWatcher, _active_keys
from modeldeck.webui.app import create_app

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


def _write_secrets(path: Path, providers: dict) -> None:
    path.write_text(
        yaml.safe_dump({"mqtt": {}, "providers": providers}, sort_keys=False),
        encoding="utf-8",
    )


def _make_client(monkeypatch, tmp_path: Path) -> TestClient:
    cfg = tmp_path / "modeldeck.yaml"
    sec = tmp_path / "secrets.yaml"
    _write_config(cfg, {
        "codex": [{"id": "work", "label": "Work", "enabled": True, "auth_mode": "subscription"}],
        "claude": [{"id": "personal", "label": "Personal", "enabled": True, "auth_mode": "oauth"}],
        "cursor": [],
    })
    _write_secrets(sec, {
        "codex": {"work": {"access_token": "tok-work"}},
        "claude": {"personal": {"access_token": "tok-personal"}},
    })
    monkeypatch.setattr("modeldeck.webui.app.config_path", lambda: cfg)
    monkeypatch.setattr("modeldeck.config.loader.config_path", lambda: cfg)
    monkeypatch.setattr("modeldeck.config.loader.secrets_path", lambda: sec)
    monkeypatch.setattr("modeldeck.config.secrets_writer.secrets_path", lambda: sec)
    return TestClient(create_app())


# ---------------------------------------------------------------------------
# move_account_secrets
# ---------------------------------------------------------------------------

class TestMoveAccountSecrets:
    def test_moves_block(self, tmp_path):
        sec = tmp_path / "secrets.yaml"
        _write_secrets(sec, {"codex": {"old_id": {"access_token": "tok"}}})
        result = move_account_secrets("codex", "old_id", "new_id", secrets_file=sec)
        assert result is True
        raw = yaml.safe_load(sec.read_text())
        assert "new_id" in raw["providers"]["codex"]
        assert "old_id" not in raw["providers"]["codex"]
        assert raw["providers"]["codex"]["new_id"]["access_token"] == "tok"

    def test_returns_false_when_missing(self, tmp_path):
        sec = tmp_path / "secrets.yaml"
        _write_secrets(sec, {"codex": {}})
        assert move_account_secrets("codex", "nonexistent", "new_id", secrets_file=sec) is False

    def test_returns_false_when_file_missing(self, tmp_path):
        assert move_account_secrets("codex", "a", "b", secrets_file=tmp_path / "nope.yaml") is False

    def test_migrates_flat_format(self, tmp_path):
        sec = tmp_path / "secrets.yaml"
        # Flat (legacy) format — no nested account_id key.
        sec.write_text(
            yaml.safe_dump({"mqtt": {}, "providers": {"codex": {"access_token": "flat_tok"}}}),
            encoding="utf-8",
        )
        result = move_account_secrets("codex", "default", "new_id", secrets_file=sec)
        assert result is True
        raw = yaml.safe_load(sec.read_text())
        assert raw["providers"]["codex"]["new_id"]["access_token"] == "flat_tok"

    def test_returns_false_on_yaml_read_error(self, tmp_path):
        """Corrupted YAML content hits the except (OSError, yaml.YAMLError) branch."""
        sec = tmp_path / "secrets.yaml"
        # Invalid YAML (unbalanced flow mapping) raises yaml.YAMLError on parse.
        sec.write_text("providers: {codex: [unterminated", encoding="utf-8")
        assert move_account_secrets("codex", "a", "b", secrets_file=sec) is False

    def test_chmod_oserror_is_swallowed(self, tmp_path, monkeypatch):
        """chmod failure after a successful move does not raise (except OSError: pass)."""
        sec = tmp_path / "secrets.yaml"
        _write_secrets(sec, {"codex": {"old_id": {"access_token": "tok"}}})

        def boom_chmod(*a, **kw):
            raise OSError("cannot chmod")

        # move_account_secrets imports os as _os locally and calls _os.chmod —
        # patch the os module's chmod function (auto-restored by monkeypatch
        # at test teardown).
        monkeypatch.setattr("os.chmod", boom_chmod)
        result = move_account_secrets("codex", "old_id", "new_id", secrets_file=sec)
        assert result is True
        raw = yaml.safe_load(sec.read_text())
        assert "new_id" in raw["providers"]["codex"]


# ---------------------------------------------------------------------------
# Rename endpoint
# ---------------------------------------------------------------------------

class TestRenameEndpoint:
    def test_label_only_rename(self, monkeypatch, tmp_path):
        client = _make_client(monkeypatch, tmp_path)
        r = client.post("/accounts/codex/work/rename", json={"label": "My Work", "update_entity_id": False})
        assert r.status_code == 200
        data = r.json()
        assert data["account_id"] == "work"  # slug unchanged
        assert data["label"] == "My Work"
        assert data["entity_id_changed"] is False

    def test_entity_id_rename_changes_slug(self, monkeypatch, tmp_path):
        client = _make_client(monkeypatch, tmp_path)
        r = client.post("/accounts/codex/work/rename", json={"label": "Home Office", "update_entity_id": True})
        assert r.status_code == 200
        data = r.json()
        assert data["account_id"] == "home_office"  # new slug
        assert data["entity_id_changed"] is True

    def test_entity_id_rename_slug_same_no_change(self, monkeypatch, tmp_path):
        """When new slug equals old slug, entity_id_changed is False."""
        client = _make_client(monkeypatch, tmp_path)
        # "Work" → "work" → same slug
        r = client.post("/accounts/codex/work/rename", json={"label": "Work", "update_entity_id": True})
        assert r.status_code == 200
        assert r.json()["entity_id_changed"] is False
        assert r.json()["account_id"] == "work"

    def test_empty_label_rejected(self, monkeypatch, tmp_path):
        client = _make_client(monkeypatch, tmp_path)
        r = client.post("/accounts/codex/work/rename", json={"label": "  ", "update_entity_id": False})
        assert r.status_code == 400

    def test_unknown_account_404(self, monkeypatch, tmp_path):
        client = _make_client(monkeypatch, tmp_path)
        r = client.post("/accounts/codex/nonexistent/rename", json={"label": "X", "update_entity_id": False})
        assert r.status_code == 404

    def test_entity_id_rename_migrates_secrets(self, monkeypatch, tmp_path):
        client = _make_client(monkeypatch, tmp_path)
        client.post("/accounts/codex/work/rename", json={"label": "Home", "update_entity_id": True})
        sec = tmp_path / "secrets.yaml"
        raw = yaml.safe_load(sec.read_text())
        assert "home" in raw["providers"]["codex"]
        assert "work" not in raw["providers"]["codex"]

    def test_unknown_provider_400(self, monkeypatch, tmp_path):
        client = _make_client(monkeypatch, tmp_path)
        r = client.post("/accounts/unknown/work/rename", json={"label": "X", "update_entity_id": False})
        assert r.status_code == 400

    def test_config_not_found_404(self, monkeypatch, tmp_path):
        """rename returns 404 when modeldeck.yaml does not exist on disk."""
        missing_cfg = tmp_path / "missing.yaml"
        monkeypatch.setattr("modeldeck.webui.app.config_path", lambda: missing_cfg)
        monkeypatch.setattr("modeldeck.config.loader.config_path", lambda: missing_cfg)
        monkeypatch.setattr("modeldeck.config.loader.secrets_path", lambda: tmp_path / "secrets.yaml")
        client = TestClient(create_app())
        r = client.post("/accounts/codex/work/rename", json={"label": "X", "update_entity_id": False})
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# Entities endpoint
# ---------------------------------------------------------------------------

class TestEntitiesEndpoint:
    def test_returns_entities_for_codex_account(self, monkeypatch, tmp_path):
        client = _make_client(monkeypatch, tmp_path)
        r = client.get("/accounts/codex/work/entities")
        assert r.status_code == 200
        data = r.json()
        assert data["provider"] == "codex"
        assert data["account_id"] == "work"
        assert "device_id" in data
        assert "availability_topic" in data
        assert len(data["entities"]) > 0
        # Check shape of one entity
        e = data["entities"][0]
        assert "entity_id" in e
        assert "state_topic" in e
        assert "discovery_topic" in e
        assert e["entity_id"].startswith("sensor.modeldeck_codex_work_")

    def test_returns_entities_for_claude_account(self, monkeypatch, tmp_path):
        client = _make_client(monkeypatch, tmp_path)
        r = client.get("/accounts/claude/personal/entities")
        assert r.status_code == 200
        data = r.json()
        assert data["provider"] == "claude"
        for e in data["entities"]:
            assert "modeldeck_claude_personal_" in e["entity_id"]

    def test_load_config_error_returns_500(self, monkeypatch, tmp_path):
        """entities endpoint returns 500 when load_config raises."""
        client = _make_client(monkeypatch, tmp_path)

        def boom():
            raise RuntimeError("config corrupted")

        monkeypatch.setattr("modeldeck.webui.app.load_config", boom)
        r = client.get("/accounts/codex/work/entities")
        assert r.status_code == 500

    def test_unknown_account_404(self, monkeypatch, tmp_path):
        client = _make_client(monkeypatch, tmp_path)
        r = client.get("/accounts/codex/nonexistent/entities")
        assert r.status_code == 404

    def test_unknown_provider_400(self, monkeypatch, tmp_path):
        client = _make_client(monkeypatch, tmp_path)
        r = client.get("/accounts/unknown/work/entities")
        assert r.status_code == 400


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
# ConfigWatcher.load() — covers reload.py lines 58-65
# ---------------------------------------------------------------------------

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
        # collectors list: codex enabled but no secrets so collector built (enabled=True)
        assert isinstance(keys, set)


# ---------------------------------------------------------------------------
# move_account_secrets — additional edge cases (secrets_writer lines 132-145)
# ---------------------------------------------------------------------------

class TestMoveAccountSecretsEdgeCases:
    def test_returns_false_for_non_dict_raw(self, tmp_path):
        sec = tmp_path / "secrets.yaml"
        sec.write_text("- not a dict", encoding="utf-8")
        assert move_account_secrets("codex", "a", "b", secrets_file=sec) is False

    def test_returns_false_for_non_dict_providers(self, tmp_path):
        sec = tmp_path / "secrets.yaml"
        sec.write_text(yaml.safe_dump({"mqtt": {}, "providers": "broken"}), encoding="utf-8")
        assert move_account_secrets("codex", "a", "b", secrets_file=sec) is False

    def test_returns_false_for_non_dict_provider_block(self, tmp_path):
        sec = tmp_path / "secrets.yaml"
        sec.write_text(
            yaml.safe_dump({"mqtt": {}, "providers": {"codex": "broken_string"}}),
            encoding="utf-8",
        )
        assert move_account_secrets("codex", "a", "b", secrets_file=sec) is False


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
# Entities endpoint with auto auth_mode (covers app.py lines 828-829)
# ---------------------------------------------------------------------------

class TestEntitiesAutoAuthMode:
    def test_auto_auth_mode_codex_maps_to_subscription(self, monkeypatch, tmp_path):
        cfg = tmp_path / "modeldeck.yaml"
        sec = tmp_path / "secrets.yaml"
        _write_config(cfg, {
            "codex": [{"id": "auto_acc", "label": "Auto", "enabled": True, "auth_mode": "auto"}],
            "claude": [],
            "cursor": [],
        })
        sec.write_text(yaml.safe_dump({"mqtt": {}, "providers": {}}), encoding="utf-8")
        monkeypatch.setattr("modeldeck.webui.app.config_path", lambda: cfg)
        monkeypatch.setattr("modeldeck.config.loader.config_path", lambda: cfg)
        monkeypatch.setattr("modeldeck.config.loader.secrets_path", lambda: sec)
        from starlette.testclient import TestClient

        from modeldeck.webui.app import create_app
        client = TestClient(create_app())
        r = client.get("/accounts/codex/auto_acc/entities")
        assert r.status_code == 200
        # subscription metrics include usage_percent and reset_at
        entity_metrics = [e["metric"] for e in r.json()["entities"]]
        assert "usage_percent" in entity_metrics

    def test_auto_auth_mode_cursor_maps_to_personal(self, monkeypatch, tmp_path):
        cfg = tmp_path / "modeldeck.yaml"
        sec = tmp_path / "secrets.yaml"
        _write_config(cfg, {
            "codex": [],
            "claude": [],
            "cursor": [{"id": "cur_auto", "label": "C", "enabled": True, "auth_mode": "auto"}],
        })
        sec.write_text(yaml.safe_dump({"mqtt": {}, "providers": {}}), encoding="utf-8")
        monkeypatch.setattr("modeldeck.webui.app.config_path", lambda: cfg)
        monkeypatch.setattr("modeldeck.config.loader.config_path", lambda: cfg)
        monkeypatch.setattr("modeldeck.config.loader.secrets_path", lambda: sec)
        from starlette.testclient import TestClient

        from modeldeck.webui.app import create_app
        client = TestClient(create_app())
        r = client.get("/accounts/cursor/cur_auto/entities")
        assert r.status_code == 200
        entity_metrics = [e["metric"] for e in r.json()["entities"]]
        assert "usage_percent" in entity_metrics


# ---------------------------------------------------------------------------
# Static dir serving — covers app.py lines 315-318 (asset mounts) and 329
# (index.html served when the built SPA exists on disk). These are
# environment-dependent (only exercised when a frontend build artifact is
# present), so we deterministically point MODELDECK_STATIC_DIR at a fake
# built SPA directory for this test.
# ---------------------------------------------------------------------------

class TestStaticDirServing:
    def test_serves_built_index_html_and_mounts_assets(self, monkeypatch, tmp_path):
        static_dir = tmp_path / "static"
        assets_dir = static_dir / "assets"
        assets_dir.mkdir(parents=True)
        (static_dir / "index.html").write_text(
            "<html><body>Built SPA</body></html>", encoding="utf-8"
        )
        (assets_dir / "app.js").write_text("console.log('hi');", encoding="utf-8")

        monkeypatch.setenv("MODELDECK_STATIC_DIR", str(static_dir))
        client = TestClient(create_app())
        r = client.get("/")
        assert r.status_code == 200
        assert "Built SPA" in r.text

        # Confirm the /assets mount is live.
        r2 = client.get("/assets/app.js")
        assert r2.status_code == 200


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
