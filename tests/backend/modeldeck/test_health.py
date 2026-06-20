"""Logging tests."""

from modeldeck.core.logging import RedactingFilter


def test_redacting_filter_masks_secrets():
    """Sensitive log fragments should be masked."""
    filt = RedactingFilter()
    text = filt.redact("Authorization: Bearer sk-secret")
    assert "sk-secret" not in text
    assert "***" in text
