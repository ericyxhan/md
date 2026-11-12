"""activity feed indexes

Revision ID: 0008
Down Revision: 0007
Create Date: 2026-11-11 00:00:00.000000

The account-wide activity feed reads the newest events across ``job_events``
and ``prep_events``.  ``prep_events`` already had an index on ``created_at``;
``job_events`` did not, so the feed sorted the entire event history before
returning the first page.  This adds the matching index and declares the
``jobs.workflow_id`` index in the model so the metadata matches the schema.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0008'
down_revision: Union[str, None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'ix_job_events_created_at',
        'job_events',
        ['created_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_job_events_created_at', table_name='job_events')
