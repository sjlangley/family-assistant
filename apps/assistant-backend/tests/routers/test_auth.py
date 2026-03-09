"""Tests for auth endpoint."""

import pytest

from tests.conftest import TEST_USER_EMAIL, TEST_USER_ID, TEST_USER_NAME

pytestmark = pytest.mark.usefixtures('override_google_bearer_token_dependency')


@pytest.mark.asyncio
async def test_login_endpoint(async_test_client):
    """Test that login endpoint returns a 200 OK with correct content."""
    response = await async_test_client.post('/auth/login')

    # Verify status code
    assert response.status_code == 200

    # Verify response contains correct user data
    response_data = response.json()
    assert response_data['email'] == TEST_USER_EMAIL
    assert response_data['userid'] == TEST_USER_ID
    assert response_data['name'] == TEST_USER_NAME

    # Verify session cookie was created
    assert 'family-assistant-session' in response.cookies

    # Verify session is valid by making another request with the cookie
    cookies = {
        'family-assistant-session': response.cookies['family-assistant-session']
    }
    verify_response = await async_test_client.get('/health', cookies=cookies)
    assert verify_response.status_code == 200


@pytest.mark.asyncio
async def test_logout_endpoint(authenticated_async_test_client):
    """Test that logout endpoint clears the session."""
    response = await authenticated_async_test_client.post('/auth/logout')

    # Verify status code
    assert response.status_code == 200

    # Verify session cookie was cleared
    assert 'family-assistant-session' not in response.cookies
