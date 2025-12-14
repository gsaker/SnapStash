"""Add push device tokens table

Revision ID: add_push_device_tokens
Revises: add_app_settings_table
Create Date: 2025-12-13

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_push_device_tokens'
down_revision = 'add_app_settings_table'
branch_labels = None
depends_on = None


def upgrade():
    # Create push_device_tokens table
    op.create_table(
        'push_device_tokens',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('token', sa.String(), nullable=False),
        sa.Column('platform', sa.String(), nullable=False),
        sa.Column('app_version', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='1'),
        sa.Column('last_seen', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('token')
    )
    
    # Create indexes
    op.create_index('idx_push_tokens_platform', 'push_device_tokens', ['platform'])
    op.create_index('idx_push_tokens_active', 'push_device_tokens', ['is_active'])


def downgrade():
    # Drop indexes
    op.drop_index('idx_push_tokens_active', 'push_device_tokens')
    op.drop_index('idx_push_tokens_platform', 'push_device_tokens')
    
    # Drop table
    op.drop_table('push_device_tokens')
