"""add_group_chat_support_and_participants

Revision ID: 0b3a63387df4
Revises: c04ba21ff190
Create Date: 2025-09-10 21:07:57.192339

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0b3a63387df4'
down_revision: Union[str, Sequence[str], None] = 'c04ba21ff190'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add group chat support and conversation participants table."""
    
    # Add group chat fields to conversations table
    op.add_column('conversations', sa.Column('group_name', sa.String(), nullable=True))
    op.add_column('conversations', sa.Column('is_group_chat', sa.Boolean(), nullable=False, default=False))
    op.add_column('conversations', sa.Column('participant_count', sa.Integer(), nullable=True))
    
    # Create conversation_participants table
    op.create_table(
        'conversation_participants',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('conversation_id', sa.String(), nullable=False),
        sa.Column('user_id', sa.String(), nullable=False),
        sa.Column('join_timestamp', sa.BigInteger(), nullable=True),
        sa.Column('unknown_field_2', sa.BigInteger(), nullable=True),
        sa.Column('unknown_field_3', sa.BigInteger(), nullable=True),
        sa.Column('unknown_field_9', sa.BigInteger(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index('idx_conversation_participants_conv', 'conversation_participants', ['conversation_id'])
    op.create_index('idx_conversation_participants_user', 'conversation_participants', ['user_id'])


def downgrade() -> None:
    """Remove group chat support and conversation participants table."""
    
    # Drop indexes
    op.drop_index('idx_conversation_participants_user', table_name='conversation_participants')
    op.drop_index('idx_conversation_participants_conv', table_name='conversation_participants')
    
    # Drop conversation_participants table
    op.drop_table('conversation_participants')
    
    # Remove group chat fields from conversations table
    op.drop_column('conversations', 'participant_count')
    op.drop_column('conversations', 'is_group_chat')
    op.drop_column('conversations', 'group_name')
