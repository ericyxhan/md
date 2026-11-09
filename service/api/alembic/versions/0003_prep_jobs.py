"""prep jobs

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-08 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'prep_jobs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('owner_id', sa.String(length=64), nullable=False),
        sa.Column('type', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=24), nullable=False),
        sa.Column('request_json', sa.Text(), nullable=False),
        sa.Column('result_json', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('output_file_ids', sa.Text(), nullable=True),
        sa.Column('created_at', sa.String(length=32), nullable=False),
        sa.Column('updated_at', sa.String(length=32), nullable=False),
        sa.Column('completed_at', sa.String(length=32), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('prep_jobs', schema=None) as batch_op:
        batch_op.create_index(
            'ix_prep_jobs_owner_created_at',
            ['owner_id', 'created_at'],
            unique=False,
        )
        batch_op.create_index(
            'ix_prep_jobs_status',
            ['status'],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table('prep_jobs', schema=None) as batch_op:
        batch_op.drop_index('ix_prep_jobs_status')
        batch_op.drop_index('ix_prep_jobs_owner_created_at')

    op.drop_table('prep_jobs')
