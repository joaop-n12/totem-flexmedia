"""Shared utilities: tenant loading, AI context builder, slugify, auth decorators, CSRF."""
import os
import re
import secrets
import unicodedata
from functools import wraps

from flask import abort, g, redirect, request, session, url_for
from flask_login import current_user

from app.models import Institution, Animal, Event, Store, Product, FAQ


# ── Slugify ────────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    text = (text or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s-]+", "-", text).strip("-")
    return text or "item"


# ── CSRF ───────────────────────────────────────────────────────────────────────

def generate_csrf_token() -> str:
    """Return (and lazily create) the per-session CSRF token."""
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]


def validate_csrf_token() -> None:
    """Abort 403 if the submitted CSRF token does not match the session token."""
    token = session.get("_csrf_token", "")
    form_token = request.form.get("_csrf_token", "")
    if not token or not secrets.compare_digest(token, form_token):
        abort(403)


# ── Tenant loading ─────────────────────────────────────────────────────────────

def load_institution(slug: str) -> Institution:
    """Fetch institution by slug and store in g.  Aborts 404 if not found."""
    inst = Institution.query.filter_by(slug=slug, active=True).first()
    if not inst:
        abort(404)
    g.institution = inst
    return inst


def require_module(module_slug: str):
    """Decorator: abort 404 if institution does not have the given module enabled."""
    def decorator(f):
        @wraps(f)
        def wrapper(slug, *args, **kwargs):
            inst = getattr(g, "institution", None) or load_institution(slug)
            if not inst.has_module(module_slug):
                abort(404)
            return f(slug, *args, **kwargs)
        return wrapper
    return decorator


# ── Auth decorators ────────────────────────────────────────────────────────────

def _login_redirect():
    next_path = request.path
    if next_path and next_path.startswith("/admin"):
        return redirect(url_for("auth.login", next=next_path))
    return redirect(url_for("auth.login"))


def super_admin_required(f):
    """Permite acesso apenas a usuários com role='super_admin'."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.active:
            return _login_redirect()
        if not current_user.is_super_admin:
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def client_admin_required(f):
    """
    Permite acesso a super_admin (qualquer instituição) e client_admin
    somente para a própria institution_id.  Garante isolamento de tenant.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.active:
            return _login_redirect()
        iid = kwargs.get("iid")
        if current_user.is_super_admin:
            pass  # acesso total
        elif current_user.role == "client_admin":
            if current_user.institution_id != iid:
                abort(403)
        else:
            abort(403)
        return f(*args, **kwargs)
    return wrapper


# ── AI context builder ─────────────────────────────────────────────────────────

def build_ai_context(institution: Institution) -> str:
    """Build a rich system prompt from institution data + FAQ + content."""
    lines = []

    base = (institution.ai_context or "").strip()
    if base:
        lines.append(base)
    else:
        lines.append(
            f"Você é {institution.ai_name}, assistente virtual do(a) {institution.name}. "
            "Responda de forma educada, clara e objetiva. "
            "Se não souber a resposta, sugira que o visitante fale com a equipe."
        )

    if institution.opening_hours:
        lines.append(f"\nHorário de funcionamento: {institution.opening_hours}")

    if institution.address:
        lines.append(f"Endereço: {institution.address}")

    events = Event.query.filter_by(institution_id=institution.id, active=True).all()
    if events:
        lines.append("\nEventos/Programação de hoje:")
        for ev in events:
            lines.append(f"  - {ev.evento} às {ev.horario or '?'} em {ev.local or '?'}")

    if institution.type == "zoo":
        animals = Animal.query.filter_by(institution_id=institution.id).all()
        if animals:
            by_species: dict = {}
            for a in animals:
                by_species.setdefault(a.especie or "Outros", []).append(a.nome)
            lines.append("\nAnimais do zoológico:")
            for sp, nomes in by_species.items():
                lines.append(f"  {sp}: {', '.join(nomes)}")

    if institution.type == "shopping":
        stores = Store.query.filter_by(institution_id=institution.id).all()
        if stores:
            lines.append("\nLojas:")
            for s in stores:
                info = f"  - {s.name} (Piso {s.floor or '?'}, {s.category or '?'})"
                if s.on_promotion:
                    info += f" ⭐ Promoção: {s.promo_text or 'Sim'}"
                lines.append(info)

    if institution.type == "pharmacy":
        promo = Product.query.filter_by(institution_id=institution.id, on_sale=True).all()
        if promo:
            lines.append("\nProdutos em promoção:")
            for p in promo:
                lines.append(f"  - {p.name} ({p.category or '?'})")

    faqs = FAQ.query.filter_by(institution_id=institution.id).all()
    if faqs:
        lines.append("\nPerguntas frequentes:")
        for fq in faqs:
            lines.append(f"  P: {fq.question}\n  R: {fq.answer}")

    return "\n".join(lines)


# ── Image upload helper ────────────────────────────────────────────────────────

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp", "svg"}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_upload(file, subfolder: str, filename: str) -> str:
    """Save an uploaded file and return its path relative to static/."""
    from flask import current_app
    upload_dir = os.path.join(current_app.config["UPLOAD_FOLDER"], subfolder)
    os.makedirs(upload_dir, exist_ok=True)
    dest = os.path.join(upload_dir, filename)
    file.save(dest)
    return os.path.join("uploads", subfolder, filename).replace("\\", "/")
