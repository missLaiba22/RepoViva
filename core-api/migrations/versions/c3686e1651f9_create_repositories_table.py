"""create repositories table

Revision ID: c3686e1651f9
Revises: 0f185e91dca2
Create Date: 2026-09-11 15:14:11.714758

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3686e1651f9'
down_revision: Union[str, Sequence[str], None] = '0f185e91dca2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'repositories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('owner_user_id', sa.BigInteger(), nullable=False),
        sa.Column('github_url', sa.String(length=500), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('error_message', sa.String(length=1000), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('owner_user_id', 'github_url', name='uq_repo_owner_url'),
    )
    op.create_index(
        op.f('ix_repositories_owner_user_id'),
        'repositories',
        ['owner_user_id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_repositories_owner_user_id'), table_name='repositories')
    op.drop_table('repositories')