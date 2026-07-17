"""add report workflow steps

Revision ID: 003
Revises: 002
Create Date: 2026-07-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "report_steps",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer, nullable=False),
        sa.Column("step_key", sa.String, nullable=False),
        sa.Column("step_name", sa.String, nullable=False, server_default=""),
        sa.Column("sequence", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String, nullable=False, server_default="pending"),
        sa.Column("progress", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("input_summary", sa.Text, nullable=False, server_default="{}"),
        sa.Column("output_summary", sa.Text, nullable=False, server_default="{}"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("started_at", sa.String, nullable=True),
        sa.Column("finished_at", sa.String, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
    )
    op.create_index("ix_report_steps_run_id", "report_steps", ["run_id"])


def downgrade() -> None:
    op.drop_table("report_steps")

