"""Tests for bearer token verification."""

from fastapi import HTTPException
from google.auth import exceptions
import pytest

from assistant.security import google_bearer_token as bearer_token_module
from assistant.settings import settings


@pytest.mark.asyncio
async def test_verify_bearer_token_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_verify_oauth2_token(token: str, request, audience: str):  # noqa: ANN001
        assert token == 'token-123'
        assert audience == settings.client_id
        return {'sub': 'user-1', 'email': 'u@example.com', 'name': 'User One'}

    monkeypatch.setattr(
        bearer_token_module.google_id_token,
        'verify_oauth2_token',
        fake_verify_oauth2_token,
    )

    user = await bearer_token_module.verify_bearer_token('token-123')
    assert user.userid == 'user-1'
    assert user.email == 'u@example.com'
    assert user.name == 'User One'


@pytest.mark.asyncio
async def test_verify_bearer_token_missing_sub_raises_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_verify_oauth2_token(token: str, request, audience: str):  # noqa: ANN001
        return {'email': 'u@example.com'}

    monkeypatch.setattr(
        bearer_token_module.google_id_token,
        'verify_oauth2_token',
        fake_verify_oauth2_token,
    )

    with pytest.raises(HTTPException) as exc:
        await bearer_token_module.verify_bearer_token('token-123')

    assert exc.value.status_code == 401
    assert exc.value.detail == 'Invalid token payload'


@pytest.mark.asyncio
async def test_verify_bearer_token_allows_missing_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_verify_oauth2_token(token: str, request, audience: str):  # noqa: ANN001
        return {'sub': 'user-1'}

    monkeypatch.setattr(
        bearer_token_module.google_id_token,
        'verify_oauth2_token',
        fake_verify_oauth2_token,
    )

    user = await bearer_token_module.verify_bearer_token('token-123')
    assert user.userid == 'user-1'
    assert user.email is None
    assert user.name is None


@pytest.mark.asyncio
async def test_verify_bearer_token_invalid_issuer_raises_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_verify_oauth2_token(token: str, request, audience: str):  # noqa: ANN001
        raise exceptions.GoogleAuthError('bad issuer')

    monkeypatch.setattr(
        bearer_token_module.google_id_token,
        'verify_oauth2_token',
        fake_verify_oauth2_token,
    )

    with pytest.raises(HTTPException) as exc:
        await bearer_token_module.verify_bearer_token('token-123')

    assert exc.value.status_code == 401
    assert exc.value.detail == 'Authentication failed'


@pytest.mark.asyncio
async def test_verify_bearer_token_invalid_token_raises_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_verify_oauth2_token(token: str, request, audience: str):  # noqa: ANN001
        raise ValueError('nope')

    monkeypatch.setattr(
        bearer_token_module.google_id_token,
        'verify_oauth2_token',
        fake_verify_oauth2_token,
    )

    with pytest.raises(HTTPException) as exc:
        await bearer_token_module.verify_bearer_token('token-123')

    assert exc.value.status_code == 401
    assert exc.value.detail == 'Invalid token'
