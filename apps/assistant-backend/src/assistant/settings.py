"""This module defines the configuration settings for the application.

It uses Pydantic's BaseSettings to load environment variables from a `.env`
file.
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from assistant.enums import Environment


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

    # For authentication

    # Disable authentication for development
    auth_disabled: bool = Field(default=False, alias='AUTH_DISABLED')

    # Environment setting (e.g., 'development', 'production')
    environment: Environment = Field(
        default=Environment.PRODUCTION, alias='ENVIRONMENT'
    )

    client_id: str = Field(
        ...,
        description='The Google OAuth client ID for verifying bearer tokens.',
        alias='GOOGLE_OAUTH_CLIENT_ID',
    )

    allowed_hosted_domains: list[str] = Field(
        default_factory=list,
        description=(
            'List of allowed hosted domains (hd claim) for Google accounts. '
            'If empty, accounts from any hosted domain are allowed.'
        ),
        alias='ALLOWED_HOSTED_DOMAINS',
    )

    session_secret_key: str = Field(
        ...,
        description=(
            'Secret key for signing session cookies. Must be set to a secure, '
            'random value in production.'
        ),
        alias='SESSION_SECRET_KEY',
    )


settings = Settings()  # pyrefly: ignore[missing-argument]
