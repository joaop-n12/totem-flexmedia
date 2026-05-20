"""Adicionar public_url às instituições

Revision ID: c3d4e5f6a7b8
Revises: b1c2d3e4f5a6
Create Date: 2026-05-19 00:00:00.000000

URL HTTPS publica do totem (Cloudflare Tunnel) — usada pelo link "Ver Totem"
no painel admin. Necessaria para liberar microfone fora de localhost (Secure
Origin). Veja Institution.effective_public_url() para resolucao + fallback
no env TOTEM_PUBLIC_URL.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c3d4e5f6a7b8'
down_revision = 'b1c2d3e4f5a6'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('institutions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('public_url', sa.String(length=255), nullable=True))


def downgrade():
    with op.batch_alter_table('institutions', schema=None) as batch_op:
        batch_op.drop_column('public_url')
