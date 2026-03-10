"""Entrypoint for the API application."""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from assistant.enums import Environment
from assistant.routers import auth, chat, health, user
from assistant.services import get_llm_service
from assistant.settings import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    yield

    await get_llm_service().aclose()


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
app.include_router(user.router, prefix='/user')
