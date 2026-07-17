"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-07-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("username", sa.String, unique=True, nullable=False),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("display_name", sa.String, nullable=True, server_default=""),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
    )
    op.create_index("ix_users_username", "users", ["username"])

    op.create_table(
        "members",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("git_email", sa.String, nullable=False, server_default=""),
        sa.Column("git_name", sa.String, nullable=False, server_default=""),
        sa.Column("real_name", sa.String, nullable=False, server_default=""),
        sa.Column("department", sa.String, nullable=False, server_default=""),
    )
    op.create_index("ix_members_git_email", "members", ["git_email"])

    op.create_table(
        "recipients",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("email", sa.String, unique=True, nullable=False),
        sa.Column("name", sa.String, nullable=False, server_default=""),
        sa.Column("receive_daily", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("receive_weekly", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("receive_monthly", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
    )
    op.create_index("ix_recipients_email", "recipients", ["email"])

    op.create_table(
        "schedules",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("report_type", sa.String, nullable=False, server_default="daily"),
        sa.Column("run_time", sa.String, nullable=False, server_default="18:30"),
        sa.Column("day_of_week", sa.Integer, nullable=True),
        sa.Column("day_of_month", sa.Integer, nullable=True),
        sa.Column("timezone", sa.String, nullable=False, server_default="Asia/Shanghai"),
        sa.Column("is_enabled", sa.Boolean, nullable=False, server_default=sa.text("1")),
    )

    op.create_table(
        "report_history",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("report_type", sa.String, nullable=False, server_default="daily"),
        sa.Column("period_start", sa.String, nullable=False),
        sa.Column("period_end", sa.String, nullable=False),
        sa.Column("title", sa.String, nullable=False, server_default=""),
        sa.Column("markdown", sa.Text, nullable=False, server_default=""),
        sa.Column("html", sa.Text, nullable=False, server_default=""),
        sa.Column("ai_analysis", sa.Text, nullable=False, server_default=""),
        sa.Column("total_commits", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("status", sa.String, nullable=False, server_default="running"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("email_sent_at", sa.String, nullable=True),
        sa.Column("created_at", sa.String, nullable=False),
    )


def downgrade() -> None:
    op.drop_table("report_history")
    op.drop_table("schedules")
    op.drop_table("recipients")
    op.drop_table("members")
    op.drop_table("users")
