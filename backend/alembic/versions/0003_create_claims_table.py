"""Create claims table.

Revision ID: 0003_create_claims_table
Revises: 0002_create_responses_table
Create Date: 2026-02-27

"""

from alembic import op
import sqlalchemy as sa


revision = "0003_create_claims_table"
down_revision = "0002_create_responses_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "claims",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("response_id", sa.Integer(), nullable=False, index=True),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("entities", sa.JSON(), nullable=False),
        sa.Column("extraction_confidence", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(
            ["response_id"],
            ["responses.id"],
            ondelete="CASCADE",
        ),
    )


def downgrade() -> None:
    op.drop_table("claims")
