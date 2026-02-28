"""Add error_message column to workflows table

Revision ID: 0007_add_workflow_error_message
Revises: 0006_create_evaluation_tables
Create Date: 2026-02-28 06:33:21

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0007_add_workflow_error_message"
down_revision = "0006_create_evaluation_tables"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('workflows', sa.Column('error_message', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('workflows', 'error_message')
