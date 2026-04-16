"""add unique partial indexes for atomic durable_fact upserts

Revision ID: af123dbd3ffa
Revises: 57bad9ffdeea
Create Date: 2026-04-16 10:45:14.599450

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'af123dbd3ffa'
down_revision: Union[str, Sequence[str], None] = '57bad9ffdeea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add unique partial index for (user_id, fact_key, active)
    # This supports atomic upsert when fact_key is present
    op.execute(
        """
        CREATE UNIQUE INDEX durable_facts_user_fact_key_active_uniq
        ON durable_facts(user_id, fact_key, active)
        WHERE fact_key IS NOT NULL AND active = true
        """
    )
    # Add unique partial index for (user_id, subject, fact_text, active)
    # This supports atomic upsert when fact_key is absent (keyless facts only)
    op.execute(
        """
        CREATE UNIQUE INDEX durable_facts_user_subject_text_active_uniq
        ON durable_facts(user_id, subject, fact_text, active)
        WHERE active = true AND fact_key IS NULL
        """
    )
    # Drop the old non-unique index since we have unique indexes now
    op.execute('DROP INDEX IF EXISTS durable_facts_user_fact_key_active_idx')


def downgrade() -> None:
    """Downgrade schema."""
    # Restore the old non-unique index
    op.execute(
        """
        CREATE INDEX durable_facts_user_fact_key_active_idx
        ON durable_facts(user_id, fact_key, active)
        """
    )
    # Drop the unique partial indexes
    op.execute('DROP INDEX IF EXISTS durable_facts_user_fact_key_active_uniq')
    op.execute(
        'DROP INDEX IF EXISTS durable_facts_user_subject_text_active_uniq'
    )
