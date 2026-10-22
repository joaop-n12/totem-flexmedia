"""Add store coordinates and floor/category to map points.

Revision ID: e7f8a9b0c1d2
Revises: d4e5f6a7b8c9
Create Date: 2026-10-21
"""
from alembic import op
import sqlalchemy as sa


revision = "e7f8a9b0c1d2"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("stores") as batch_op:
        batch_op.add_column(sa.Column("unit_code", sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column("x_pos", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("y_pos", sa.Float(), nullable=True))
    with op.batch_alter_table("map_areas") as batch_op:
        batch_op.add_column(sa.Column("floor", sa.String(length=50), nullable=True))
        batch_op.add_column(sa.Column("category", sa.String(length=80), nullable=True))
    op.execute("UPDATE map_areas SET floor = 'Terreo', category = 'Servicos' WHERE floor IS NULL")


def downgrade():
    with op.batch_alter_table("map_areas") as batch_op:
        batch_op.drop_column("category")
        batch_op.drop_column("floor")
    with op.batch_alter_table("stores") as batch_op:
        batch_op.drop_column("y_pos")
        batch_op.drop_column("x_pos")
        batch_op.drop_column("unit_code")
