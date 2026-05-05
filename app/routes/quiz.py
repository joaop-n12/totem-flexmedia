"""Quiz/Curiosidades — modulo gamificado para visitantes.

Rotas publicas (totem):
  GET  /<slug>/quiz              — tela de entrada + perguntas embebidas (JSON)
  POST /<slug>/api/quiz/answer   — registra resposta no InteractionLog

Trello: Modulo 2 - Quiz [Baixa] criterios 3.1 a 3.8.

Decisao de arquitetura:
  As perguntas sao embebidas no HTML como JSON (via tag <script>) em vez de
  serem buscadas via fetch separado. Atende o criterio 3.8 ("telas devem
  carregar em menos de 2 segundos") sem segundo round-trip de rede no Pi 3
  com 4G. O state-machine vive no client; o servidor so valida respostas
  e registra metricas.
"""
import json
import logging
import random

from flask import Blueprint, abort, jsonify, render_template, request

from app.extensions import db, limiter
from app.helpers import load_institution, require_module
from app.models import InteractionLog, QuizQuestion

logger = logging.getLogger(__name__)

quiz_bp = Blueprint("quiz", __name__)


# Quantidade maxima de perguntas por sessao — evita visitante "preso" e
# garante que a tela nao fique pesada com banco de 100 perguntas.
DEFAULT_BATCH = 5
MAX_BATCH = 10


@quiz_bp.route("/<slug>/quiz", methods=["GET"])
def quiz_page(slug):
    """Tela do quiz. Pre-carrega ate DEFAULT_BATCH perguntas aleatorias."""
    inst = load_institution(slug)
    if not inst.has_module("quiz"):
        abort(404)

    questions = (
        QuizQuestion.query
        .filter_by(institution_id=inst.id, active=True)
        .all()
    )
    # Filtra perguntas mal formadas (defesa em profundidade — nao deveria
    # acontecer, pois validamos no admin, mas dados antigos podem violar).
    valid = [q for q in questions if q.is_valid()]
    random.shuffle(valid)
    batch = valid[:DEFAULT_BATCH]

    # Apenas dados publicos vao para o totem (sem correct_index nem curiosity).
    public_payload = [q.to_public_dict() for q in batch]

    return render_template(
        "modules/quiz/quiz.html",
        institution=inst,
        questions_json=json.dumps(public_payload, ensure_ascii=False),
        total_questions=len(batch),
    )


@quiz_bp.route("/<slug>/api/quiz/answer", methods=["POST"])
@limiter.limit("60 per minute")
def quiz_answer(slug):
    """Recebe uma resposta, valida e devolve correto/errado + curiosidade.

    O totem NAO conhece o gabarito — quem responde manda apenas
    {question_id, choice_index}. O servidor consulta o gabarito, registra
    no InteractionLog (alimenta as metricas de uso) e devolve o resultado
    + curiosidade para a tela de feedback.
    """
    inst = load_institution(slug)
    if not inst.has_module("quiz"):
        abort(404)

    data = request.get_json(silent=True) or {}
    qid = data.get("question_id")
    choice = data.get("choice_index")

    if not isinstance(qid, int) or not isinstance(choice, int):
        return jsonify(error="invalid_payload"), 400

    # Filtro tenant — pergunta tem que pertencer A instituicao do slug,
    # senao um visitante poderia "responder" perguntas de outro cliente.
    q = QuizQuestion.query.filter_by(
        id=qid, institution_id=inst.id, active=True,
    ).first()
    if not q:
        return jsonify(error="not_found"), 404

    correct = (choice == q.correct_index)

    # Loga no InteractionLog para alimentar dashboard de metricas. O
    # `input_type` segue o padrao "<canal>" — usar "quiz:correct" /
    # "quiz:incorrect" permite reuso direto pelas agregacoes existentes.
    db.session.add(InteractionLog(
        institution_id=inst.id,
        input_text=q.question[:1000],
        input_type=f"quiz:{'correct' if correct else 'incorrect'}",
        response_text=(q.options[choice] if 0 <= choice < len(q.options) else ""),
    ))
    db.session.commit()

    return jsonify({
        "correct": correct,
        "correct_index": q.correct_index,
        "curiosity": q.curiosity or "",
    })
