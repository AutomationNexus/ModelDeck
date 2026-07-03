"""CLI commands for OAuth login wizard and account management."""

from __future__ import annotations

import argparse
import asyncio
from typing import Any

from modeldeck.auth.oauth_flow import (
    OAuthFlowError,
    build_authorize_url,
    exchange_code,
    generate_state,
    generate_verifier,
    parse_code_and_state,
)
from modeldeck.auth.provider_specs import get_spec, supported_oauth_providers
from modeldeck.config.loader import ProviderAccount, load_config, slugify
from modeldeck.config.secrets_writer import write_account_secrets
from modeldeck.core.logging import get_logger

logger = get_logger(__name__)

_PASTE_ONLY_PROVIDERS = ("cursor",)


def _print_separator() -> None:
    print("-" * 60)


# ---------------------------------------------------------------------------
# modeldeck login
# ---------------------------------------------------------------------------

async def _run_oauth_login(provider: str, label: str, account_id: str) -> int:
    """Interactive OAuth PKCE login for Claude or Codex."""
    spec = get_spec(provider)
    if spec is None:
        print(f"Error: provider '{provider}' does not support OAuth login wizard.")
        print(f"Supported providers: {', '.join(supported_oauth_providers())}")
        print("For Cursor, use: modeldeck accounts add --provider cursor --label '...'")
        return 1

    verifier = generate_verifier()
    state = generate_state()
    url = build_authorize_url(spec, verifier, state)

    print(f"\nAdding {provider} account: {label!r} (id: {account_id})")
    _print_separator()
    print("1. Open this URL in your browser:\n")
    print(f"   {url}\n")
    print("2. Log in and authorize ModelDeck.")
    print("3. After authorization, copy the code or the full redirect URL.")
    _print_separator()

    raw = input("Paste the authorization code or redirect URL: ").strip()
    if not raw:
        print("Error: no input provided.")
        return 1

    try:
        code, parsed_state = parse_code_and_state(raw)
    except OAuthFlowError as exc:
        print(f"Error: {exc}")
        return 1

    print("Exchanging code for tokens...")
    try:
        tokens = await exchange_code(spec, code, verifier, state=parsed_state)
    except OAuthFlowError as exc:
        print(f"Error: token exchange failed — {exc}")
        return 1

    fields: dict[str, str] = {}
    access = tokens.get("access_token")
    refresh = tokens.get("refresh_token")
    if isinstance(access, str) and access:
        fields["access_token"] = access
    if isinstance(refresh, str) and refresh:
        fields["refresh_token"] = refresh

    if not fields:
        print("Error: no tokens in exchange response.")
        return 1

    write_account_secrets(provider, account_id, fields)
    _ensure_account_in_config(provider, account_id, label, auth_mode="oauth")

    print(f"\nAccount '{label}' ({account_id}) saved successfully.")
    print(
        f"Run 'modeldeck credentials verify"
        f" --provider {provider} --account {account_id}' to test."
    )
    return 0


def _ensure_account_in_config(
    provider: str,
    account_id: str,
    label: str,
    auth_mode: str,
    enabled: bool = True,
) -> None:
    """Add account to modeldeck.yaml if not already present."""
    import yaml

    from modeldeck.core.paths import config_path

    path = config_path()
    if not path.exists():
        return

    raw: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    providers = raw.setdefault("providers", {})
    accounts: list[dict[str, Any]] = providers.get(provider, [])
    if not isinstance(accounts, list):
        accounts = []

    # Check if account_id already exists.
    existing_ids = {a.get("id") for a in accounts if isinstance(a, dict)}
    if account_id not in existing_ids:
        accounts.append({
            "id": account_id,
            "label": label,
            "enabled": enabled,
            "auth_mode": auth_mode,
        })
        providers[provider] = accounts
        path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
        logger.info("Added account %s/%s to config", provider, account_id)


def cmd_login(args: argparse.Namespace) -> int:
    """Run the OAuth login wizard for a provider."""
    provider = args.provider

    # Compute account id slug from label.
    try:
        config, _ = load_config()
        existing_accounts = getattr(config.providers, provider, [])
        existing_ids = {a.id for a in existing_accounts if isinstance(a, ProviderAccount)}
    except Exception:
        existing_ids = set()

    label = args.label or f"{provider}_{len(existing_ids) + 1}"
    account_id = slugify(label, existing_ids, provider_id=provider)

    if provider in _PASTE_ONLY_PROVIDERS:
        print("\nCursor does not support an OAuth login wizard.")
        print("To add a Cursor account, paste your JWT token:")
        print("  modeldeck accounts add --provider cursor --label 'My Cursor' --token 'eyJ...'")
        return 1

    return asyncio.run(_run_oauth_login(provider, label, account_id))


# ---------------------------------------------------------------------------
# modeldeck accounts list|add|remove|disable
# ---------------------------------------------------------------------------

def cmd_accounts_list(args: argparse.Namespace) -> int:
    """List all configured accounts."""
    try:
        config, _ = load_config()
    except Exception as exc:
        print(f"Error loading config: {exc}")
        return 1

    for provider in ("codex", "claude", "cursor"):
        accounts = getattr(config.providers, provider, [])
        if not isinstance(accounts, list):
            continue
        for acct in accounts:
            if not isinstance(acct, ProviderAccount):
                continue
            status = "enabled" if acct.enabled else "disabled"
            print(
                f"{provider}/{acct.id}  [{status}]  "
                f"label={acct.label!r}  auth_mode={acct.auth_mode}"
            )
    return 0


