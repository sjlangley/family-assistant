"""Characterisation tests for startup settings logging."""

import logging
from types import SimpleNamespace

from asgi_lifespan import LifespanManager
import pytest
from sqlalchemy.engine.url import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from assistant.app import (
    _log_database_url,
    _log_startup_settings,
    _redact_database_url,
    app,
)
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
    redacted = _redact_database_url('postgresql+asyncpg://u:secret-789@h/db')

    assert 'secret-789' not in redacted
    assert redacted == 'postgresql+asyncpg://u:***@h/db'


@pytest.mark.parametrize(
    'url',
    [
        'not-a-url',
        '',
        None,
        'postgresql+asyncpg://u:pw-secret@h:abc/db',
    ],
)
def test_redact_database_url_never_raises(url):
    redacted = _redact_database_url(url)

    assert isinstance(redacted, str)
    assert 'pw-secret' not in redacted


def test_redact_database_url_does_not_echo_unparseable_input():
    assert 'pw-secret' not in _redact_database_url('pw-secret')


def test_redact_database_url_masks_password_query_param():
    redacted = _redact_database_url(
        'postgresql+asyncpg://u@h/db?password=secret'
    )

    assert 'secret' not in redacted


def test_log_startup_settings_survives_unparseable_database_url(caplog):
    message = _log_with(caplog, DATABASE_URL='not-a-url')

    assert len(caplog.records) == 1
    assert message.startswith(PREFIX)


def test_log_startup_settings_leaves_passwordless_database_url(caplog):
    message = _log_with(caplog, DATABASE_URL='postgresql+asyncpg://u@h:5432/db')

    assert "'database_url': 'postgresql+asyncpg://u@h:5432/db'" in message


def test_log_startup_settings_database_url_empty(caplog):
    message = _log_with(caplog, DATABASE_URL='')

    assert "'database_url': ''" in message


def test_log_startup_settings_database_url_unset(caplog, monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    test_settings = Settings(
        GOOGLE_OAUTH_CLIENT_ID='cid',
        SESSION_SECRET_KEY='sk',
        LLM_BASE_URL='http://llm',
        _env_file=None,
    )
    with caplog.at_level(logging.INFO, logger='assistant.app'):
        _log_startup_settings(test_settings)

    assert "'database_url': None" in caplog.records[0].getMessage()


def test_log_database_url_hides_password(caplog):
    with caplog.at_level(logging.INFO, logger='assistant.app'):
        _log_database_url('postgresql+asyncpg://u:final-pass-1@h:5432/db')

    messages = [r.getMessage() for r in caplog.records]
    assert len(messages) == 1
    assert messages[0].startswith('Final Database URL:')
    assert 'final-pass-1' not in messages[0]


def test_redact_database_url_hides_fragment_after_unencoded_at():
    redacted = _redact_database_url('postgresql+asyncpg://u:p@ss-frag@h/db')

    assert 'ss-frag' not in redacted


def test_log_startup_settings_unparseable_url_with_colon_hides_text(caplog):
    message = _log_with(caplog, DATABASE_URL='not a url:pw-secret')

    assert 'pw-secret' not in message


@pytest.mark.parametrize(
    ('url', 'secret'),
    [
        ('postgresql+asyncpg://u:final-pass-2@h/db', 'final-pass-2'),
        ('postgresql+asyncpg://u@h/db?password=qpw-77', 'qpw-77'),
    ],
)
@pytest.mark.asyncio
async def test_lifespan_database_url_records_hide_password(
    url, secret, caplog, monkeypatch
):
    """Run the real lifespan; only the engine is swapped for in-memory sqlite."""
    # setup_logging() reconfigures root handlers, which would drop caplog's.
    monkeypatch.setattr('assistant.app.setup_logging', lambda: None)
    monkeypatch.setattr('assistant.app.get_database_url', lambda: url)

    def fake_engine(*_args, **_kwargs):
        real = create_async_engine('sqlite+aiosqlite:///:memory:')
        return SimpleNamespace(
            url=make_url(url), begin=real.begin, dispose=real.dispose
        )

    monkeypatch.setattr('assistant.app.create_async_engine', fake_engine)

    with caplog.at_level(logging.INFO, logger='assistant.app'):
        async with LifespanManager(app):
            pass

    messages = [r.getMessage() for r in caplog.records]
    assert any(m.startswith('Final Database URL:') for m in messages)
    assert any(m.startswith('Engine URL') for m in messages)
    assert all(secret not in m for m in messages)
