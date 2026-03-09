"""Tests for user endpoint."""

import pytest


@pytest.mark.asyncio
async def test_get_current_user_endpoint(authenticated_async_test_client):
    """Test that get_current_user endpoint returns correct content."""
    response = await authenticated_async_test_client.get('/user/current')
    assert response.status_code == 200
    data = response.json()
    assert data['email'] == 'test_user@test.org'
    assert data['userid'] == 'test-oid-123'
    assert data['name'] == 'Test User'


@pytest.mark.asyncio
async def test_get_current_user_unauthenticated(async_test_client):
    """Test that get_current_user endpoint errors for unauthenticated users."""
    response = await async_test_client.get('/user/current')
    assert response.status_code == 401
