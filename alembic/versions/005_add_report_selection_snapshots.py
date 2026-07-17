"""add report selection snapshots

Revision ID: 005
Revises: 004
Create Date: 2026-07-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "report_selection_snapshots",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("report_type", sa.String, nullable=False),
        sa.Column("period_start", sa.String, nullable=False),
        sa.Column("period_end", sa.String, nullable=False),
        sa.Column("repositories_json", sa.Text, nullable=False, server_default="[]"),
        sa.Column("created_at", sa.String, nullable=False),
    )
    op.create_index("ix_report_selection_snapshots_report_type", "report_selection_snapshots", ["report_type"])


def downgrade() -> None:
    op.drop_table("report_selection_snapshots")
