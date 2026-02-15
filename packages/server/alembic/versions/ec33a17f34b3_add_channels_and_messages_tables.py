"""Add channels and messages tables

Revision ID: ec33a17f34b3
Revises: 
Create Date: 2026-02-15 11:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import sqlmodel

# revision identifiers, used by Alembic.
revision: str = 'ec33a17f34b3'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Channels
    op.create_table('channels',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('type', sa.Enum('ORG_WIDE', 'PROJECT', name='channeltype'), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_channels_id'), 'channels', ['id'], unique=False)
    op.create_index(op.f('ix_channels_org_id'), 'channels', ['org_id'], unique=False)
    op.create_index(op.f('ix_channels_project_id'), 'channels', ['project_id'], unique=False)
    op.create_foreign_key(None, 'channels', 'organizations', ['org_id'], ['id'])
    op.create_foreign_key(None, 'channels', 'projects', ['project_id'], ['id'])

    # Messages (Partitioned)
    op.create_table('messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('channel_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('sender_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('content', sa.String(), nullable=False),
        sa.Column('mentions', postgresql.ARRAY(postgresql.UUID(as_uuid=True)), server_default='{}', nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', 'created_at'),
        postgresql_partition_by='RANGE (created_at)'
    )
    # We cannot create standard indexes on partitioned tables easily in older PG versions, 
    # but in PG 11+ we can. Alembic supports this.
    
    # However, create_index might fail if partitions don't exist yet? 
    # No, indexes on partitioned tables are supported.
    
    op.create_index(op.f('ix_messages_id'), 'messages', ['id'], unique=False)
    op.create_index(op.f('ix_messages_org_id'), 'messages', ['org_id'], unique=False)
    op.create_index(op.f('ix_messages_channel_id'), 'messages', ['channel_id'], unique=False)
    op.create_index(op.f('ix_messages_sender_id'), 'messages', ['sender_id'], unique=False)
    op.create_index(op.f('ix_messages_created_at'), 'messages', ['created_at'], unique=False)

    # Note: Foreign keys on partitioned tables are supported in PG 12+, but references TO partitioned tables are tricky.
    # References FROM partitioned tables are fine.
    # We reference organizations, channels, users which are regular tables.
    
    # IMPORTANT: Alembic/SQLAlchemy might not emit foreign keys for partitioned tables correctly in all versions.
    # We'll try adding them.
    # op.create_foreign_key(None, 'messages', 'organizations', ['org_id'], ['id'])
    # op.create_foreign_key(None, 'messages', 'channels', ['channel_id'], ['id'])
    # op.create_foreign_key(None, 'messages', 'users', ['sender_id'], ['id'])

    # Create initial partition for current month and next month
    # This should ideally be handled by pg_partman, but for POC we create a default or specific partition.
    op.execute("""
        CREATE TABLE messages_default PARTITION OF messages DEFAULT;
    """)


def downgrade() -> None:
    op.drop_table('messages')
    op.drop_index(op.f('ix_channels_project_id'), table_name='channels')
    op.drop_index(op.f('ix_channels_org_id'), table_name='channels')
    op.drop_index(op.f('ix_channels_id'), table_name='channels')
    op.drop_table('channels')
    sa.Enum(name='channeltype').drop(op.get_bind())
