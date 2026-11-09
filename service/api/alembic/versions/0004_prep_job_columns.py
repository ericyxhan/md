"""prep job columns

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-08 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0004'
down_revision: Union[str, None] = '0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('prep_jobs', schema=None) as batch_op:
        batch_op.add_column(sa.Column('run_token', sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column('cancel_requested', sa.Boolean(), nullable=False, server_default=sa.false()))
        batch_op.add_column(sa.Column('phase', sa.String(length=24), nullable=True))
        batch_op.add_column(sa.Column('progress_percent', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('progress_updated_at', sa.String(length=32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('prep_jobs', schema=None) as batch_op:
        batch_op.drop_column('progress_updated_at')
        batch_op.drop_column('progress_percent')
        batch_op.drop_column('phase')
        batch_op.drop_column('cancel_requested')
        batch_op.drop_column('run_token')
