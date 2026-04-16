from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.engine.url import URL
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from assistant.settings import settings


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(request.app.state.engine) as session:
        yield session


DBSession = Annotated[AsyncSession, Depends(get_session)]


def get_database_url() -> URL | str:
    """Get the canonical database URL, resolving TCP connection if needed.

    Returns configured DATABASE_URL if set, otherwise constructs a TCP
    connection URL for Cloud SQL using database credentials.

    Returns:
        URL: The SQLAlchemy URL object configured for database connection.

    Raises:
        RuntimeError: If database URL cannot be resolved.
    """
    # If explicit database_url is configured, use it
    if settings.database_url is not None:
        return settings.database_url

    # Otherwise, build TCP connection URL from credentials
    db_user = settings.database_user
    db_pass = settings.database_password
    db_name = settings.database_name
    db_host = settings.database_host
    db_port = settings.database_port

    url = URL.create(
        drivername='postgresql+asyncpg',
        username=db_user,
        password=db_pass,
        host=db_host,
        port=db_port,
        database=db_name,
    )

    if not url:
        raise RuntimeError('Database URL could not be constructed.')

    return url


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a standalone async database session for background jobs.

    This creates its own engine connection, suitable for long-running
    background tasks that don't have access to FastAPI's request context.
    Uses the canonical database URL resolution from get_database_url().
    """
    engine = create_async_engine(
        get_database_url(),
        echo=False,
    )
    # expire_on_commit=False prevents ORM instances from expiring after commit,
    # which can cause lazy loads to fail in background jobs where we need to
    # access attributes after committing (e.g., indexing persisted memory).
    async with AsyncSession(engine, expire_on_commit=False) as session:
        try:
            yield session
        finally:
            await engine.dispose()