def cmd_accounts_add(args: argparse.Namespace) -> int:
    """Add a new account (paste-token path for Cursor and api-key modes)."""
    provider = args.provider
    token = getattr(args, "token", None) or ""
    auth_mode = getattr(args, "auth_mode", "auto") or "auto"

    try:
        config, _ = load_config()
        existing_accounts = getattr(config.providers, provider, [])
        existing_ids = {a.id for a in existing_accounts if isinstance(a, ProviderAccount)}
    except Exception:
        existing_ids = set()

    label = args.label or f"{provider}_{len(existing_ids) + 1}"
    account_id = slugify(label, existing_ids, provider_id=provider)

    if token:
        # Cursor personal or api-key paste
        if provider == "cursor":
            if token.startswith("eyJ"):
                write_account_secrets(provider, account_id, {"access_token": token})
            else:
                write_account_secrets(provider, account_id, {"session_token": token})
        elif provider in ("codex", "claude") and token.startswith("sk-admin"):
            write_account_secrets(provider, account_id, {"api_key": token})
        else:
            write_account_secrets(provider, account_id, {"access_token": token})

    _ensure_account_in_config(provider, account_id, label, auth_mode=auth_mode)
    print(f"Account '{label}' ({account_id}) added. Run credentials verify to confirm.")
    return 0


def cmd_accounts_remove(args: argparse.Namespace) -> int:
    """Remove an account from config and secrets."""
    import yaml

    from modeldeck.core.paths import config_path, secrets_path

    provider = args.provider
    account_id = args.account

    # Remove from config.
    cfg_path = config_path()
    if cfg_path.exists():
        raw: dict[str, Any] = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        accounts: list[Any] = raw.get("providers", {}).get(provider, [])
        if isinstance(accounts, list):
            before = len(accounts)
            accounts = [
                a for a in accounts
                if not (isinstance(a, dict) and a.get("id") == account_id)
            ]
            if len(accounts) < before:
                raw["providers"][provider] = accounts
                cfg_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    # Remove from secrets.
    sec_path = secrets_path()
    if sec_path.exists():
        raw_sec: dict[str, Any] = yaml.safe_load(sec_path.read_text(encoding="utf-8")) or {}
        prov_secrets = raw_sec.get("providers", {}).get(provider, {})
        if isinstance(prov_secrets, dict) and account_id in prov_secrets:
            del prov_secrets[account_id]
            raw_sec["providers"][provider] = prov_secrets
            sec_path.write_text(yaml.safe_dump(raw_sec, sort_keys=False), encoding="utf-8")

    print(f"Account {provider}/{account_id} removed.")
    print("Restart the service to retire MQTT sensors for this account.")
    return 0


def cmd_accounts_disable(args: argparse.Namespace) -> int:
    """Disable an account (keeps secrets, stops polling)."""
    import yaml

    from modeldeck.core.paths import config_path

    provider = args.provider
    account_id = args.account
    enable = getattr(args, "enable", False)

    cfg_path = config_path()
    if not cfg_path.exists():
        print("Config file not found.")
        return 1

    raw: dict[str, Any] = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    accounts: list[Any] = raw.get("providers", {}).get(provider, [])
    changed = False
    for acct in accounts:
        if isinstance(acct, dict) and acct.get("id") == account_id:
            acct["enabled"] = bool(enable)
            changed = True
    if not changed:
        print(f"Account {provider}/{account_id} not found in config.")
        return 1

    raw["providers"][provider] = accounts
    cfg_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    state = "enabled" if enable else "disabled"
    print(f"Account {provider}/{account_id} {state}.")
    return 0


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_login_commands(sub: argparse._SubParsersAction) -> None:
    """Register login and accounts subcommands."""
    # modeldeck login
    login = sub.add_parser("login", help="OAuth login wizard for Claude or Codex")
    login.add_argument(
        "--provider",
        choices=["claude", "codex", "cursor"],
        required=True,
        help="Provider to log in to",
    )
    login.add_argument("--label", default="", help="Human-readable account label")
    login.set_defaults(func=cmd_login)

    # modeldeck accounts
    accounts = sub.add_parser("accounts", help="Manage provider accounts")
    acc_sub = accounts.add_subparsers(dest="accounts_cmd", required=True)

    acc_list = acc_sub.add_parser("list", help="List all configured accounts")
    acc_list.set_defaults(func=cmd_accounts_list)

    acc_add = acc_sub.add_parser("add", help="Add a new account (paste-token)")
    acc_add.add_argument("--provider", choices=["claude", "codex", "cursor"], required=True)
    acc_add.add_argument("--label", default="")
    acc_add.add_argument("--token", default="", help="JWT/cookie/API key to paste")
    acc_add.add_argument("--auth-mode", dest="auth_mode", default="auto")
    acc_add.set_defaults(func=cmd_accounts_add)

    acc_remove = acc_sub.add_parser("remove", help="Remove an account")
    acc_remove.add_argument("--provider", choices=["claude", "codex", "cursor"], required=True)
    acc_remove.add_argument("--account", required=True, help="Account ID (slug)")
    acc_remove.set_defaults(func=cmd_accounts_remove)

    acc_disable = acc_sub.add_parser("disable", help="Disable an account")
    acc_disable.add_argument("--provider", choices=["claude", "codex", "cursor"], required=True)
    acc_disable.add_argument("--account", required=True, help="Account ID (slug)")
    acc_disable.set_defaults(func=cmd_accounts_disable)

    acc_enable = acc_sub.add_parser("enable", help="Re-enable a disabled account")
    acc_enable.add_argument("--provider", choices=["claude", "codex", "cursor"], required=True)
    acc_enable.add_argument("--account", required=True, help="Account ID (slug)")
    acc_enable.add_argument("--enable", action="store_true", default=True)
    acc_enable.set_defaults(func=cmd_accounts_disable)
