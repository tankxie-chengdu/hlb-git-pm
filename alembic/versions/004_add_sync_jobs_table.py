"""add sync_jobs table for tracking sync status

Revision ID: 004
Revises: 003
Create Date: 2026-07-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sync_jobs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("repo_name", sa.String, nullable=False, unique=True),
        sa.Column("status", sa.String, nullable=False, server_default="queued"),
        sa.Column("error", sa.String, nullable=False, server_default=""),
        sa.Column("started_at", sa.String, nullable=False, server_default=""),
        sa.Column("finished_at", sa.String, nullable=False, server_default=""),
    )
    op.create_index("ix_sync_jobs_repo_name", "sync_jobs", ["repo_name"], unique=True)


def downgrade() -> None:
    op.drop_table("sync_jobs")
