"""Rota publica de traducao consumida pelo totem (visitantes estrangeiros).

Endpoint:
  POST /<slug>/api/translate
    Body JSON: {"text": "...", "target": "en", "source": "auto"}
    Resposta: {"translation": "...", "cached": true|false, "target": "en"}

Por que sob `/<slug>/`?
  - Reusa o gate de quota diaria por instituicao (ai_quota_exceeded).
  - Reusa o limiter por IP.
  - InteractionLog registra a traducao ligada ao tenant correto, alimentando
    o futuro dashboard de "idiomas mais usados".

Hardening:
  - Rate-limit 30/min por IP (10x mais permissivo que voz porque traducao
    e' barata; ainda assim corta abuso).
  - Quota da instituicao continua valendo — uma frase traduzida conta como
    1 chamada de IA.
  - Texto truncado a MAX_TEXT_LEN no servico (defesa em profundidade).
  - Mensagens de erro NUNCA vazam stack trace ou config interna.
"""
import logging

from flask import Blueprint, jsonify, request

from app.extensions import db, limiter
from app.helpers import load_institution
from app.models import InteractionLog
from app.services import registry
from app.services.translation import (
    MSG_GENERIC, SUPPORTED_LANGUAGES, TranslationError, TranslationIntegration,
)

logger = logging.getLogger(__name__)

translate_bp = Blueprint("translate", __name__)


# ── Rota visitante ────────────────────────────────────────────────────────────

@translate_bp.route("/<slug>/api/translate", methods=["POST"])
@limiter.limit("30 per minute; 200 per hour")
def translate_api(slug):
    inst = load_institution(slug)
    if inst.ai_quota_exceeded():
        return jsonify({"error": "quota",
                        "message": "Limite diário de IA atingido."}), 429

    integration = registry.get("translation")
    if not isinstance(integration, TranslationIntegration):
        return jsonify({"error": "unavailable",
                        "message": "Tradução não está habilitada nesta instalação."}), 503

    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    target = (data.get("target") or "en").lower()
    source = (data.get("source") or "auto").lower()

    if not text:
        return jsonify({"error": "invalid", "message": "Texto vazio."}), 400

    try:
        result = integration.translate(text=text, target=target, source=source)
    except TranslationError as exc:
        # Rate-limit e offline → 429/503; auth → 503 (admin-side); invalid → 400.
        status = {
            "rate_limit": 429,
            "offline":    503,
            "auth":       503,
            "invalid":    400,
        }.get(exc.kind, 500)
        return jsonify({"error": exc.kind, "message": exc.message}), status
    except Exception:  # noqa: BLE001 — defesa em profundidade
        logger.exception("translate_api falha inesperada slug=%s", slug)
        return jsonify({"error": "generic", "message": MSG_GENERIC}), 500

    # Log da interacao — alimenta metricas de "idiomas usados" do epico Operador.
    db.session.add(InteractionLog(
        institution_id=inst.id,
        input_text=text[:1000],
        input_type=f"translate:{result.target_lang}",
        response_text=result.text[:1000],
    ))
    db.session.commit()

    return jsonify({
        "translation": result.text,
        "cached": result.cached,
        "source": result.source_lang,
        "target": result.target_lang,
    })


@translate_bp.route("/api/translate/languages", methods=["GET"])
def supported_languages():
    """Lista publica dos idiomas suportados — para popular dropdowns no front."""
    return jsonify({"languages": SUPPORTED_LANGUAGES})
