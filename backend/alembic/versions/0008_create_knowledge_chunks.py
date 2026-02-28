"""Create knowledge_chunks table (Phase retrieval upgrade).

Stores embeddings as JSONB so retrieval works without the pgvector extension.
Similarity search is done in Python over loaded chunks.

Revision ID: 0008_create_knowledge_chunks
Revises: 0007_add_workflow_error_message
Create Date: 2026-02-28

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "0008_create_knowledge_chunks"
down_revision = "0007_add_workflow_error_message"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    # Idempotent: skip if table already exists (e.g. from a previous partial run)
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'knowledge_chunks'"
    ))
    if result.scalar() is None:
        op.create_table(
            "knowledge_chunks",
            sa.Column("id", sa.Integer(), primary_key=True, index=True),
            sa.Column("text", sa.Text(), nullable=False),
            sa.Column("source", sa.String(length=512), nullable=True, index=True),
            sa.Column("embedding", JSONB, nullable=False),
        )


def downgrade() -> None:
    op.drop_table("knowledge_chunks")

