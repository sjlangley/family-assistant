"""alembic/env.py must build a connectable URL, not a masked one."""

import importlib.util
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

ENV = Path(__file__).parents[2] / 'alembic' / 'env.py'


def _load_env() -> ModuleType:
    # env.py runs migrations at import; a mocked alembic.context makes that a no-op.
    fake_context = MagicMock()
    fake_context.config.config_file_name = None
    fake_context.is_offline_mode.return_value = True
    with patch('alembic.context', fake_context):
        spec = importlib.util.spec_from_file_location('alembic_env', ENV)
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return module


def _settings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        'database_url': None,
        'database_user': 'app',
        'database_password': 's3cret',
        'database_host': 'db',
        'database_port': 5432,
        'database_name': 'assistant',
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_get_url_from_components_keeps_real_password() -> None:
    env = _load_env()
    with patch.object(env, 'settings', _settings()):
        url = env.get_url()
    assert url == 'postgresql+psycopg://app:s3cret@db:5432/assistant'


def test_get_url_converts_database_url_driver() -> None:
    env = _load_env()
    cases = {
        'postgresql+asyncpg://u:p@h/d': 'postgresql+psycopg://u:p@h/d',
        'sqlite+aiosqlite:///x.db': 'sqlite:///x.db',
        'postgresql://u:p@h/d': 'postgresql://u:p@h/d',
    }
    for given, expected in cases.items():
        with patch.object(env, 'settings', _settings(database_url=given)):
            assert env.get_url() == expected
