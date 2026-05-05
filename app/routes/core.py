"""Core routes: institution selector, home, map, events, food."""
import random
from flask import Blueprint, render_template, redirect, url_for, abort, jsonify, g, request, send_from_directory, current_app
from app.models import Institution, Event, MapArea
from app.helpers import load_institution
from app.services.i18n import SUPPORTED_LOCALES, set_locale

core_bp = Blueprint("core", __name__)


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
    """Redirect to selector or directly to the only active institution."""
    active = Institution.query.filter_by(active=True).all()
    if len(active) == 1:
        return redirect(url_for("core.home", slug=active[0].slug))
    return redirect(url_for("core.selector"))


@core_bp.route("/select")
def selector():
    """Institution selection screen."""
    institutions = Institution.query.filter_by(active=True).all()
    if len(institutions) == 1:
        return redirect(url_for("core.home", slug=institutions[0].slug))
    return render_template("selector.html", institutions=institutions)


@core_bp.route("/<slug>/")
def home(slug):
    inst = load_institution(slug)
    return render_template("core/home.html", institution=inst)


@core_bp.route("/<slug>/mapa")
def mapa(slug):
    inst = load_institution(slug)
    if not inst.has_module("mapa"):
        abort(404)
    areas = MapArea.query.filter_by(institution_id=inst.id).all()
    return render_template("core/mapa.html", institution=inst, areas=areas)


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
    if not inst.has_module("alimentacao"):
        abort(404)
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
