"""Add source to evidence for Wikipedia/Wikidata labeling.

Revision ID: 0011_add_evidence_source
Revises: 0010_add_evidence_is_external
Create Date: 2026-02-28

"""
from alembic import op
import sqlalchemy as sa


revision = "0011_add_evidence_source"
down_revision = "0010_add_evidence_is_external"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "evidence",
        sa.Column("source", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("evidence", "source")
