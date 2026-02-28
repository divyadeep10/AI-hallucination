"""Add is_external to evidence for external retrieval layer.

Revision ID: 0010_add_evidence_is_external
Revises: 0009_add_created_at
Create Date: 2026-02-28

"""
from alembic import op
import sqlalchemy as sa


revision = "0010_add_evidence_is_external"
down_revision = "0009_add_created_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "evidence",
        sa.Column("is_external", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("evidence", "is_external")
