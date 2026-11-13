"""users

Creates the accounts table and turns the old shared ``local`` owner into a
real administrator account.  Every row that used to belong to the shared lab
owner is moved to that account, so the existing jobs, uploads, and prep jobs
stay reachable after the upgrade.

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-12 00:00:00.000000

"""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0009'
down_revision: Union[str, None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# The administrator keeps this id forever.  It is stable across upgrades, so
# the owner_id written here never has to be rewritten again.
ADMIN_USER_ID = '00000000-0000-4000-8000-000000000001'

LEGACY_OWNER_ID = 'local'

_OWNER_TABLES = ('jobs', 'files', 'prep_jobs', 'workflows', 'audit_events')


def _env(*names: str, default: str = '') -> str:
    for name in names:
        value = os.environ.get(name, '')
        if value:
            return value
    return default


def _admin_password_hash() -> str:
    """Return the hash to store for the administrator account.

    ``ADMIN_PASSWORD_HASH`` wins; otherwise the pre-accounts lab password is
    used, so the sign-in that works today keeps working.  The plaintext
    variant is hashed here, once, and never written to disk again.
    """

    stored = _env('ADMIN_PASSWORD_HASH', 'WEB_PASSWORD_HASH')
    if stored:
        return stored

    plaintext = _env('WEB_PASSWORD')
    if not plaintext:
        return ''

    from app.passwords import hash_password

    return hash_password(plaintext)


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('first_name', sa.String(length=100), nullable=False),
        sa.Column('last_name', sa.String(length=100), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('is_admin', sa.Boolean(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.String(length=32), nullable=False),
        sa.Column('updated_at', sa.String(length=32), nullable=False),
        sa.Column('last_login_at', sa.String(length=32), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email', name='uq_users_email'),
    )
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.create_index('ix_users_is_active', ['is_active'], unique=False)

    now = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    op.execute(
        sa.text(
            'INSERT INTO users (id, email, first_name, last_name, '
            'password_hash, is_admin, is_active, created_at, updated_at, '
            'last_login_at) VALUES (:id, :email, :first_name, :last_name, '
            ':password_hash, 1, 1, :now, :now, NULL)'
        ).bindparams(
            id=ADMIN_USER_ID,
            email=_env('ADMIN_EMAIL', default='admin@lattice.local').strip().lower(),
            first_name=_env('ADMIN_FIRST_NAME', default='Lab'),
            last_name=_env('ADMIN_LAST_NAME', default='Administrator'),
            password_hash=_admin_password_hash(),
            now=now,
        )
    )

    # Everything that belonged to the shared lab owner now belongs to the
    # administrator account.
    for table in _OWNER_TABLES:
        op.execute(
            sa.text(
                f'UPDATE {table} SET owner_id = :owner WHERE owner_id = :legacy'
            ).bindparams(owner=ADMIN_USER_ID, legacy=LEGACY_OWNER_ID)
        )


def downgrade() -> None:
    for table in _OWNER_TABLES:
        op.execute(
            sa.text(
                f'UPDATE {table} SET owner_id = :legacy WHERE owner_id = :owner'
            ).bindparams(owner=ADMIN_USER_ID, legacy=LEGACY_OWNER_ID)
        )

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index('ix_users_is_active')

    op.drop_table('users')
