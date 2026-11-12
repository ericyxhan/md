"""prep job events

Revision ID: 0007
Down Revision: 0006
Create Date: 2026-11-11 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0007'
down_revision: Union[str, None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'prep_events',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('prep_job_id', sa.String(length=36), nullable=False),
        sa.Column('type', sa.String(length=64), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('data_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(
            ['prep_job_id'],
            ['prep_jobs.id'],
            ondelete='CASCADE',
        ),
    )
    op.create_index(
        'ix_prep_events_prep_job_id_id',
        'prep_events',
        ['prep_job_id', 'id'],
        unique=False,
    )
    op.create_index(
        'ix_prep_events_created_at',
        'prep_events',
        ['created_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_prep_events_created_at', table_name='prep_events')
    op.drop_index('ix_prep_events_prep_job_id_id', table_name='prep_events')
    op.drop_table('prep_events')
