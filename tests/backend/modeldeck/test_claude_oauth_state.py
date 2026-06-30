"""Tests for Claude OAuth state parameter fix and parse_code_and_state."""

from __future__ import annotations

import httpx
import pytest

from modeldeck.auth.oauth_flow import (
    OAuthFlowError,
    exchange_code,
    extract_code_from_redirect,
    generate_verifier,
    parse_code_and_state,
)
from modeldeck.auth.provider_specs import CLAUDE_SPEC, CODEX_SPEC

# ---------------------------------------------------------------------------
# parse_code_and_state — all input forms
# ---------------------------------------------------------------------------

class TestParseCodeAndState:
    def test_bare_code_hash_state(self):
        """Claude console bare CODE#STATE format."""
        code, state = parse_code_and_state("ac_abc123#randomstate")
        assert code == "ac_abc123"
        assert state == "randomstate"

    def test_bare_code_no_state(self):
        """Plain bare code with no hash."""
        code, state = parse_code_and_state("ac_abc123")
        assert code == "ac_abc123"
        assert state is None

    def test_full_url_query_code_and_state(self):
        """Full URL with code and state in query string."""
        url = "https://console.anthropic.com/oauth/code/callback?code=mycode&state=mystate"
        code, state = parse_code_and_state(url)
        assert code == "mycode"
        assert state == "mystate"

    def test_full_url_query_code_only(self):
        """Full URL with code only."""
        url = "https://console.anthropic.com/oauth/code/callback?code=mycode"
        code, state = parse_code_and_state(url)
        assert code == "mycode"
        assert state is None

    def test_localhost_url(self):
        """Codex localhost URL with code and state."""
        url = "http://localhost:1455/auth/callback?code=codex_code&state=s1"
        code, state = parse_code_and_state(url)
        assert code == "codex_code"
        assert state == "s1"

    def test_fragment_url(self):
        """Code in URL fragment."""
        url = "https://example.com/callback#code=frag_code&state=frag_state"
        code, state = parse_code_and_state(url)
        assert code == "frag_code"
        assert state == "frag_state"

    def test_scheme_less_url(self):
        """Scheme-less address-bar URL."""
        url = "localhost:1455/auth/callback?code=sl_code&state=sl_state"
        code, state = parse_code_and_state(url)
        assert code == "sl_code"
        assert state == "sl_state"

    def test_bare_code_equals_param(self):
        """code=VALUE string."""
        code, state = parse_code_and_state("code=myvalue")
        assert code == "myvalue"
        assert state is None

    def test_bare_code_equals_with_state(self):
        """code=VALUE&state=S string."""
        code, state = parse_code_and_state("code=myvalue&state=mystate")
        assert code == "myvalue"
        assert state == "mystate"

    def test_strips_surrounding_whitespace(self):
        code, state = parse_code_and_state("  ac_abc  ")
        assert code == "ac_abc"
        assert state is None

    def test_strips_surrounding_quotes(self):
        code, state = parse_code_and_state('"ac_abc"')
        assert code == "ac_abc"
        assert state is None

    def test_strips_angle_brackets(self):
        code, state = parse_code_and_state("<ac_abc>")
        assert code == "ac_abc"
        assert state is None

    def test_empty_raises(self):
        with pytest.raises(OAuthFlowError, match="Nothing to parse"):
            parse_code_and_state("   ")

    def test_code_equals_no_value_raises(self):
        with pytest.raises(OAuthFlowError, match="No value found after"):
            parse_code_and_state("code=")

    def test_url_without_code_raises(self):
        with pytest.raises(OAuthFlowError, match="No 'code' parameter"):
            parse_code_and_state("https://console.anthropic.com/oauth/code/callback?state=s")


# ---------------------------------------------------------------------------
# extract_code_from_redirect — wrapper behaviour (state discarded)
# ---------------------------------------------------------------------------

