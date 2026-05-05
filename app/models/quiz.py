"""QuizQuestion — perguntas com curiosidades por instituicao.

Atende o backlog Trello (Modulo 2 - Quiz [Baixa]):
  3.1 "Quer testar seu conhecimento?"
  3.3 Quiz com multiplas alternativas.
  3.5 Feedback visual.
  3.6 Curiosidades relacionadas ao tema.

Modelagem:
  - `options_json` armazena as alternativas como JSON serializado (lista
    de strings). SQLite/Postgres concordam em TEXT, sem tipo `JSON`
    proprietario. A property `options` cuida da (de)serializacao.
  - `correct_index` aponta para a alternativa correta (0-based).
  - `curiosity` e' um trecho explicativo opcional mostrado apos a resposta
    — atende o item 3.6 do backlog.
  - `active` permite ocultar perguntas sem deletar — util quando o tema
    do quiz vai ser revisado pelo curador.
"""
import json
from datetime import datetime

from app.extensions import db


# Limites de seguranca para evitar payloads gigantes.
MAX_OPTIONS = 6
MIN_OPTIONS = 2
MAX_OPTION_LEN = 120
MAX_QUESTION_LEN = 300
MAX_CURIOSITY_LEN = 600


class QuizQuestion(db.Model):
    __tablename__ = "quiz_questions"
    __table_args__ = (
        db.Index("ix_quiz_institution", "institution_id"),
    )

    id             = db.Column(db.Integer, primary_key=True)
    institution_id = db.Column(
        db.Integer,
        db.ForeignKey("institutions.id", ondelete="CASCADE"),
        nullable=False,
    )
    question       = db.Column(db.String(MAX_QUESTION_LEN), nullable=False)
    options_json   = db.Column(db.Text, nullable=False)
    correct_index  = db.Column(db.Integer, nullable=False, default=0)
    curiosity      = db.Column(db.String(MAX_CURIOSITY_LEN), nullable=True)
    category       = db.Column(db.String(60), nullable=True)
    order          = db.Column(db.Integer, nullable=False, default=0)
    active         = db.Column(db.Boolean, nullable=False, default=True)
    created_at     = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    institution    = db.relationship(
        "Institution",
        backref=db.backref("quiz_questions", lazy="dynamic", cascade="all, delete-orphan"),
    )

    # ── (De)serializacao das opcoes ────────────────────────────────────────

    @property
    def options(self) -> list[str]:
        if not self.options_json:
            return []
        try:
            data = json.loads(self.options_json)
            return [str(x) for x in data] if isinstance(data, list) else []
        except (json.JSONDecodeError, TypeError):
            return []

    @options.setter
    def options(self, values: list[str]) -> None:
        # Normalizacao: corta strings vazias, limita tamanho de cada opcao,
        # e tambem o numero total de alternativas.
        cleaned = [str(v)[:MAX_OPTION_LEN] for v in (values or []) if str(v).strip()]
        cleaned = cleaned[:MAX_OPTIONS]
        self.options_json = json.dumps(cleaned, ensure_ascii=False)

    # ── Helpers ─────────────────────────────────────────────────────────────

    def is_valid(self) -> bool:
        opts = self.options
        return (
            bool(self.question and self.question.strip()) and
            MIN_OPTIONS <= len(opts) <= MAX_OPTIONS and
            0 <= self.correct_index < len(opts)
        )

    def to_public_dict(self) -> dict:
        """Serializacao para o totem — NAO inclui correct_index nem curiosity.

        Quem responde nao deve receber a resposta certa no payload inicial.
        Apos o submit, o servidor compara e devolve o resultado.
        """
        return {
            "id": self.id,
            "question": self.question,
            "options": self.options,
            "category": self.category,
        }

    def __repr__(self):
        return f"<QuizQuestion {self.id}>"
