"""Entrypoint for the API application."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from assistant.routers import health
from assistant.settings import settings

logger = logging.getLogger(__name__)


app = FastAPI()

# Configure CORS
if settings.client_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.client_origins,
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )

app.include_router(health.router, prefix='/health')
