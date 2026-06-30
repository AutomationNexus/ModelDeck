"""Tests for modeldeck.auth.oauth_flow (all using httpx.MockTransport)."""

from __future__ import annotations

import re

import httpx
import pytest

from modeldeck.auth.oauth_flow import (
    OAuthFlowError,
    build_authorize_url,
    derive_challenge,
    exchange_code,
    extract_code_from_redirect,
    generate_state,
    generate_verifier,
    refresh_tokens,
)
from modeldeck.auth.provider_specs import CLAUDE_SPEC

# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------

_BASE64URL_RE = re.compile(r"^[A-Za-z0-9_\-]+$")


def test_generate_verifier_non_empty():
    """generate_verifier should return a non-empty string."""
    v = generate_verifier()
    assert isinstance(v, str)
    assert len(v) > 0


def test_generate_verifier_length_gte_43():
    """PKCE spec requires verifier length ≥ 43 characters."""
    v = generate_verifier()
    assert len(v) >= 43


def test_generate_verifier_base64url_chars():
    """Verifier must use only base64url characters (no padding '=')."""
    v = generate_verifier()
    assert _BASE64URL_RE.match(v), f"Invalid chars in verifier: {v!r}"


def test_generate_verifier_different_on_successive_calls():
    """generate_verifier must produce a unique value each call."""
    v1 = generate_verifier()
    v2 = generate_verifier()
    assert v1 != v2


def test_derive_challenge_returns_base64url():
    """derive_challenge must return a non-empty base64url string."""
    verifier = generate_verifier()
    challenge = derive_challenge(verifier)
    assert isinstance(challenge, str)
    assert len(challenge) > 0
    assert _BASE64URL_RE.match(challenge), f"Invalid chars in challenge: {challenge!r}"


def test_derive_challenge_no_padding():
    """Challenge must not contain '=' padding."""
    challenge = derive_challenge(generate_verifier())
    assert "=" not in challenge


def test_generate_state_non_empty():
    """generate_state should return a non-empty string."""
    s = generate_state()
    assert isinstance(s, str)
    assert len(s) > 0


def test_generate_state_different_on_successive_calls():
    state1 = generate_state()
    state2 = generate_state()
    assert state1 != state2


# ---------------------------------------------------------------------------
# build_authorize_url
# ---------------------------------------------------------------------------


def test_build_authorize_url_contains_client_id():
    verifier = generate_verifier()
    state = generate_state()
    url = build_authorize_url(CLAUDE_SPEC, verifier, state)
    assert CLAUDE_SPEC.client_id in url


def test_build_authorize_url_contains_code_challenge():
    verifier = generate_verifier()
    state = generate_state()
    url = build_authorize_url(CLAUDE_SPEC, verifier, state)
    challenge = derive_challenge(verifier)
    assert challenge in url


def test_build_authorize_url_contains_response_type_code():
    verifier = generate_verifier()
    state = generate_state()
    url = build_authorize_url(CLAUDE_SPEC, verifier, state)
    assert "response_type=code" in url


def test_build_authorize_url_starts_with_authorize_url(monkeypatch):
    """Built URL must start with the spec's effective authorize URL."""
    monkeypatch.delenv("MODELDECK_CLAUDE_OAUTH_AUTHORIZE_URL", raising=False)
    verifier = generate_verifier()
    state = generate_state()
    url = build_authorize_url(CLAUDE_SPEC, verifier, state)
    assert url.startswith(CLAUDE_SPEC.effective_authorize_url)


# ---------------------------------------------------------------------------
# extract_code_from_redirect
# ---------------------------------------------------------------------------


def test_extract_code_from_redirect_bare_code():
    """A bare code string (not a URL) should be returned as-is."""
    result = extract_code_from_redirect("abc123")
    assert result == "abc123"


def test_extract_code_from_redirect_full_url():
    """A full redirect URL should have its ?code= value extracted."""
    url = "https://console.anthropic.com/oauth/code/callback?code=xyz&state=s"
    result = extract_code_from_redirect(url)
    assert result == "xyz"


def test_extract_code_from_redirect_codex_url():
    """Codex localhost redirect URL should be parsed correctly."""
    url = "http://localhost:1455/auth/callback?code=ac_abc123&state=s"
    result = extract_code_from_redirect(url)
    assert result == "ac_abc123"


def test_extract_code_from_redirect_fragment():
    """Code in the URL fragment (#code=…) should be extracted."""
    url = "https://console.anthropic.com/oauth/code/callback#code=frag_code&state=xyz"
    result = extract_code_from_redirect(url)
    assert result == "frag_code"


def test_extract_code_from_redirect_scheme_less():
    """Scheme-less URL pasted from address bar should work."""
    url = "localhost:1455/auth/callback?code=schemeless_code&state=s"
    result = extract_code_from_redirect(url)
    assert result == "schemeless_code"


def test_extract_code_from_redirect_bare_param():
    """Bare 'code=VALUE' string (no URL) should extract the value."""
    result = extract_code_from_redirect("code=ac_rpcQfsO0Dgx80xz9zG2an3FCMGl")
    assert result == "ac_rpcQfsO0Dgx80xz9zG2an3FCMGl"


def test_extract_code_from_redirect_bare_param_with_state():
    """'code=VALUE&state=…' should extract the value only."""
    result = extract_code_from_redirect("code=mycode&state=randomstate")
    assert result == "mycode"


def test_extract_code_from_redirect_surrounding_quotes():
    """Surrounding quotes should be stripped."""
    result = extract_code_from_redirect('"abc123"')
    assert result == "abc123"


