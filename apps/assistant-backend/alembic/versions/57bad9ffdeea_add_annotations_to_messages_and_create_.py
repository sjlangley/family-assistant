"""Add annotations to messages and create memory tables

Revision ID: 57bad9ffdeea
Revises:
Create Date: 2026-04-13 18:35:28.157609

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '57bad9ffdeea'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _get_inspector() -> sa.Inspector:
    """Return a SQLAlchemy inspector for the current Alembic bind."""
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    """Return whether the given table exists."""
    return table_name in _get_inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    """Return whether the given column exists on the table."""
    if not _has_table(table_name):
        return False
    columns = _get_inspector().get_columns(table_name)
    return any(column['name'] == column_name for column in columns)


def _has_index(table_name: str, index_name: str) -> bool:
    """Return whether the given index exists on the table."""
    if not _has_table(table_name):
        return False
    indexes = _get_inspector().get_indexes(table_name)
    return any(index['name'] == index_name for index in indexes)


def _require_bootstrapped_base_tables() -> None:
    """Validate that the pre-existing base schema has been bootstrapped."""
    missing_tables = [
        table_name
        for table_name in ('conversations', 'messages')
        if not _has_table(table_name)
    ]
    if missing_tables:
        missing_tables_text = ', '.join(sorted(missing_tables))
        msg = (
            'Alembic revision 57bad9ffdeea depends on existing base tables '
            f'but found missing table(s): {missing_tables_text}. '
            'Bootstrap the base schema first, then mark this revision as '
            'applied (for example, create the base tables and run '
            '`alembic stamp head`), or add a baseline migration that creates '
            '`conversations` and `messages` before this revision.'
        )
        raise RuntimeError(msg)


def upgrade() -> None:
    """Upgrade schema."""
    _require_bootstrapped_base_tables()

    # Add annotations column to messages table
    if not _has_column('messages', 'annotations'):
        op.add_column(
            'messages',
            sa.Column('annotations', sa.JSON(), nullable=True),
        )

    # Create conversation_memory_summaries table
    if not _has_table('conversation_memory_summaries'):
        op.create_table(
            'conversation_memory_summaries',
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('conversation_id', sa.UUID(), nullable=False),
            sa.Column('user_id', sa.String(length=255), nullable=False),
            sa.Column('summary_text', sa.Text(), nullable=False),
            sa.Column('source_message_id', sa.UUID(), nullable=True),
            sa.Column(
                'version',
                sa.Integer(),
                server_default='1',
                nullable=False,
            ),
            sa.Column(
                'created_at',
                sa.DateTime(timezone=True),
                server_default=sa.text('now()'),
                nullable=False,
            ),
            sa.Column(
                'updated_at',
                sa.DateTime(timezone=True),
                server_default=sa.text('now()'),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ['conversation_id'],
                ['conversations.id'],
                name='conversation_memory_summaries_conversation_id_fkey',
            ),
            sa.ForeignKeyConstraint(
                ['source_message_id'],
                ['messages.id'],
                name='conversation_memory_summaries_source_message_id_fkey',
            ),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint(
                'conversation_id',
                name='conversation_memory_summaries_conversation_id_key',
            ),
        )
    if not _has_index(
        'conversation_memory_summaries',
        'conversation_memory_summaries_user_id_idx',
    ):
        op.create_index(
            'conversation_memory_summaries_user_id_idx',
            'conversation_memory_summaries',
            ['user_id'],
        )
    if not _has_index(
        'conversation_memory_summaries',
        'conversation_memory_summaries_user_updated_idx',
    ):
        op.create_index(
            'conversation_memory_summaries_user_updated_idx',
            'conversation_memory_summaries',
            ['user_id', 'updated_at'],
        )

    # Create durable_facts table
    if not _has_table('durable_facts'):
        op.create_table(
            'durable_facts',
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('user_id', sa.String(length=255), nullable=False),
            sa.Column('subject', sa.String(length=255), nullable=False),
            sa.Column('fact_key', sa.String(length=255), nullable=True),
            sa.Column('fact_text', sa.Text(), nullable=False),
            sa.Column('confidence', sa.String(length=32), nullable=False),
            sa.Column('source_type', sa.String(length=32), nullable=False),
            sa.Column('source_conversation_id', sa.UUID(), nullable=True),
            sa.Column('source_message_id', sa.UUID(), nullable=True),
            sa.Column('source_excerpt', sa.Text(), nullable=True),
            sa.Column(
                'active',
                sa.Boolean(),
                server_default=sa.text('true'),
                nullable=False,
            ),
            sa.Column(
                'created_at',
                sa.DateTime(timezone=True),
                server_default=sa.text('now()'),
                nullable=False,
            ),
            sa.Column(
                'updated_at',
                sa.DateTime(timezone=True),
                server_default=sa.text('now()'),
                nullable=False,
            ),
            sa.ForeignKeyConstraint(
                ['source_conversation_id'],
                ['conversations.id'],
                name='durable_facts_source_conversation_id_fkey',
            ),
            sa.ForeignKeyConstraint(
                ['source_message_id'],
                ['messages.id'],
                name='durable_facts_source_message_id_fkey',
            ),
            sa.PrimaryKeyConstraint('id'),
        )
    if not _has_index('durable_facts', 'durable_facts_source_message_idx'):
        op.create_index(
            'durable_facts_source_message_idx',
            'durable_facts',
            ['source_message_id'],
        )
    if not _has_index(
        'durable_facts',
        'durable_facts_user_active_updated_idx',
    ):
        op.create_index(
            'durable_facts_user_active_updated_idx',
            'durable_facts',
            ['user_id', 'active', 'updated_at'],
        )
    if not _has_index(
        'durable_facts',
        'durable_facts_user_fact_key_active_idx',
    ):
        op.create_index(
            'durable_facts_user_fact_key_active_idx',
            'durable_facts',
            ['user_id', 'fact_key', 'active'],
        )
    if not _has_index('durable_facts', 'durable_facts_user_id_idx'):
        op.create_index(
            'durable_facts_user_id_idx',
            'durable_facts',
            ['user_id'],
        )
    if not _has_index('durable_facts', 'durable_facts_user_subject_idx'):
        op.create_index(
            'durable_facts_user_subject_idx',
            'durable_facts',
            ['user_id', 'subject'],
        )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop durable_facts indexes
    if _has_index('durable_facts', 'durable_facts_user_subject_idx'):
        op.drop_index(
            'durable_facts_user_subject_idx',
            table_name='durable_facts',
        )
    if _has_index('durable_facts', 'durable_facts_user_id_idx'):
        op.drop_index('durable_facts_user_id_idx', table_name='durable_facts')
    if _has_index('durable_facts', 'durable_facts_user_fact_key_active_idx'):
        op.drop_index(
            'durable_facts_user_fact_key_active_idx',
            table_name='durable_facts',
        )
    if _has_index('durable_facts', 'durable_facts_user_active_updated_idx'):
        op.drop_index(
            'durable_facts_user_active_updated_idx',
            table_name='durable_facts',
        )
    if _has_index('durable_facts', 'durable_facts_source_message_idx'):
        op.drop_index(
            'durable_facts_source_message_idx',
            table_name='durable_facts',
        )

    # Drop durable_facts table
    if _has_table('durable_facts'):
        op.drop_table('durable_facts')

    # Drop conversation_memory_summaries indexes
    if _has_index(
        'conversation_memory_summaries',
        'conversation_memory_summaries_user_updated_idx',
    ):
        op.drop_index(
            'conversation_memory_summaries_user_updated_idx',
            table_name='conversation_memory_summaries',
        )
    if _has_index(
        'conversation_memory_summaries',
        'conversation_memory_summaries_user_id_idx',
    ):
        op.drop_index(
            'conversation_memory_summaries_user_id_idx',
            table_name='conversation_memory_summaries',
        )

    # Drop conversation_memory_summaries table
    if _has_table('conversation_memory_summaries'):
        op.drop_table('conversation_memory_summaries')

    # Drop annotations column from messages
    if _has_column('messages', 'annotations'):
        op.drop_column('messages', 'annotations')
