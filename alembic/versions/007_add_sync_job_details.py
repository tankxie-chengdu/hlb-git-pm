"""add detailed command output to sync jobs

Revision ID: 007
Revises: 006
Create Date: 2026-07-21
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("sync_jobs", sa.Column("details_json", sa.Text(), nullable=False, server_default="{}"))


def downgrade() -> None:
    op.drop_column("sync_jobs", "details_json")
