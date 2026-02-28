"""Create responses table.

Revision ID: 0002_create_responses_table
Revises: 0001_create_workflows_table
Create Date: 2026-02-27
"""

from alembic import op
import sqlalchemy as sa


revision = "0002_create_responses_table"
down_revision = "0001_create_workflows_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "responses",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("workflow_id", sa.Integer(), nullable=False, index=True),
        sa.Column("agent_type", sa.String(length=50), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=False),
        sa.Column("model_used", sa.String(length=100), nullable=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["workflow_id"],
            ["workflows.id"],
            ondelete="CASCADE",
        ),
    )


def downgrade() -> None:
    op.drop_table("responses")

