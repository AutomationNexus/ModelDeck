"""Playwright E2E fixtures for ModelDeck web UI smoke tests.

Starts the ModelDeck web UI in a background thread using uvicorn so the
server runs in the same process and shares the filesystem — guaranteeing
that the static SPA assets (downloaded by CI before this suite runs) are
served from ``src/modeldeck/webui/static/`` without subprocess path
ambiguity.

Set ``MODELDECK_WEBUI_URL`` to override the default http://127.0.0.1:8099.
"""
from __future__ import annotations

import os
import threading
import time
import urllib.request

import pytest
from playwright.sync_api import Browser, BrowserContext, Page

BASE_URL = os.environ.get("MODELDECK_WEBUI_URL", "http://127.0.0.1:8099")
_PORT = int(BASE_URL.rstrip("/").rsplit(":", 1)[-1]) if ":" in BASE_URL else 8099


@pytest.fixture(scope="session")
def webui_server(tmp_path_factory):
    """Start modeldeck webui in a background thread; yield base URL."""
    import uvicorn

    from modeldeck.webui.app import create_app

    tmp = tmp_path_factory.mktemp("config")
    cfg = tmp / "modeldeck.yaml"
    cfg.write_text(
        "mqtt:\n  host: 127.0.0.1\n  port: 1883\n"
        "providers:\n  mock:\n    enabled: false\n"
        "  codex: []\n  claude: []\n  cursor: []\n",
        encoding="utf-8",
    )
    os.environ.setdefault("MODELDECK_CONFIG_DIR", str(tmp))

    app = create_app()
    config = uvicorn.Config(app, host="127.0.0.1", port=_PORT, log_level="error")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait up to 10 s for the server to become ready.
    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            urllib.request.urlopen(f"{BASE_URL}/", timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    else:
        raise RuntimeError(f"ModelDeck webui did not start within 10 s on {BASE_URL}")

    yield BASE_URL

    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture()
def page(browser: Browser, webui_server) -> Page:  # noqa: ARG001
    """Fresh browser page for each test."""
    ctx: BrowserContext = browser.new_context()
    pg = ctx.new_page()
    yield pg
    ctx.close()
