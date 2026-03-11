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

    # LLM Backend
    llm_base_url: str = Field(
        ...,
        description='Base URL for the LLM backend service.',
        alias='LLM_BASE_URL',
    )
    llm_timeout_seconds: int = Field(
        default=120,
        description='Timeout in seconds for requests to the LLM backend.',
        alias='LLM_TIMEOUT_SECONDS',
    )
    llm_model: str = Field(
        default='gpt-4',
        description='Name of the LLM model to use.',
        alias='LLM_MODEL',
    )

    # Conversation storage
    database_url: str | None = Field(default=None, alias='DATABASE_URL')
    database_name: str = Field(
        default='conversations',
        description='The database name for storing conversations.',
        alias='DATABASE_NAME',
    )
    database_user: str = Field(
        default='nobody',
        description='Database username for storing conversations.',
        alias='DATABASE_USER',
    )
    database_password: str = Field(
        default='',
        description='Database password for storing conversations.',
        alias='DATABASE_PASSWORD',
    )
    database_host: str = Field(default='localhost', alias='DATABASE_HOST')
    database_port: int = Field(default=3306, alias='DATABASE_PORT')


settings = Settings()  # pyrefly: ignore[missing-argument]
