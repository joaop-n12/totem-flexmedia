"""Shared utilities: tenant loading, AI context builder, slugify, auth decorators, CSRF."""
import json
import os
import re
import secrets
import unicodedata
from functools import wraps

from flask import abort, current_app, g, redirect, request, session, url_for
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
    """Abort 403 if the submitted CSRF token does not match the session token.

    Respeita WTF_CSRF_ENABLED para que a suite de testes possa enviar POSTs
    sem precisar simular o ciclo de GET → renderiza form → POST com token.
    Em desenvolvimento e producao o flag fica True (default).
    """
    if current_app.config.get("WTF_CSRF_ENABLED", True) is False:
        return
    token = session.get("_csrf_token", "")
    form_token = request.form.get("_csrf_token", "")
    # Defesa em profundidade: token tem que existir, ter tamanho minimo e
    # bater em tempo constante. Sem o len-check, uma futura remocao do guard
    # `not token` viraria bypass via compare_digest("", "") == True.
    if not token or len(token) < 32 or not secrets.compare_digest(token, form_token):
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
    """Permite acesso apenas a usuários com role='super_admin'.

    Politica de seguranca: super_admin SEM 2FA configurado e empurrado para
    a tela de cadastro antes de acessar qualquer rota de plataforma.
    Comprometer a conta da plataforma e o pior caso possivel — 2FA e
    requisito, nao opcao. A propria rota de setup e a unica excecao.
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.active:
            return _login_redirect()
        if not current_user.is_super_admin:
            abort(403)
        if not current_user.has_totp and request.endpoint != "auth.totp_setup":
            return redirect(url_for("auth.totp_setup"))
        return f(*args, **kwargs)
    return wrapper


def client_admin_required(f):
    """
    Permite acesso a super_admin (qualquer instituição) e client_admin
    somente para a própria institution_id.  Garante isolamento de tenant.

    Tentativa de cross-tenant (client_admin pedindo iid != institution_id)
    NAO retorna apenas 403: tambem grava AdminAuditLog com ACTION_TENANT_DENIED.
    Esse sinal e' tipicamente sintoma de:
      - Credencial vazada (atacante explorando IDs sequenciais).
      - Bug de UI deixando link errado.
      - Tentativa interna nao autorizada.
    Manter trilha permite o super_admin investigar mesmo dias depois.
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
                # Audita ANTES do abort — senao o handler 403 ja respondeu.
                # `commit=True` garante persistencia mesmo que o request seja
                # interrompido pelo abort(403) sem commit posterior.
                from app.helpers import audit_log as _audit
                _audit(
                    "tenant.access_denied",
                    resource_type="institution",
                    resource_id=iid,
                    details={
                        "endpoint": request.endpoint,
                        "path": request.path,
                        "user_institution_id": current_user.institution_id,
                        "requested_institution_id": iid,
                    },
                    commit=True,
                )
                abort(403)
        else:
            abort(403)
        return f(*args, **kwargs)
    return wrapper


# ── Tenant scoping helpers ────────────────────────────────────────────────────
# Padrao adotado em admin_institution.py: toda query de filho (Animal, Event,
# Store, Product, FAQ, InteractionLog) DEVE filtrar tambem por institution_id.
# Esses helpers centralizam a regra para evitar IDOR via parametro de rota:
# se um futuro PR esquecer o filter_by(institution_id=...), basta usar
# `tenant_get_or_404(Model, id, iid)` e o isolamento e' garantido.

def tenant_get_or_404(model, child_id, iid):
    """Busca registro filho garantindo que pertenca a `iid` (404 se nao).

    Levanta 404 (e nao 403) intencionalmente quando a pessoa pede um id
    de outro tenant — nao queremos vazar a existencia de recursos alheios.
    Para um atacante o efeito e' indistinguivel de "id inexistente".
    """
    if not hasattr(model, "institution_id"):
        # Erro de programacao — modelo errado para esse helper.
        raise TypeError(f"{model.__name__} nao tem coluna institution_id")
    return model.query.filter_by(id=child_id, institution_id=iid).first_or_404()


def tenant_query(model, iid):
    """Query base filtrada por institution_id. Use para listagens."""
    if not hasattr(model, "institution_id"):
        raise TypeError(f"{model.__name__} nao tem coluna institution_id")
    return model.query.filter_by(institution_id=iid)


