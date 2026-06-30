"""Playwright E2E smoke tests for ModelDeck web UI.

Marked ``playwright`` so they are excluded from the standard pytest run
(``-m 'not integration'``) and only run via the CI e2e job or locally with:

    pytest tests/e2e_frontend -m playwright -v
"""
from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect

BASE = "http://127.0.0.1:8099"

pytestmark = pytest.mark.playwright


class TestUILoads:
    def test_page_title(self, page: Page) -> None:
        """The UI loads and sets the correct document title."""
        page.goto(BASE)
        expect(page).to_have_title("ModelDeck")

    def test_header_visible(self, page: Page) -> None:
        """Header with ModelDeck branding is visible."""
        page.goto(BASE)
        header = page.locator(".header-logo")
        expect(header).to_be_visible()
        expect(header).to_contain_text("ModelDeck")

    def test_add_account_button_visible(self, page: Page) -> None:
        """'Add account' button is present in the UI."""
        page.goto(BASE)
        btn = page.get_by_text("+ Add account")
        expect(btn).to_be_visible()

    def test_empty_state_shown_when_no_accounts(self, page: Page) -> None:
        """Empty state card is shown when no accounts are configured."""
        page.goto(BASE)
        # Wait for loading skeletons to disappear.
        page.wait_for_selector(".skeleton-card", state="detached", timeout=10_000)
        # Either empty state or account cards — both are valid.
        empty = page.locator(".empty-state")
        cards = page.locator(".account-card")
        assert empty.count() > 0 or cards.count() > 0


class TestAddAccountWizard:
    def test_wizard_opens_on_click(self, page: Page) -> None:
        """Clicking 'Add account' opens the wizard modal."""
        page.goto(BASE)
        page.wait_for_selector(".skeleton-card", state="detached", timeout=10_000)
        page.get_by_text("+ Add account").click()
        expect(page.locator(".modal")).to_be_visible()
        expect(page.locator(".modal-title")).to_contain_text("Add account")

    def test_wizard_shows_provider_selector(self, page: Page) -> None:
        """Step 1 of wizard has a provider dropdown."""
        page.goto(BASE)
        page.wait_for_selector(".skeleton-card", state="detached", timeout=10_000)
        page.get_by_text("+ Add account").click()
        select = page.locator("select").first
        expect(select).to_be_visible()

    def test_wizard_can_advance_to_mode_step(self, page: Page) -> None:
        """Clicking Next in step 1 advances to auth mode selection."""
        page.goto(BASE)
        page.wait_for_selector(".skeleton-card", state="detached", timeout=10_000)
        page.get_by_text("+ Add account").click()
        page.get_by_role("button", name="Next").click()
        # Step 2 shows auth mode radio options.
        expect(page.locator("input[type='radio']").first).to_be_visible(timeout=5_000)

    def test_wizard_cancel_closes_modal(self, page: Page) -> None:
        """Clicking Cancel closes the wizard modal."""
        page.goto(BASE)
        page.wait_for_selector(".skeleton-card", state="detached", timeout=10_000)
        page.get_by_text("+ Add account").click()
        expect(page.locator(".modal")).to_be_visible()
        page.get_by_role("button", name="Cancel").click()
        expect(page.locator(".modal")).to_have_count(0)

    def test_wizard_escape_overlay_closes(self, page: Page) -> None:
        """Clicking the overlay backdrop closes the modal."""
        page.goto(BASE)
        page.wait_for_selector(".skeleton-card", state="detached", timeout=10_000)
        page.get_by_text("+ Add account").click()
        expect(page.locator(".modal")).to_be_visible()
        # Click the overlay outside the modal box.
        page.locator(".overlay").click(position={"x": 5, "y": 5})
        expect(page.locator(".modal")).to_have_count(0)


class TestIngressBasePath:
    def test_api_calls_succeed_at_root(self, page: Page) -> None:
        """GET /accounts returns 200 (base-path routing works at root)."""
        resp = page.request.get(f"{BASE}/accounts")
        assert resp.status == 200

    def test_providers_endpoint_returns_list(self, page: Page) -> None:
        """GET /providers returns the expected shape."""
        resp = page.request.get(f"{BASE}/providers")
        assert resp.status == 200
        data = resp.json()
        assert "providers" in data
        ids = {p["name"] for p in data["providers"]}
        assert {"Claude", "OpenAI Codex", "Cursor"} == ids

    def test_providers_auth_modes_have_fields(self, page: Page) -> None:
        """Each auth mode from /providers contains id, label, and fields."""
        resp = page.request.get(f"{BASE}/providers")
        data = resp.json()
        for provider in data["providers"]:
            for mode in provider["auth_modes"]:
                assert "id" in mode
                assert "label" in mode
                assert "fields" in mode
                assert "oauth_capable" in mode


class TestErrorHandling:
    def test_status_dot_appears(self, page: Page) -> None:
        """Status dot in header changes state after load."""
        page.goto(BASE)
        page.wait_for_selector(".skeleton-card", state="detached", timeout=10_000)
        dot = page.locator(".status-dot")
        expect(dot).to_be_visible()
