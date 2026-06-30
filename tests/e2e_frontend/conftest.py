"""Playwright E2E fixtures for ModelDeck web UI smoke tests.

The tests expect a running ``modeldeck webui`` process (served from the built
static assets or the fallback HTML) plus a real or mocked Python API.

For CI the SPA artifact is downloaded into ``src/modeldeck/webui/static/``
before this suite runs (via the shared CI workflow).

Set ``MODELDECK_WEBUI_URL`` to override the default http://127.0.0.1:8099.
"""
from __future__ import annotations

import os
import subprocess
import time

import pytest
from playwright.sync_api import Browser, BrowserContext, Page

BASE_URL = os.environ.get("MODELDECK_WEBUI_URL", "http://127.0.0.1:8099")


@pytest.fixture(scope="session")
def webui_process(tmp_path_factory):
    """Start modeldeck webui for the session; yield then terminate."""
    tmp = tmp_path_factory.mktemp("config")
    # Minimal config so the server starts without real provider secrets.
    cfg = tmp / "modeldeck.yaml"
    cfg.write_text(
        "mqtt:\n  host: 127.0.0.1\n  port: 1883\nproviders:\n  mock:\n    enabled: false\n  codex: []\n  claude: []\n  cursor: []\n",
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["MODELDECK_CONFIG_DIR"] = str(tmp)
    proc = subprocess.Popen(
        ["python", "-m", "modeldeck", "webui", "--host", "127.0.0.1", "--port", "8099"],
        env=env,
    )
    # Give it up to 5 s to start.
    import urllib.request
    for _ in range(50):
        try:
            urllib.request.urlopen(f"{BASE_URL}/", timeout=1)
            break
        except Exception:
            time.sleep(0.1)
    yield proc
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture()
def page(browser: Browser, webui_process) -> Page:  # noqa: ARG001
    """Fresh browser page for each test."""
    ctx: BrowserContext = browser.new_context()
    pg = ctx.new_page()
    yield pg
    ctx.close()