def test_extract_code_from_redirect_surrounding_angle_brackets():
    """Surrounding angle brackets should be stripped."""
    result = extract_code_from_redirect("<abc123>")
    assert result == "abc123"


def test_extract_code_from_redirect_missing_code_raises():
    """A redirect URL without ?code= or #code= should raise OAuthFlowError."""
    url = "https://console.anthropic.com/oauth/code/callback?state=s"
    with pytest.raises(OAuthFlowError):
        extract_code_from_redirect(url)


def test_extract_code_strips_whitespace():
    """Whitespace around bare code should be stripped."""
    result = extract_code_from_redirect("  mycode  ")
    assert result == "mycode"


# ---------------------------------------------------------------------------
# exchange_code
# ---------------------------------------------------------------------------


def _make_client(status: int, body: dict | None = None) -> httpx.AsyncClient:
    """Build an AsyncClient backed by a MockTransport returning a fixed response."""

    async def handler(request: httpx.Request) -> httpx.Response:
        if body is not None:
            return httpx.Response(status, json=body)
        return httpx.Response(status)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_exchange_code_success_returns_access_token():
    """A 200 response with access_token should be returned as a dict."""
    client = _make_client(200, {"access_token": "at", "refresh_token": "rt"})
    result = await exchange_code(CLAUDE_SPEC, "abc", generate_verifier(), client=client)
    assert result["access_token"] == "at"


@pytest.mark.asyncio
async def test_exchange_code_http_400_raises_oauth_flow_error():
    """HTTP 400 from token endpoint should raise OAuthFlowError."""
    client = _make_client(400)
    with pytest.raises(OAuthFlowError, match="400"):
        await exchange_code(CLAUDE_SPEC, "abc", generate_verifier(), client=client)


@pytest.mark.asyncio
async def test_exchange_code_missing_access_token_raises():
    """200 but missing access_token should raise OAuthFlowError."""
    client = _make_client(200, {"token_type": "Bearer"})
    with pytest.raises(OAuthFlowError, match="missing access_token"):
        await exchange_code(CLAUDE_SPEC, "abc", generate_verifier(), client=client)


@pytest.mark.asyncio
async def test_exchange_code_http_401_raises_oauth_flow_error():
    """HTTP 401 from token endpoint should raise OAuthFlowError."""
    client = _make_client(401)
    with pytest.raises(OAuthFlowError):
        await exchange_code(CLAUDE_SPEC, "abc", generate_verifier(), client=client)


@pytest.mark.asyncio
async def test_exchange_code_http_500_raises_oauth_flow_error():
    """HTTP 500 from token endpoint should raise OAuthFlowError."""
    client = _make_client(500)
    with pytest.raises(OAuthFlowError):
        await exchange_code(CLAUDE_SPEC, "abc", generate_verifier(), client=client)


@pytest.mark.asyncio
async def test_exchange_code_network_error_raises_oauth_flow_error():
    """Network-level transport error should raise OAuthFlowError."""

    async def error_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down")

    client = httpx.AsyncClient(transport=httpx.MockTransport(error_handler))
    with pytest.raises(OAuthFlowError):
        await exchange_code(CLAUDE_SPEC, "abc", generate_verifier(), client=client)


# ---------------------------------------------------------------------------
# refresh_tokens
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_tokens_success():
    """A 200 response with access_token should be returned."""
    client = _make_client(200, {"access_token": "new_at"})
    result = await refresh_tokens(CLAUDE_SPEC, "rt", client=client)
    assert result["access_token"] == "new_at"


@pytest.mark.asyncio
async def test_refresh_tokens_http_401_raises_oauth_flow_error():
    """HTTP 401 from token refresh should raise OAuthFlowError."""
    client = _make_client(401)
    with pytest.raises(OAuthFlowError):
        await refresh_tokens(CLAUDE_SPEC, "rt", client=client)


@pytest.mark.asyncio
async def test_refresh_tokens_missing_access_token_raises():
    """200 but missing access_token should raise OAuthFlowError."""
    client = _make_client(200, {"token_type": "Bearer"})
    with pytest.raises(OAuthFlowError, match="missing access_token"):
        await refresh_tokens(CLAUDE_SPEC, "rt", client=client)


@pytest.mark.asyncio
async def test_refresh_tokens_network_error_raises():
    """Network error during token refresh should raise OAuthFlowError."""

    async def error_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network down")

    client = httpx.AsyncClient(transport=httpx.MockTransport(error_handler))
    with pytest.raises(OAuthFlowError):
        await refresh_tokens(CLAUDE_SPEC, "rt", client=client)


# ---------------------------------------------------------------------------
# exchange_code / refresh_tokens without explicit client (uses own AsyncClient)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exchange_code_without_client_uses_own_http_client(monkeypatch):
    """When no client is passed, exchange_code uses its own httpx.AsyncClient."""
    import httpx as _httpx

    async def mock_handler(request: _httpx.Request) -> _httpx.Response:
        return _httpx.Response(200, json={"access_token": "no-client-at", "refresh_token": "rt"})

    # Patch httpx.AsyncClient so the internal client uses MockTransport
    original_async_client = _httpx.AsyncClient

    class PatchedAsyncClient(original_async_client):
        def __init__(self, **kwargs):
            kwargs["transport"] = _httpx.MockTransport(mock_handler)
            super().__init__(**kwargs)

    monkeypatch.setattr(_httpx, "AsyncClient", PatchedAsyncClient)

    from modeldeck.auth.oauth_flow import exchange_code as _exchange_code

    result = await _exchange_code(CLAUDE_SPEC, "some-code", generate_verifier())
    assert result["access_token"] == "no-client-at"
