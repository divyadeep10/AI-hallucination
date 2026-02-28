"""Create evidence table.

Revision ID: 0004_create_evidence_table
Revises: 0003_create_claims_table
Create Date: 2026-02-27

"""

from alembic import op
import sqlalchemy as sa


revision = "0004_create_evidence_table"
down_revision = "0003_create_claims_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("claim_id", sa.Integer(), nullable=False, index=True),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=False),
        sa.Column("retrieval_score", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(
            ["claim_id"],
            ["claims.id"],
            ondelete="CASCADE",
        ),
    )


def downgrade() -> None:
    op.drop_table("evidence")

