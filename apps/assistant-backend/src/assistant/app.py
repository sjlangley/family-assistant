"""Entrypoint for the API application."""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel import SQLModel
from starlette.middleware.sessions import SessionMiddleware

from assistant.enums import Environment
from assistant.logging import setup_logging
from assistant.routers import auth, chat, conversations, health, user
from assistant.services import get_llm_service
from assistant.settings import Settings, settings
from assistant.utils.database import get_database_url

logger = logging.getLogger(__name__)


def _redact_database_url(url) -> str:
    try:
        parsed = make_url(url)
    except (ArgumentError, ValueError):
        return '<unparseable database URL>'
    if '@' in (parsed.host or ''):
        return '<unparseable database URL>'
    query = {
        k: '***' if k in ('password', 'passwd', 'pwd') else v
        for k, v in parsed.query.items()
    }
    return parsed.set(query=query).render_as_string(hide_password=True)


def _get_safe_settings_for_logging(settings_to_log: Settings) -> dict:
    """Get settings with sensitive values redacted for logging.

    Args:
        settings_to_log: The application settings.


    Returns:
        Dictionary of settings with sensitive values masked.
    """
    # Fields that should never be logged
    sensitive_fields = {
        'client_id',
        'session_secret_key',
        'database_password',
    }

    data = settings_to_log.model_dump()
    safe_data = {}

    for key, value in data.items():
        if key in sensitive_fields:
            safe_data[key] = '***REDACTED***'
        elif key == 'database_url' and value:
            safe_data[key] = _redact_database_url(value)
        else:
            safe_data[key] = value

    return safe_data


def _log_startup_settings(settings_to_log: Settings) -> None:
    """Log application settings at startup for debugging.

    Args:
        settings_to_log: The application settings to log.
    """
    safe_settings = _get_safe_settings_for_logging(settings_to_log)
    logger.info(
        'Application startup configuration: %s',
        safe_settings,
    )


def _log_database_url(database_url) -> None:
    logger.info(f'Final Database URL: {_redact_database_url(database_url)!r}')


@asynccontextmanager
async def lifespan(application: FastAPI):
    setup_logging()
    _log_startup_settings(settings)

    # Get the canonical database URL (uses DATABASE_URL or builds TCP connection)
    database_url = get_database_url()

    _log_database_url(database_url)

    application.state.engine = create_async_engine(
        database_url, pool_pre_ping=True
    )

    async with application.state.engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    engine_url = _redact_database_url(application.state.engine.url)
    logger.info(f'Engine URL after parsing: {engine_url!r}')
    logger.info(
        f'Engine URL components -> dialect='
        f'{application.state.engine.url.get_dialect().name}, '
        f'driver={application.state.engine.url.get_driver_name()}'
    )

    yield

    await get_llm_service().aclose()
    engine = getattr(application.state, 'engine', None)
    if engine is not None:
        await engine.dispose()


app = FastAPI(lifespan=lifespan)

# Configure CORS
if settings.client_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.client_origins,
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret_key,
    session_cookie='family-assistant-session',
    max_age=60 * 60 * 24 * 7,  # 7 days
    same_site='lax',
    https_only=settings.environment
    in (Environment.PRODUCTION, Environment.STAGING),
)

app.include_router(auth.router, prefix='/auth')
app.include_router(health.router, prefix='/health')
app.include_router(chat.router, prefix='/api/v1/chat')
app.include_router(conversations.router, prefix='/api/v1/conversations')
app.include_router(user.router, prefix='/user')
