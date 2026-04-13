from logging.config import fileConfig
import os
from pathlib import Path
import sys

from alembic import context
from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine.url import URL
from sqlmodel import SQLModel

# Add the src directory to the path so we can import our models
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

# Ensure CLIENT_ORIGINS is properly formatted for pydantic-settings
# pytest-env can set it to a bare [] which causes JSON parsing errors
client_origins = os.getenv('CLIENT_ORIGINS', '').strip()
if client_origins and not client_origins.startswith('['):
    # If it's set but not valid JSON, unset it to use the default
    os.environ.pop('CLIENT_ORIGINS', None)
elif not client_origins:
    # If empty or not set, use empty JSON array
    os.environ['CLIENT_ORIGINS'] = '[]'

# Set minimal env vars for migration context if not already set
if not os.getenv('GOOGLE_OAUTH_CLIENT_ID'):
    os.environ['GOOGLE_OAUTH_CLIENT_ID'] = 'migration-placeholder'
if not os.getenv('SESSION_SECRET_KEY'):
    os.environ['SESSION_SECRET_KEY'] = 'migration-placeholder'
if not os.getenv('LLM_BASE_URL'):
    os.environ['LLM_BASE_URL'] = 'http://localhost:8000'
if not os.getenv('CHROMA_HOST'):
    os.environ['CHROMA_HOST'] = 'http://localhost:8100'

# Import settings after sys.path and env var setup
# Import all models to ensure they're registered with SQLModel metadata
from assistant.models.conversation_sql import (  # noqa: E402, F401
    Conversation,
    Message,
)
from assistant.models.memory_sql import (  # noqa: E402, F401
    ConversationMemorySummary,
    DurableFact,
)
from assistant.settings import settings  # noqa: E402

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = SQLModel.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def get_url() -> str:
    """Get database URL from settings, converting to synchronous driver for migrations."""
    if settings.database_url is not None:
        url_str = settings.database_url
        # Convert async driver to sync for migrations
        if '+aiosqlite://' in url_str:
            return url_str.replace('+aiosqlite://', '://')
        elif 'postgresql+asyncpg://' in url_str:
            return url_str.replace(
                'postgresql+asyncpg://', 'postgresql+psycopg://'
            )
        return url_str

    # Build URL from components with synchronous driver
    return str(
        URL.create(
            drivername='postgresql+psycopg',  # Use synchronous driver for migrations
            username=settings.database_user,
            password=settings.database_password,
            host=settings.database_host,
            port=settings.database_port,
            database=settings.database_name,
        )
    )


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={'paramstyle': 'named'},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # Override the sqlalchemy.url in the alembic.ini config
    configuration = config.get_section(config.config_ini_section, {})
    configuration['sqlalchemy.url'] = get_url()

    connectable = engine_from_config(
        configuration,
        prefix='sqlalchemy.',
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