def bump_content_version(iid: int) -> None:
    """Incrementa Institution.content_version do tenant alvo.

    Acionado por cada mutacao bem-sucedida em conteudo gerenciado pelo
    client_admin (animais, eventos, lojas, produtos, FAQs). O totem polla
    /api/sync/version a cada N segundos e recarrega quando o numero muda
    — assim a atualizacao no painel reflete no kiosk sem precisar reiniciar
    o sistema.

    Implementacao via UPDATE atomico (e nao read-modify-write) para evitar
    race entre dois admins editando ao mesmo tempo. Funciona em SQLite e
    Postgres porque `Institution.content_version + 1` e' resolvido pelo
    proprio banco.

    NAO faz commit — o caller controla a transacao para que o bump fique
    no mesmo commit da mudanca de conteudo (atomicidade).
    """
    from app.extensions import db
    from app.models import Institution
    db.session.query(Institution).filter(Institution.id == iid).update(
        {Institution.content_version: Institution.content_version + 1},
        synchronize_session=False,
    )


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

# SVG removido propositalmente: pode embutir <script> e atributos on*. Mesmo
# servido pelo admin (CSP estrita), o arquivo fica em /static/uploads — se
# aberto direto pelo URL fora do contexto admin, executa. Voltar a aceitar
# SVG exige sanitizacao com bleach/defusedxml ou Content-Disposition: attachment.
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_upload(file, subfolder: str, filename: str) -> str:
    """Save an uploaded file and return its path relative to static/."""
    upload_dir = os.path.join(current_app.config["UPLOAD_FOLDER"], subfolder)
    os.makedirs(upload_dir, exist_ok=True)
    dest = os.path.join(upload_dir, filename)
    file.save(dest)
    return os.path.join("uploads", subfolder, filename).replace("\\", "/")


# ── Política de senha ──────────────────────────────────────────────────────────
# Mínimo de 12 caracteres + variedade (3 das 4 classes: minúscula, maiúscula,
# número, símbolo). Não exigimos todas as 4 classes — empurra usuários para
# padrões previsíveis do tipo "Senha123!". A regra real é: tamanho impede
# ataque por força bruta.
PASSWORD_MIN_LENGTH = 12


def validate_password_strength(password: str) -> list[str]:
    """Retorna lista de erros (vazia = senha aceita)."""
    erros: list[str] = []
    if not password or len(password) < PASSWORD_MIN_LENGTH:
        erros.append(f"Senha deve ter ao menos {PASSWORD_MIN_LENGTH} caracteres.")
    classes = sum([
        bool(re.search(r"[a-z]", password)),
        bool(re.search(r"[A-Z]", password)),
        bool(re.search(r"\d", password)),
        bool(re.search(r"[^A-Za-z0-9]", password)),
    ])
    if classes < 3:
        erros.append(
            "Senha deve combinar pelo menos 3 categorias entre: minúscula, "
            "maiúscula, número e símbolo."
        )
    # Senhas óbvias mesmo passando nas regras acima.
    fracas = {"flexmedia2024", "senha123456", "password1234", "totemflexmedia"}
    if password.lower() in fracas:
        erros.append("Senha em lista de senhas comuns. Escolha outra.")
    return erros


# ── Audit log ──────────────────────────────────────────────────────────────────
# Wrapper pequeno para registrar ações administrativas. Aceita atualizar via
# tanto current_user (rotas autenticadas) quanto chamadas anônimas (login).
def audit_log(
    action: str,
    *,
    actor=None,
    actor_email: str | None = None,
    resource_type: str | None = None,
    resource_id=None,
    details: dict | None = None,
    commit: bool = False,
) -> None:
    """Insere uma linha em admin_audit_logs.

    NUNCA passar campos sensíveis (senhas, tokens) em `details`.
    `commit=True` apenas em rotas que já não fazem commit próprio depois.
    """
    from app.extensions import db
    from app.models import AdminAuditLog

    if actor is None and current_user and getattr(current_user, "is_authenticated", False):
        actor = current_user

    ip = (request.remote_addr or "unknown") if request else "unknown"
    ua = (request.headers.get("User-Agent", "") or "")[:255] if request else None

    entry = AdminAuditLog(
        actor_user_id=getattr(actor, "id", None),
        actor_email=getattr(actor, "email", None) or actor_email,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        details_json=json.dumps(details, default=str) if details else None,
        ip_address=ip,
        user_agent=ua,
    )
    db.session.add(entry)
    if commit:
        db.session.commit()
