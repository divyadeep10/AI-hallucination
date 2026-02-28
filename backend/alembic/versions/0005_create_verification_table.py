"""Create verification table.

Revision ID: 0005_create_verification_table
Revises: 0004_create_evidence_table
Create Date: 2026-02-27

"""

from alembic import op
import sqlalchemy as sa


revision = "0005_create_verification_table"
down_revision = "0004_create_evidence_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "verification",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("claim_id", sa.Integer(), nullable=False, index=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("evidence_id", sa.Integer(), nullable=True, index=True),
        sa.ForeignKeyConstraint(
            ["claim_id"],
            ["claims.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evidence_id"],
            ["evidence.id"],
            ondelete="SET NULL",
        ),
    )


def downgrade() -> None:
    op.drop_table("verification")

