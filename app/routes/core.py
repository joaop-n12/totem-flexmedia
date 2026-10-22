"""Core routes: admin entry, public home, map, events, food."""
import random
import unicodedata
from flask import Blueprint, render_template, redirect, url_for, abort, jsonify, g, request, send_from_directory, current_app
from app.models import Event, FAQ, MapArea, Store
from app.helpers import load_institution
from app.services.i18n import SUPPORTED_LOCALES, set_locale

core_bp = Blueprint("core", __name__)


def _plain_text(value):
    value = (value or "").lower()
    value = unicodedata.normalize("NFKD", value)
    return "".join(ch for ch in value if not unicodedata.combining(ch))


def _is_food_store(store):
    haystack = _plain_text(f"{store.name} {store.category} {store.description}")
    keywords = (
        "alimentacao", "restaurante", "restaurant", "food", "praca",
        "lanchonete", "lanche", "cafe", "cafeteria", "sorvete",
        "sorveteria", "pizza", "hamburguer", "burger", "doces",
        "chocolate", "pastel", "acai", "suco", "bar", "bistro",
    )
    return any(word in haystack for word in keywords)


# Sprint 4: a sessao orientada por sensores NAO tem rota dedicada.
# Em vez disso, ela se manifesta como overlay global no `base.html` para
# que o totem reaja proativamente em qualquer tela (home, animais, mapa,
# voz, etc.). Ver bloco "Sessao orientada por sensores" no base.html e a
# maquina de estados em `app/services/session.py`.


# ── Troca de idioma da sessao ─────────────────────────────────────────────────
# Trello: Modulo 3 - Acessibilidade e Idiomas, criterios 3.1, 3.2, 3.6.
@core_bp.route("/api/locale", methods=["POST"])
def set_session_locale():
    """Define o idioma da sessao atual.

    Aceita JSON {"locale": "pt"|"en"} ou form. Retorna 400 se desconhecido.
    Sem auth — visitante anonimo pode trocar idioma. Idempotente.
    """
    data = request.get_json(silent=True) or {}
    locale = (data.get("locale") or request.form.get("locale") or "").strip().lower()
    if not set_locale(locale):
        return jsonify(error="locale_not_supported",
                       supported=list(SUPPORTED_LOCALES.keys())), 400
    return jsonify(ok=True, locale=locale)


# Service worker precisa ser servido a partir da raiz para ter escopo global.
# Sem isso, um SW em /static/ so intercepta /static/*.
@core_bp.route("/sw.js")
def service_worker():
    resp = send_from_directory(current_app.static_folder, "js/sw.js")
    resp.headers["Service-Worker-Allowed"] = "/"
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@core_bp.route("/offline")
def offline():
    """Pagina exibida pelo service worker quando nao ha rede."""
    return render_template("offline.html")


@core_bp.route("/privacidade")
@core_bp.route("/<slug>/privacidade")
def privacidade(slug=None):
    """Aviso de privacidade (LGPD).

    Exibido a partir do rodape e do modal de consentimento do assistente.
    """
    inst = load_institution(slug) if slug else None
    retention = current_app.config.get("INTERACTION_LOG_RETENTION_DAYS", 90)
    return render_template("privacidade.html", institution=inst, retention_days=retention)


@core_bp.route("/")
def index():
    """Redirect the first screen to the admin login."""
    return redirect(url_for("auth.login"))


@core_bp.route("/select")
def select_removed():
    """Legacy selector URL now goes straight to the admin login."""
    return redirect(url_for("auth.login"))


@core_bp.route("/<slug>")
@core_bp.route("/<slug>/")
def home(slug):
    inst = load_institution(slug)
    if inst.type == "shopping":
        return render_template("core/home_shopping.html", institution=inst)
    return render_template("core/home.html", institution=inst)


@core_bp.route("/<slug>/mapa")
def mapa(slug):
    inst = load_institution(slug)
    if not inst.has_module("mapa"):
        abort(404)
    areas = MapArea.query.filter_by(institution_id=inst.id).all()
    if inst.type == "shopping":
        stores = Store.query.filter_by(institution_id=inst.id).all()
        food_store_ids = {store.id for store in stores if _is_food_store(store)}
        return render_template("core/mapa_shopping.html", institution=inst, areas=areas,
                               stores=stores, food_store_ids=food_store_ids)
    area_targets = {}
    has_food_area = False
    has_entry_area = False
    for area in areas:
        area_slug = _plain_text(area.slug).replace("_", "-").replace(" ", "-")
        area_name = _plain_text(area.name).strip()
        if area_slug in {"alimentacao", "praca-de-alimentacao", "food-court"} or area_name in {
            "alimentacao", "praca de alimentacao", "praca de alimentacao do parque",
        }:
            area_targets[area.id] = url_for("core.alimentacao", slug=inst.slug)
            has_food_area = True
        elif area_slug in {"entrada", "entrada-principal", "bilheteria", "portao-principal"} or area_name in {
            "entrada", "entrada principal", "portao principal", "bilheteria",
        }:
            area_targets[area.id] = url_for("core.visitar", slug=inst.slug)
            has_entry_area = True
        elif area.slug:
            area_targets[area.id] = url_for("zoo.animais_por_area", slug=inst.slug, area_slug=area.slug)
        else:
            area_targets[area.id] = url_for("zoo.catalogo", slug=inst.slug)
    return render_template("core/mapa.html", institution=inst, areas=areas,
                           area_targets=area_targets, has_food_area=has_food_area,
                           has_entry_area=has_entry_area)


@core_bp.route("/<slug>/visitar")
@core_bp.route("/<slug>/ingressos")
def visitar(slug):
    inst = load_institution(slug)
    faqs = FAQ.query.filter_by(institution_id=inst.id).order_by(FAQ.category, FAQ.question).all()
    ticket_faqs = [faq for faq in faqs if any(term in _plain_text(f"{faq.category} {faq.question}")
                   for term in ("ingresso", "bilheteria", "preco", "valor", "meia-entrada", "gratuidade"))]
    hours_faqs = [faq for faq in faqs if any(term in _plain_text(f"{faq.category} {faq.question}")
                  for term in ("horario", "funcionamento"))]
    office_faqs = [faq for faq in faqs if "bilheteria" in _plain_text(f"{faq.category} {faq.question}")]
    return render_template("core/visitar.html", institution=inst, ticket_faqs=ticket_faqs,
                           hours_faqs=hours_faqs, office_faqs=office_faqs)


@core_bp.route("/<slug>/programacao")
def programacao(slug):
    inst = load_institution(slug)
    if not inst.has_module("programacao"):
        abort(404)
    eventos = Event.query.filter_by(institution_id=inst.id, active=True).all()
    return render_template("core/programacao.html", institution=inst, eventos=eventos)


@core_bp.route("/<slug>/alimentacao")
def alimentacao(slug):
    inst = load_institution(slug)
    if inst.type == "shopping":
        if not inst.has_module("alimentacao"):
            abort(404)
        stores = Store.query.filter_by(institution_id=inst.id).order_by(Store.name).all()
        food_stores = [store for store in stores if _is_food_store(store)]
        return render_template(
            "core/alimentacao_shopping.html",
            institution=inst,
            stores=food_stores,
        )
    return render_template("core/alimentacao.html", institution=inst)


# ── IoT sensor simulation (kept from original) ──────────────────────────────────

@core_bp.route("/api/sensores")
def api_sensores():
    return jsonify({
        "temperatura":  round(random.uniform(24.0, 30.0), 1),
        "umidade":      random.randint(45, 75),
        "presenca":     random.choice([True, False]),
        "luminosidade": random.randint(200, 700),
    })
