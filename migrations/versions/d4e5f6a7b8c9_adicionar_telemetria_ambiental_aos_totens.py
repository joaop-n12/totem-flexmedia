"""Adicionar telemetria ambiental aos totens.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8, b1c2d3e4f5a6
"""
from alembic import op
import sqlalchemy as sa


revision = "d4e5f6a7b8c9"
down_revision = ("c3d4e5f6a7b8", "b1c2d3e4f5a6")
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("totem_devices")}
    with op.batch_alter_table("totem_devices", schema=None) as batch_op:
        if "ambient_temp_c" not in columns:
            batch_op.add_column(sa.Column("ambient_temp_c", sa.Float(), nullable=True))
        if "ambient_humidity_pct" not in columns:
            batch_op.add_column(sa.Column("ambient_humidity_pct", sa.Float(), nullable=True))


def downgrade():
    with op.batch_alter_table("totem_devices", schema=None) as batch_op:
        batch_op.drop_column("ambient_humidity_pct")
        batch_op.drop_column("ambient_temp_c")
