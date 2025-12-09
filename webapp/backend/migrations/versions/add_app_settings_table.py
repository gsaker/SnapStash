"""add_app_settings_table

Revision ID: a1b2c3d4e5f6
Revises: 0b3a63387df4
Create Date: 2025-11-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '0b3a63387df4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create app_settings table for storing user-configurable settings."""

    op.create_table(
        'app_settings',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('key', sa.String(), nullable=False),
        sa.Column('value', sa.String(), nullable=True),
        sa.Column('value_type', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('category', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('key')
    )

    # Create indexes
    op.create_index('ix_app_settings_key', 'app_settings', ['key'], unique=True)
    op.create_index('idx_settings_category', 'app_settings', ['category'])


def downgrade() -> None:
    """Remove app_settings table."""

    # Drop indexes
    op.drop_index('idx_settings_category', table_name='app_settings')
    op.drop_index('ix_app_settings_key', table_name='app_settings')

    # Drop table
    op.drop_table('app_settings')
