"""Entrypoint for the API application."""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.engine.url import URL
from sqlmodel import SQLModel, create_engine
from starlette.middleware.sessions import SessionMiddleware

from assistant.enums import Environment
from assistant.logging import setup_logging
from assistant.routers import auth, chat, conversations, health, user
from assistant.services import get_llm_service
from assistant.settings import Settings, settings

logger = logging.getLogger(__name__)


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
    }

    data = settings_to_log.model_dump()
    safe_data = {}

    for key, value in data.items():
        if key in sensitive_fields:
            safe_data[key] = '***REDACTED***'
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


def tcp_connection_url() -> URL:
    """Initializes a TCP connection URL for a Cloud SQL instance of PostgreSQL.

    Returns:
        URL: The SQLAlchemy URL object configured for TCP connection.
    """
    db_user = settings.database_user
    db_pass = settings.database_password
    db_name = settings.database_name
    db_host = settings.database_host
    db_port = settings.database_port

    return URL.create(
        drivername='postgresql+asyncpg',
        username=db_user,
        password=db_pass,
        host=db_host,
        port=db_port,
        database=db_name,
    )


@asynccontextmanager
async def lifespan(application: FastAPI):
    setup_logging()
    _log_startup_settings(settings)

    # Connect to the database
    if settings.database_url is not None:
        database_url = settings.database_url
    else:
        database_url = tcp_connection_url()

    logger.info(f'Final Database URL: {database_url!r}')  # Ensure this is redacted if it's a string

    application.state.engine = create_async_engine(database_url, pool_pre_ping=True)

    async with application.state.engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    logger.info(f'Engine URL after parsing: {application.state.engine.url!r}')
    logger.info(
        f'Engine URL components -> dialect='
        f'{application.state.engine.url.get_dialect().name}, '
        f'driver={application.state.engine.url.get_driver_name()}'
    )

    yield

    await get_llm_service().aclose()
    application.state.engine.dispose()


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
