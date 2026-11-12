"""workflows

Revision ID: 0005
Down Revision: 0004
Create Date: 2026-11-11 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'workflows',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('owner_id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('source_file_id', sa.String(length=64), nullable=False),
        sa.Column('source_type', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.String(length=32), nullable=False),
        sa.Column('updated_at', sa.String(length=32), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_workflows_owner_created_at',
        'workflows',
        ['owner_id', 'created_at'],
        unique=False,
    )

    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('workflow_id', sa.String(length=36), nullable=True)
        )
        batch_op.create_foreign_key(
            'fk_jobs_workflow_id_workflows',
            'workflows',
            ['workflow_id'],
            ['id'],
            ondelete='SET NULL',
        )
        batch_op.create_index(
            'ix_jobs_workflow_id',
            ['workflow_id'],
            unique=False,
        )


def downgrade() -> None:
    with op.batch_alter_table('jobs', schema=None) as batch_op:
        batch_op.drop_index('ix_jobs_workflow_id')
        batch_op.drop_constraint(
            'fk_jobs_workflow_id_workflows', type_='foreignkey'
        )
        batch_op.drop_column('workflow_id')

    op.drop_index('ix_workflows_owner_created_at', table_name='workflows')
    op.drop_table('workflows')
