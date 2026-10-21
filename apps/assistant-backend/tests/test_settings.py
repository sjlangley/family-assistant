"""Tests for list-valued settings parsing."""

import pytest

from assistant.settings import Settings


@pytest.fixture(autouse=True)
def required_env(monkeypatch):
    monkeypatch.setenv('GOOGLE_OAUTH_CLIENT_ID', 'cid')
    monkeypatch.setenv('SESSION_SECRET_KEY', 'secret')
    monkeypatch.setenv('LLM_BASE_URL', 'http://llm')
    monkeypatch.setenv('CHROMA_HOST', 'chroma')


def make_settings() -> Settings:
    return Settings(_env_file=None)  # pyrefly: ignore[missing-argument]


def test_client_origins_comma_separated(monkeypatch):
    monkeypatch.setenv(
        'CLIENT_ORIGINS', 'http://localhost:3000, http://localhost:5173,'
    )
    assert make_settings().client_origins == [
        'http://localhost:3000',
        'http://localhost:5173',
    ]


def test_allowed_hosted_domains_comma_separated(monkeypatch):
    monkeypatch.setenv('ALLOWED_HOSTED_DOMAINS', 'a.com,b.com')
    assert make_settings().allowed_hosted_domains == ['a.com', 'b.com']


def test_allowed_hosted_domains_empty_string(monkeypatch):
    monkeypatch.setenv('ALLOWED_HOSTED_DOMAINS', '')
    assert make_settings().allowed_hosted_domains == []


def test_client_origins_json_list_still_accepted(monkeypatch):
    monkeypatch.setenv('CLIENT_ORIGINS', '["http://a","http://b"]')
    assert make_settings().client_origins == ['http://a', 'http://b']
