"""add snapshot reference to report history

Revision ID: 006
Revises: 005
Create Date: 2026-07-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("report_history")}
    if "selection_snapshot_id" not in columns:
        op.add_column("report_history", sa.Column("selection_snapshot_id", sa.Integer, nullable=True))
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("report_history")}
    if "ix_report_history_selection_snapshot_id" not in indexes:
        op.create_index("ix_report_history_selection_snapshot_id", "report_history", ["selection_snapshot_id"])


def downgrade() -> None:
    op.drop_index("ix_report_history_selection_snapshot_id", table_name="report_history")
    op.drop_column("report_history", "selection_snapshot_id")