class TestExtractCodeFromRedirect:
    def test_returns_code_only_from_hash_format(self):
        """CODE#STATE → only the code is returned."""
        result = extract_code_from_redirect("ac_abc123#randomstate")
        assert result == "ac_abc123"

    def test_returns_code_from_url(self):
        result = extract_code_from_redirect(
            "https://console.anthropic.com/oauth/code/callback?code=xyz&state=s"
        )
        assert result == "xyz"


# ---------------------------------------------------------------------------
# provider_specs — token_exchange_includes_state flag
# ---------------------------------------------------------------------------

class TestProviderSpecStateFlag:
    def test_claude_spec_has_state_flag_true(self):
        assert CLAUDE_SPEC.token_exchange_includes_state is True
        assert CLAUDE_SPEC.effective_token_exchange_includes_state is True

    def test_codex_spec_has_state_flag_false(self):
        assert CODEX_SPEC.token_exchange_includes_state is False
        assert CODEX_SPEC.effective_token_exchange_includes_state is False

    def test_env_override_true(self, monkeypatch):
        monkeypatch.setenv("MODELDECK_CODEX_OAUTH_TOKEN_INCLUDES_STATE", "1")
        assert CODEX_SPEC.effective_token_exchange_includes_state is True

    def test_env_override_false(self, monkeypatch):
        monkeypatch.setenv("MODELDECK_CLAUDE_OAUTH_TOKEN_INCLUDES_STATE", "0")
        assert CLAUDE_SPEC.effective_token_exchange_includes_state is False


# ---------------------------------------------------------------------------
# exchange_code — state forwarded for Claude, not for Codex
# ---------------------------------------------------------------------------

def _mock_client(status: int, body: dict | None = None) -> httpx.AsyncClient:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body or {})
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def _capturing_client() -> tuple[httpx.AsyncClient, list[httpx.Request]]:
    """Return a client that records requests and returns a valid token response."""
    captured: list[httpx.Request] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"access_token": "tok"})

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), captured


@pytest.mark.asyncio
async def test_exchange_code_claude_includes_state():
    """Claude exchange sends state in the JSON body."""
    client, captured = _capturing_client()
    await exchange_code(CLAUDE_SPEC, "mycode", generate_verifier(), state="mystate", client=client)
    assert len(captured) == 1
    import json as _json
    body = _json.loads(captured[0].content)
    assert body["code"] == "mycode"
    assert body["state"] == "mystate"


@pytest.mark.asyncio
async def test_exchange_code_claude_no_state_omits_field():
    """Claude exchange without state omits state from body."""
    client, captured = _capturing_client()
    await exchange_code(CLAUDE_SPEC, "mycode", generate_verifier(), client=client)
    import json as _json
    body = _json.loads(captured[0].content)
    assert "state" not in body


@pytest.mark.asyncio
async def test_exchange_code_codex_never_includes_state():
    """Codex exchange never sends state even when provided."""
    import modeldeck.auth.oauth_flow as _flow_mod

    async def error_handler(request: httpx.Request) -> httpx.Response:
        import urllib.parse
        params = dict(urllib.parse.parse_qsl(request.content.decode()))
        assert "state" not in params, "Codex should not send state"
        return httpx.Response(200, json={"access_token": "tok"})

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(error_handler))

    class _MockCtx:
        def __init__(self, **_kw):
            pass
        async def __aenter__(self):
            return mock_client
        async def __aexit__(self, *_):
            pass

    original = _flow_mod.httpx.AsyncClient
    _flow_mod.httpx.AsyncClient = _MockCtx  # type: ignore[assignment]
    try:
        await exchange_code(CODEX_SPEC, "codex_code", generate_verifier(), state="some_state")
    finally:
        _flow_mod.httpx.AsyncClient = original  # type: ignore[assignment]


@pytest.mark.asyncio
async def test_exchange_code_strips_embedded_hash_state():
    """code#state passed directly as code arg — hash is stripped."""
    client, captured = _capturing_client()
    await exchange_code(CLAUDE_SPEC, "mycode#mystate", generate_verifier(), client=client)
    import json as _json
    body = _json.loads(captured[0].content)
    assert body["code"] == "mycode"
    # state from the embedded hash should also be forwarded for Claude
    assert body["state"] == "mystate"
