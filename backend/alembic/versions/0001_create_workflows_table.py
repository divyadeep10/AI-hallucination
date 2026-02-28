"""Create workflows table.

Revision ID: 0001_create_workflows_table
Revises: 
Create Date: 2026-02-27
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_create_workflows_table"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workflows",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("user_query", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("workflows")

