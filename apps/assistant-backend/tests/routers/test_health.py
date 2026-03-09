"""Tests for health check endpoint."""

import pytest


@pytest.mark.asyncio
async def test_health_endpoint(async_test_client):
    """Test that health endpoint returns a 200 OK with correct content."""
    response = await async_test_client.get('/health')
    assert response.status_code == 200
    assert response.json() == {'status': 'OK'}
