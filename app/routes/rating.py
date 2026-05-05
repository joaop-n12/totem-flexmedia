"""Avaliacao de experiencia — anonima, ao final do uso do totem.

Rotas publicas:
  GET  /<slug>/rating             — pagina SPA (intro → form → obrigado).
  POST /<slug>/api/rating          — submete {stars, comment}.

Trello: Modulo 4 - Avaliacao [Baixa] criterios 4.1 / 4.2 / 10.1 / 10.2.

Hardening:
  - Rate-limit por IP (totem nao logado): 5 ratings por minuto e' o suficiente
    para qualquer fluxo legitimo e corta abuso (cliente bot enviando spam).
  - Estrelas validadas server-side (1-5 inteiro); comentario truncado.
  - Sem identificacao do visitante — anonimo por design (LGPD).
  - Modulo precisa estar habilitado para a rota responder.
"""
import logging

from flask import Blueprint, abort, jsonify, render_template, request

from app.extensions import db, limiter
from app.helpers import load_institution
from app.models import ExperienceRating
from app.models.rating import MAX_COMMENT_LEN

logger = logging.getLogger(__name__)

rating_bp = Blueprint("rating", __name__)


@rating_bp.route("/<slug>/rating", methods=["GET"])
def rating_page(slug):
    inst = load_institution(slug)
    if not inst.has_module("avaliacao"):
        abort(404)
    return render_template("modules/rating/rating.html", institution=inst)


@rating_bp.route("/<slug>/api/rating", methods=["POST"])
@limiter.limit("5 per minute; 30 per hour")
def submit_rating(slug):
    inst = load_institution(slug)
    if not inst.has_module("avaliacao"):
        abort(404)

    data = request.get_json(silent=True) or {}
    stars = data.get("stars")

    if not ExperienceRating.is_valid_stars(stars):
        return jsonify(error="invalid_stars",
                       message="Avalie de 1 a 5 estrelas."), 400

    comment = (data.get("comment") or "").strip()
    if len(comment) > MAX_COMMENT_LEN:
        # Trunca silenciosamente — visitante nao precisa ver erro.
        comment = comment[:MAX_COMMENT_LEN]

    rating = ExperienceRating(
        institution_id=inst.id,
        stars=int(stars),
        comment=comment or None,
    )
    db.session.add(rating)
    db.session.commit()

    return jsonify(ok=True, message="Obrigado pela avaliação!")
