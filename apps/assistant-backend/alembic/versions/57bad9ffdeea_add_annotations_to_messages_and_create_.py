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


def upgrade() -> None:
    """Upgrade schema."""
    # Add annotations column to messages table
    op.add_column(
        'messages',
        sa.Column('annotations', sa.JSON(), nullable=True),
    )

    # Create conversation_memory_summaries table
    op.create_table(
        'conversation_memory_summaries',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('conversation_id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.String(length=255), nullable=False),
        sa.Column('summary_text', sa.Text(), nullable=False),
        sa.Column('source_message_id', sa.UUID(), nullable=True),
        sa.Column('version', sa.Integer(), server_default='1', nullable=False),
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
    op.create_index(
        'conversation_memory_summaries_user_id_idx',
        'conversation_memory_summaries',
        ['user_id'],
    )
    op.create_index(
        'conversation_memory_summaries_user_updated_idx',
        'conversation_memory_summaries',
        ['user_id', 'updated_at'],
    )

    # Create durable_facts table
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
    op.create_index(
        'durable_facts_source_message_idx',
        'durable_facts',
        ['source_message_id'],
    )
    op.create_index(
        'durable_facts_user_active_updated_idx',
        'durable_facts',
        ['user_id', 'active', 'updated_at'],
    )
    op.create_index(
        'durable_facts_user_fact_key_active_idx',
        'durable_facts',
        ['user_id', 'fact_key', 'active'],
    )
    op.create_index(
        'durable_facts_user_id_idx',
        'durable_facts',
        ['user_id'],
    )
    op.create_index(
        'durable_facts_user_subject_idx',
        'durable_facts',
        ['user_id', 'subject'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop durable_facts indexes
    op.drop_index('durable_facts_user_subject_idx', table_name='durable_facts')
    op.drop_index('durable_facts_user_id_idx', table_name='durable_facts')
    op.drop_index(
        'durable_facts_user_fact_key_active_idx',
        table_name='durable_facts',
    )
    op.drop_index(
        'durable_facts_user_active_updated_idx',
        table_name='durable_facts',
    )
    op.drop_index(
        'durable_facts_source_message_idx',
        table_name='durable_facts',
    )

    # Drop durable_facts table
    op.drop_table('durable_facts')

    # Drop conversation_memory_summaries indexes
    op.drop_index(
        'conversation_memory_summaries_user_updated_idx',
        table_name='conversation_memory_summaries',
    )
    op.drop_index(
        'conversation_memory_summaries_user_id_idx',
        table_name='conversation_memory_summaries',
    )

    # Drop conversation_memory_summaries table
    op.drop_table('conversation_memory_summaries')

    # Drop annotations column from messages
    op.drop_column('messages', 'annotations')
