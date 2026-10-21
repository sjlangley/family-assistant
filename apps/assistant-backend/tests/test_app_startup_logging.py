"""Characterisation tests for startup settings logging."""

import logging

import pytest

from assistant.app import _log_startup_settings
from assistant.settings import Settings

PREFIX = 'Application startup configuration:'


@pytest.fixture
def startup_messages(caplog):
    test_settings = Settings(
        GOOGLE_OAUTH_CLIENT_ID='real-client-id',
        SESSION_SECRET_KEY='real-secret',
        LLM_BASE_URL='http://llm',
    )

    with caplog.at_level(logging.INFO, logger='assistant.app'):
        _log_startup_settings(test_settings)

    return [r.getMessage() for r in caplog.records]


def test_log_startup_settings_logs_one_record(startup_messages):
    assert len(startup_messages) == 1
    assert startup_messages[0].startswith(PREFIX)


def test_log_startup_settings_redacts_sensitive_fields(startup_messages):
    message = startup_messages[0]

    assert "'client_id': '***REDACTED***'" in message
    assert "'session_secret_key': '***REDACTED***'" in message
    assert 'real-client-id' not in message
    assert 'real-secret' not in message


def _log_with(caplog, **overrides):
    test_settings = Settings(
        GOOGLE_OAUTH_CLIENT_ID='cid',
        SESSION_SECRET_KEY='sk',
        LLM_BASE_URL='http://llm',
        **overrides,
    )
    with caplog.at_level(logging.INFO, logger='assistant.app'):
        _log_startup_settings(test_settings)
    return caplog.records[0].getMessage()


def test_log_startup_settings_redacts_database_password(caplog):
    message = _log_with(caplog, DATABASE_PASSWORD='db-pass-123')

    assert "'database_password': '***REDACTED***'" in message
    assert 'db-pass-123' not in message


def test_log_startup_settings_masks_password_in_database_url(caplog):
    message = _log_with(
        caplog, DATABASE_URL='postgresql+asyncpg://u:url-pass-456@h:5432/db'
    )

    assert 'url-pass-456' not in message
    assert 'postgresql+asyncpg://u:***@h:5432/db' in message


def test_redact_database_url_hides_password():
    from assistant.app import _redact_database_url

    redacted = _redact_database_url('postgresql+asyncpg://u:secret-789@h/db')

    assert 'secret-789' not in redacted
    assert redacted == 'postgresql+asyncpg://u:***@h/db'
