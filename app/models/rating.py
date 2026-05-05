"""ExperienceRating — avaliacao anonima da experiencia no totem.

Atende o backlog Trello (Modulo 4 - Avaliacao [Baixa]):
  10.1 / 4.1 — pergunta SIM/NAO ao final.
  10.2 / 4.2 — estrelas 1-5 + comentario.

LGPD:
  - Anonima por design — NAO armazenamos session_id, IP, cookie ou qualquer
    identificador. Quem cadastra um rating fica anonimo.
  - `comment` e' truncado em MAX_COMMENT_LEN para nao virar canal de
    armazenamento de dados pessoais por engano (visitante digitando "meu
    nome eh Joao" — logamos os 600 chars iniciais e descartamos o resto).
  - Retencao segue o mesmo `INTERACTION_LOG_RETENTION_DAYS` em principio,
    mas nao implementamos purga aqui (sao dados anonimos e estatisticos —
    util manter mais tempo). Se o cliente exigir purga, basta filtrar
    `ExperienceRating.created_at < cutoff` no `flask purge-logs` futuro.
"""
from datetime import datetime

from app.extensions import db


MIN_STARS = 1
MAX_STARS = 5
MAX_COMMENT_LEN = 600


class ExperienceRating(db.Model):
    __tablename__ = "experience_ratings"
    __table_args__ = (
        db.Index("ix_rating_institution", "institution_id"),
        db.Index("ix_rating_created_at", "created_at"),
    )

    id             = db.Column(db.Integer, primary_key=True)
    institution_id = db.Column(
        db.Integer,
        db.ForeignKey("institutions.id", ondelete="CASCADE"),
        nullable=False,
    )
    stars          = db.Column(db.Integer, nullable=False)
    comment        = db.Column(db.String(MAX_COMMENT_LEN), nullable=True)
    created_at     = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    institution    = db.relationship(
        "Institution",
        backref=db.backref("ratings", lazy="dynamic", cascade="all, delete-orphan"),
    )

    @staticmethod
    def is_valid_stars(value) -> bool:
        try:
            n = int(value)
        except (TypeError, ValueError):
            return False
        return MIN_STARS <= n <= MAX_STARS

    def __repr__(self):
        return f"<ExperienceRating {self.id} stars={self.stars}>"
