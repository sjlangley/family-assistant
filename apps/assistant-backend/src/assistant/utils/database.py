from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from assistant.settings import settings


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSession(request.app.state.engine) as session:
        yield session


DBSession = Annotated[AsyncSession, Depends(get_session)]


def _resolve_database_url() -> str:
    """Resolve the effective database URL for standalone DB sessions."""
    database_url = settings.database_url or settings.tcp_connection_url()
    if not database_url:
        raise RuntimeError('Database URL is not configured.')
    return database_url


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a standalone async database session for background jobs.

    This creates its own engine connection, suitable for long-running
    background tasks that don't have access to FastAPI's request context.
    """
    engine = create_async_engine(
        # pyrefly: ignore [bad-argument-type]
        _resolve_database_url(),
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
