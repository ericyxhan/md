"""prep job progress message

Revision ID: 0006
Down Revision: 0005
Create Date: 2026-11-11 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('prep_jobs', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('progress_message', sa.String(length=1000), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table('prep_jobs', schema=None) as batch_op:
        batch_op.drop_column('progress_message')
