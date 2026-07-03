"""Tests for move_account_secrets.

Note: the account-rename HTTP endpoint (POST /accounts/{provider}/{account_id}
/rename) was removed. Account labels are always server-generated
("{Provider Display Name} {n}") and are no longer user-customizable, so
there is nothing left to rename via the API. move_account_secrets() itself
remains as a small, independently useful config-migration utility, tested
here on its own.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from modeldeck.config.secrets_writer import move_account_secrets

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_secrets(path: Path, providers: dict) -> None:
    path.write_text(
        yaml.safe_dump({"mqtt": {}, "providers": providers}, sort_keys=False),
        encoding="utf-8",
    )


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
