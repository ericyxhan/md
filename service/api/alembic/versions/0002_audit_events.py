"""audit events

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-07 20:15:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'audit_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('request_id', sa.String(length=64), nullable=True),
        sa.Column('owner_id', sa.String(length=64), nullable=True),
        sa.Column('action', sa.String(length=64), nullable=False),
        sa.Column('outcome', sa.String(length=24), nullable=False),
        sa.Column('target_type', sa.String(length=32), nullable=True),
        sa.Column('target_id', sa.String(length=64), nullable=True),
        sa.Column('details_json', sa.Text(), nullable=True),
        sa.Column('remote_addr', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('audit_events', schema=None) as batch_op:
        batch_op.create_index(
            'ix_audit_events_action_created_at',
            ['action', 'created_at'],
            unique=False,
        )
        batch_op.create_index(
            'ix_audit_events_created_at',
            ['created_at'],
            unique=False,
        )
        batch_op.create_index(
            'ix_audit_events_owner_created_at',
            ['owner_id', 'created_at'],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table('audit_events', schema=None) as batch_op:
        batch_op.drop_index('ix_audit_events_owner_created_at')
        batch_op.drop_index('ix_audit_events_created_at')
        batch_op.drop_index('ix_audit_events_action_created_at')

    op.drop_table('audit_events')
