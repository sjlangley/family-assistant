"""This module defines the configuration settings for the application.

It uses Pydantic's BaseSettings to load environment variables from a `.env`
file.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """The application settings."""

    model_config = SettingsConfigDict(env_file='.env')

    log_level: str = Field(default='INFO', alias='LOG_LEVEL')

    # For CORS Policy used in CORS middleware.

    # FastAPI’s CORS middleware does NOT support wildcard subdomains.
    # Ensure to include all specific subdomains for the web application.
    client_origins: list[str] = Field(
        default_factory=list, alias='CLIENT_ORIGINS'
    )


settings = Settings()  # pyrefly: ignore[missing-argument]
