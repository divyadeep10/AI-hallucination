"""Add created_at to claims, evidence, verification for timeline timestamps.

Revision ID: 0009_add_created_at
Revises: 0008_create_knowledge_chunks
Create Date: 2026-02-28

"""
from alembic import op
import sqlalchemy as sa


revision = "0009_add_created_at"
down_revision = "0008_create_knowledge_chunks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("claims", sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()))
    op.add_column("evidence", sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()))
    op.add_column("verification", sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()))


def downgrade() -> None:
    op.drop_column("verification", "created_at")
    op.drop_column("evidence", "created_at")
    op.drop_column("claims", "created_at")
