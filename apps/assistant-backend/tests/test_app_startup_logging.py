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
