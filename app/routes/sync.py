"""Sincronizacao de conteudo entre admin e totem.

Atende o backlog Trello (Modulo 3 - Atualizacao de conteudo):
  3.1 Acesso ao banco de dados e mapeamento do local do cliente.
  3.2 Linkar banco de dados do cliente ao totem.
  3.3 Atualizar textos, imagens, localizacoes e instrucoes.
  3.5 Totem carrega informacoes atualizadas apos sync ou reinicializacao.
  3.6 Validacao: alteracao no banco reflete corretamente no totem.

Dois endpoints:

  GET /<slug>/api/sync/version
      Publico, leve, sem auth — devolve {version: N}. Consumido pelo
      kiosk em polling (a cada 60s) para detectar mudancas e recarregar.
      Sem auth porque so devolve um inteiro derivado de dados publicos.

  GET /api/sync/snapshot
      HMAC-autenticado (mesmo esquema do /api/heartbeat). Devolve um JSON
      com tudo que o totem precisa para renderizar offline:
        - institution (cores, logo, contexto IA)
        - modulos habilitados
        - animais, eventos, lojas, produtos, FAQs, areas do mapa
      Suporta `If-None-Match: "v123"` → 304 Not Modified (economiza
      banda no Pi 3 com 4G).

Versionamento:
  `Institution.content_version` e' incrementado por listener SQLAlchemy
  global em qualquer mutacao de Animal/Event/Store/Product/FAQ/MapArea.
  Nao depende do desenvolvedor lembrar de chamar bump em cada rota.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
from datetime import datetime

from flask import Blueprint, abort, current_app, jsonify, request

from app.extensions import db, limiter
from app.helpers import load_institution
from app.models import (
    Animal, Event, FAQ, Institution, InstitutionModule,
    MapArea, Product, Store, TotemDevice,
)

logger = logging.getLogger(__name__)

sync_bp = Blueprint("sync", __name__)


# ════════════════════════════════════════════════════════════════════════════
# Endpoint publico — versao apenas (polling do kiosk)
# ════════════════════════════════════════════════════════════════════════════

@sync_bp.route("/<slug>/api/sync/version", methods=["GET"])
@limiter.limit("120 per minute")  # 2/s — folgado para polling de 1 kiosk
def version(slug):
    """Versao atual do conteudo da instituicao. Sem auth, sem dados sensiveis.

    O kiosk JS chama isso periodicamente. Resposta minima de proposito —
    quanto menor, menor o custo na 4G do Pi 3.
    """
    inst = load_institution(slug)
    # Endpoint de polling — DEVE ler valor atual, nao cache da identity map.
    # Sem o expire, sessoes reutilizadas (test client compartilhando contexto
    # com fixture, ou prod com sessao keep-alive) podem devolver content_version
    # antigo apos um commit feito em outra sessao no mesmo engine.
    # Custo: um SELECT extra por request — ok para polling de 60s.
    db.session.expire(inst, ["content_version"])
    return jsonify({
        "slug": inst.slug,
        "version": inst.content_version,
    })


# ════════════════════════════════════════════════════════════════════════════
# Endpoint HMAC — snapshot completo (consumido pelo totem)
# ════════════════════════════════════════════════════════════════════════════

def _check_timestamp(ts_str: str, skew: int) -> bool:
    try:
        ts = int(ts_str)
    except (TypeError, ValueError):
        return False
    return abs(int(datetime.utcnow().timestamp()) - ts) <= skew


@sync_bp.route("/api/sync/snapshot", methods=["GET"])
@limiter.limit("30 per minute")
def snapshot():
    """Snapshot completo do tenant ao qual o totem pertence.

    Auth: mesmos headers do /api/heartbeat (X-Totem-Key, X-Totem-Timestamp,
    X-Totem-Signature) — reusa as credenciais HMAC do dispositivo. O
    institution_id NAO vai no path nem na query — vem do TotemDevice
    autenticado, impedindo um totem de pedir o snapshot de outra instituicao.
    """
    api_key_id = request.headers.get("X-Totem-Key", "").strip()
    timestamp = request.headers.get("X-Totem-Timestamp", "").strip()
    signature = request.headers.get("X-Totem-Signature", "").strip()

    if not (api_key_id and timestamp and signature):
        return jsonify(error="missing_auth_headers"), 401

    skew = current_app.config.get("HEARTBEAT_CLOCK_SKEW_SECONDS", 300)
    if not _check_timestamp(timestamp, skew):
        return jsonify(error="timestamp_out_of_window"), 401

    device = TotemDevice.query.filter_by(api_key_id=api_key_id).first()
    if not device or not device.is_active:
        return jsonify(error="auth_failed"), 401

    # GET sem body — assina o body vazio (mesma formula do heartbeat).
    if not device.verify_hmac(timestamp, b"", signature):
        return jsonify(error="invalid_signature"), 401

    inst = device.institution
    if not inst or not inst.active:
        return jsonify(error="institution_inactive"), 403

    # Mesma defesa contra identity map stale do endpoint /version.
    db.session.expire(inst, ["content_version"])

    # ETag = "v<content_version>" — barato e suficiente para cache HTTP.
    etag = f'"v{inst.content_version}"'
    if request.headers.get("If-None-Match", "").strip() == etag:
        # 304 economiza banda — Pi com 4G agradece.
        return ("", 304, {"ETag": etag})

    payload = _build_snapshot(inst)
    response = jsonify(payload)
    response.headers["ETag"] = etag
    response.headers["Cache-Control"] = "private, max-age=0, must-revalidate"
    return response


# ════════════════════════════════════════════════════════════════════════════
# Construcao do snapshot
# ════════════════════════════════════════════════════════════════════════════

def _build_snapshot(inst: Institution) -> dict:
    """Serializa o tenant em um dicionario JSON-able.

    Mantem o formato chato (dicts/lists primitivos) para o cliente nao
    precisar de SQLAlchemy. Imagens vao como path relativo a /static/ —
    o totem que monta a URL final.
    """
    modules = (
        InstitutionModule.query
        .filter_by(institution_id=inst.id, enabled=True)
        .order_by(InstitutionModule.order)
        .all()
    )

    return {
        "version": inst.content_version,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "institution": {
            "id": inst.id,
            "slug": inst.slug,
            "name": inst.name,
            "type": inst.type,
            "tagline": inst.tagline,
            "logo_path": inst.logo_path,
            "primary_color": inst.primary_color,
            "secondary_color": inst.secondary_color,
            "bg_color": inst.bg_color,
            "text_color": inst.text_color,
            "theme": inst.theme,
            "address": inst.address,
            "phone": inst.phone,
            "opening_hours": inst.opening_hours,
            "website": inst.website,
            "ai_name": inst.ai_name,
            "ai_context": inst.ai_context,
        },
        "modules": [
            {"slug": m.module_slug, "order": m.order} for m in modules
        ],
        "animals": [_animal_to_dict(a) for a in inst.animals],
        "events": [_event_to_dict(e) for e in inst.events],
        "stores": [_store_to_dict(s) for s in inst.stores],
        "products": [_product_to_dict(p) for p in inst.products],
        "faqs": [_faq_to_dict(f) for f in inst.faqs],
        "map_areas": [_map_area_to_dict(m) for m in inst.map_areas],
    }


def _animal_to_dict(a: Animal) -> dict:
    return {
        "id": a.id, "slug": a.slug, "nome": a.nome,
        "especie": a.especie, "habitat": a.habitat, "area": a.area,
        "descricao": a.descricao, "alimentacao": a.alimentacao,
        "curiosidades": a.curiosidades, "conservacao": a.conservacao,
        "imagem": a.imagem,
    }


def _event_to_dict(e: Event) -> dict:
    return {
        "id": e.id, "evento": e.evento, "horario": e.horario,
        "local": e.local, "descricao": e.descricao, "active": e.active,
    }


def _store_to_dict(s: Store) -> dict:
    return {
        "id": s.id, "slug": s.slug, "name": s.name, "category": s.category,
        "floor": s.floor, "description": s.description, "hours": s.hours,
        "phone": s.phone, "on_promotion": s.on_promotion,
        "promo_text": s.promo_text,
    }


def _product_to_dict(p: Product) -> dict:
    return {
        "id": p.id, "name": p.name, "category": p.category,
        "description": p.description, "price": p.price,
        "on_sale": p.on_sale, "sale_price": p.sale_price,
    }


def _faq_to_dict(f: FAQ) -> dict:
    return {
        "id": f.id, "question": f.question, "answer": f.answer,
        "category": f.category,
    }


def _map_area_to_dict(m: MapArea) -> dict:
    # MapArea pode ter shape variavel (poligono SVG, marker x/y, etc).
    # Serializamos defensivamente — getattr com default evita crash em
    # campo opcional que ainda nao existe no banco.
    return {
        "id": m.id,
        "name": getattr(m, "name", None),
        "kind": getattr(m, "kind", None),
        "data": getattr(m, "data", None),
    }
