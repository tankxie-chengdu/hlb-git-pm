"""add repositories table

Revision ID: 002
Revises: 001
Create Date: 2026-07-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "repositories",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("org_name", sa.String, nullable=False, server_default=""),
        sa.Column("full_name", sa.String, nullable=False),
        sa.Column("description", sa.String, nullable=False, server_default=""),
        sa.Column("language", sa.String, nullable=False, server_default=""),
        sa.Column("default_branch", sa.String, nullable=False, server_default="main"),
        sa.Column("pushed_at", sa.String, nullable=False, server_default=""),
        sa.Column("stars", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("is_archived", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("is_fork", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("clone_url", sa.String, nullable=False, server_default=""),
        sa.Column("is_cloned", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("branch_count", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("total_commits", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("synced_at", sa.String, nullable=False, server_default=""),
        sa.Column("meta_updated_at", sa.String, nullable=False, server_default=""),
    )
    op.create_index("ix_repositories_org_name", "repositories", ["org_name"])
    op.create_index("ix_repositories_full_name", "repositories", ["full_name"], unique=True)


def downgrade() -> None:
    op.drop_table("repositories")
