"""Playwright E2E smoke tests for ModelDeck web UI.

Split into two groups:
- ``api`` — hit the FastAPI endpoints directly (JSON); no SPA needed.
  These always run when ``has-e2e: true``.
- ``spa`` — interact with the React SPA (CSS selectors, button clicks).
  Only run when the env var ``MODELDECK_WEBUI_HAS_SPA=1`` is set, which
  CI sets after confirming ``static/index.html`` exists.

All tests are marked ``playwright`` for exclusion from the standard
``pytest -q`` run; the CI e2e job collects them with ``-m playwright``.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect

BASE = "http://127.0.0.1:8099"

# True when the built SPA artifact has been placed into static/.
_HAS_SPA = os.environ.get("MODELDECK_WEBUI_HAS_SPA", "").strip() in ("1", "true", "yes")

# Compute expected static/index.html path for the skip message.
_REPO_ROOT = Path(__file__).parent.parent.parent
_INDEX_HTML = _REPO_ROOT / "src" / "modeldeck" / "webui" / "static" / "index.html"

pytestmark = pytest.mark.playwright

_spa = pytest.mark.skipif(
    not _HAS_SPA,
    reason=f"SPA not built: {_INDEX_HTML} absent; set MODELDECK_WEBUI_HAS_SPA=1",
)


# ---------------------------------------------------------------------------
# API tests — no SPA needed, always run
# ---------------------------------------------------------------------------

class TestAPIEndpoints:
    def test_root_returns_200(self, page: Page) -> None:
        """GET / returns 200 regardless of whether the SPA is present."""
        page.goto(BASE)
        assert page.title() == "ModelDeck"

    def test_accounts_endpoint(self, page: Page) -> None:
        """GET /accounts returns 200 and a JSON array."""
        resp = page.request.get(f"{BASE}/accounts")
        assert resp.status == 200
        data = resp.json()
        assert isinstance(data, list)

    def test_providers_endpoint_returns_list(self, page: Page) -> None:
        """GET /providers returns the expected shape."""
        resp = page.request.get(f"{BASE}/providers")
        assert resp.status == 200
        data = resp.json()
        assert "providers" in data
        names = {p["name"] for p in data["providers"]}
        assert {"Claude", "OpenAI Codex", "Cursor"} == names

    def test_providers_auth_modes_have_fields(self, page: Page) -> None:
        """Each auth mode from /providers contains id, label, fields, oauth_capable."""
        resp = page.request.get(f"{BASE}/providers")
        data = resp.json()
        for provider in data["providers"]:
            for mode in provider["auth_modes"]:
                assert "id" in mode
                assert "label" in mode
                assert "fields" in mode
                assert "oauth_capable" in mode

    def test_post_accounts_unknown_provider_returns_400(self, page: Page) -> None:
        """POST /accounts with unknown provider returns 400."""
        resp = page.request.post(
            f"{BASE}/accounts",
            data={"provider": "unknown", "label": "X"},
        )
        assert resp.status in (400, 422)

    def test_paste_token_empty_returns_400(self, page: Page) -> None:
        """POST /token with empty value returns 400."""
        resp = page.request.post(
            f"{BASE}/accounts/cursor/default/token",
            data={"field": "access_token", "value": ""},
        )
        assert resp.status in (400, 422)

    def test_paste_token_bad_field_returns_400(self, page: Page) -> None:
        """POST /token with unknown field returns 400."""
        resp = page.request.post(
            f"{BASE}/accounts/cursor/default/token",
            data={"field": "bad_xyz", "value": "sometoken"},
        )
        assert resp.status in (400, 422)


# ---------------------------------------------------------------------------
# SPA tests — only run when MODELDECK_WEBUI_HAS_SPA=1
# ---------------------------------------------------------------------------

class TestUILoads:
    @_spa
    def test_header_visible(self, page: Page) -> None:
        """Header with ModelDeck branding is visible."""
        page.goto(BASE)
        expect(page.locator(".header-logo")).to_be_visible()
        expect(page.locator(".header-logo")).to_contain_text("ModelDeck")

    @_spa
    def test_add_account_button_visible(self, page: Page) -> None:
        """'Add account' button is present in the UI."""
        page.goto(BASE)
        expect(page.get_by_text("+ Add account")).to_be_visible()

    @_spa
    def test_empty_state_shown_when_no_accounts(self, page: Page) -> None:
        """Empty state card or account cards are shown after loading."""
        page.goto(BASE)
        page.wait_for_selector(".skeleton-card", state="detached", timeout=10_000)
        empty = page.locator(".empty-state")
        cards = page.locator(".account-card")
        assert empty.count() > 0 or cards.count() > 0

    @_spa
    def test_status_dot_appears(self, page: Page) -> None:
        """Status dot in header changes state after load."""
        page.goto(BASE)
        page.wait_for_selector(".skeleton-card", state="detached", timeout=10_000)
        expect(page.locator(".status-dot")).to_be_visible()


class TestAddAccountWizard:
    @_spa
    def test_wizard_opens_on_click(self, page: Page) -> None:
        """Clicking 'Add account' opens the wizard modal."""
        page.goto(BASE)
        page.wait_for_selector(".skeleton-card", state="detached", timeout=10_000)
        page.get_by_text("+ Add account").click()
        expect(page.locator(".modal")).to_be_visible()
        expect(page.locator(".modal-title")).to_contain_text("Add account")

    @_spa
    def test_wizard_shows_provider_selector(self, page: Page) -> None:
        """Step 1 of wizard has a provider dropdown."""
        page.goto(BASE)
        page.wait_for_selector(".skeleton-card", state="detached", timeout=10_000)
        page.get_by_text("+ Add account").click()
        expect(page.locator("select").first).to_be_visible()

    @_spa
    def test_wizard_can_advance_to_mode_step(self, page: Page) -> None:
        """Clicking Next in step 1 advances to auth mode selection."""
        page.goto(BASE)
        page.wait_for_selector(".skeleton-card", state="detached", timeout=10_000)
        page.get_by_text("+ Add account").click()
        page.get_by_role("button", name="Next").click()
        expect(page.locator("input[type='radio']").first).to_be_visible(timeout=5_000)

    @_spa
    def test_wizard_cancel_closes_modal(self, page: Page) -> None:
        """Clicking Cancel closes the wizard modal."""
        page.goto(BASE)
        page.wait_for_selector(".skeleton-card", state="detached", timeout=10_000)
        page.get_by_text("+ Add account").click()
        expect(page.locator(".modal")).to_be_visible()
        page.get_by_role("button", name="Cancel").click()
        expect(page.locator(".modal")).to_have_count(0)

    @_spa
    def test_wizard_escape_overlay_closes(self, page: Page) -> None:
        """Clicking the overlay backdrop closes the modal."""
        page.goto(BASE)
        page.wait_for_selector(".skeleton-card", state="detached", timeout=10_000)
        page.get_by_text("+ Add account").click()
        expect(page.locator(".modal")).to_be_visible()
        page.locator(".overlay").click(position={"x": 5, "y": 5})
        expect(page.locator(".modal")).to_have_count(0)
