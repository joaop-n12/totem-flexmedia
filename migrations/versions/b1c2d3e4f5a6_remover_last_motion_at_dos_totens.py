"""Remover last_motion_at dos totens (exclusao do PIR)

Revision ID: b1c2d3e4f5a6
Revises: 0483dd3c15b9
Create Date: 2026-05-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b1c2d3e4f5a6'
down_revision = '0483dd3c15b9'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("totem_devices")}

    if "last_motion_at" in columns:
        with op.batch_alter_table('totem_devices', schema=None) as batch_op:
            batch_op.drop_column('last_motion_at')


def downgrade():
    with op.batch_alter_table('totem_devices', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_motion_at', sa.DateTime(), nullable=True))
