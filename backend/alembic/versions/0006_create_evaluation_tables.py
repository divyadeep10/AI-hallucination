"""Create evaluation_runs and evaluation_samples tables (Phase 8).

Revision ID: 0006_create_evaluation_tables
Revises: 0005_create_verification_table
Create Date: 2026-02-27

"""

from alembic import op
import sqlalchemy as sa


revision = "0006_create_evaluation_tables"
down_revision = "0005_create_verification_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evaluation_runs",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("mode", sa.String(length=50), nullable=False),
        sa.Column("dataset_path", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="running"),
        sa.Column("summary_metrics", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_table(
        "evaluation_samples",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("evaluation_run_id", sa.Integer(), nullable=False, index=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("workflow_id_baseline", sa.Integer(), nullable=True),
        sa.Column("workflow_id_system", sa.Integer(), nullable=True),
        sa.Column("baseline_answer", sa.Text(), nullable=True),
        sa.Column("system_answer", sa.Text(), nullable=True),
        sa.Column("baseline_status", sa.String(length=50), nullable=True),
        sa.Column("system_status", sa.String(length=50), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["evaluation_run_id"],
            ["evaluation_runs.id"],
            ondelete="CASCADE",
        ),
    )


def downgrade() -> None:
    op.drop_table("evaluation_samples")
    op.drop_table("evaluation_runs")
