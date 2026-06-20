"""Mock collector tests."""

import pytest

from modeldeck.collectors.mock import MockCollector
from modeldeck.config.loader import AppConfig, ProviderSecrets
from modeldeck.schemas.snapshot import CollectorStatus


@pytest.mark.asyncio
async def test_mock_collector_returns_ok_snapshot():
    """Mock collector should return oscillating usage."""
    collector = MockCollector(AppConfig(), ProviderSecrets())
    snap = await collector.collect()
    assert snap.provider_id == "mock"
    assert snap.status == CollectorStatus.OK
    assert snap.usage_percent is not None
    assert 0 <= snap.usage_percent <= 100


@pytest.mark.asyncio
async def test_mock_collector_account_label():
    """Account label should appear in display name."""
    collector = MockCollector(AppConfig(), ProviderSecrets(), account_label="dev")
    snap = await collector.collect()
    assert "dev" in snap.display_name
