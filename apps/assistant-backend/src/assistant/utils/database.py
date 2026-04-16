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


@asynccontextmanager
async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get a standalone async database session for background jobs.

    This creates its own engine connection, suitable for long-running
    background tasks that don't have access to FastAPI's request context.
    """
    engine = create_async_engine(
        settings.database_url,
        echo=False,
    )
    async with AsyncSession(engine) as session:
        try:
            yield session
        finally:
            await engine.dispose()
