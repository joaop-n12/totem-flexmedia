"""Create quiz questions table.

Revision ID: f9a0b1c2d3e4
Revises: e7f8a9b0c1d2
Create Date: 2026-10-22
"""
from alembic import op
import sqlalchemy as sa


revision = "f9a0b1c2d3e4"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "quiz_questions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("institution_id", sa.Integer(), nullable=False),
        sa.Column("question", sa.String(length=300), nullable=False),
        sa.Column("options_json", sa.Text(), nullable=False),
        sa.Column("correct_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("curiosity", sa.String(length=600), nullable=True),
        sa.Column("category", sa.String(length=60), nullable=True),
        sa.Column("order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_quiz_institution", "quiz_questions", ["institution_id"])


def downgrade():
    op.drop_index("ix_quiz_institution", table_name="quiz_questions")
    op.drop_table("quiz_questions")
