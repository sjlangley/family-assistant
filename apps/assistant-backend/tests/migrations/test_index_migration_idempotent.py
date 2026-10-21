"""Index migration SQL must be safe to re-run."""

import importlib.util
from pathlib import Path
import re
from unittest.mock import patch

import pytest

MIGRATION = (
    Path(__file__).parents[2]
    / 'alembic'
    / 'versions'
    / 'af123dbd3ffa_add_unique_partial_indexes_for_atomic_.py'
)


def _emitted_sql(direction: str) -> list[str]:
    spec = importlib.util.spec_from_file_location('migration_af123', MIGRATION)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with patch.object(module.op, 'execute') as execute:
        getattr(module, direction)()
    return [' '.join(str(c.args[0]).split()) for c in execute.call_args_list]


@pytest.mark.parametrize('direction', ['upgrade', 'downgrade'])
def test_index_statements_are_guarded(direction: str) -> None:
    statements = _emitted_sql(direction)
    assert statements
    for sql in statements:
        if re.match(r'CREATE (UNIQUE )?INDEX', sql):
            assert 'IF NOT EXISTS' in sql, sql
        elif sql.startswith('DROP INDEX'):
            assert 'IF EXISTS' in sql, sql
