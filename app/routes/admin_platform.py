"""Admin platform: dashboard global, CRUD de instituições e usuários (super_admin)."""
import re

from flask import (
    Blueprint, flash, g, jsonify, redirect, render_template,
    request, url_for,
)

from app.extensions import db
from app.helpers import (
    allowed_file, audit_log, save_upload, slugify,
    super_admin_required, validate_csrf_token,
    validate_password_strength,
)
from app.models import (
    AdminAuditLog, AuthLog, Institution, InteractionLog,
    Module, InstitutionModule, User,
)
from app.models.audit import (
    ACTION_INSTITUTION_CREATE, ACTION_INSTITUTION_DELETE,
    ACTION_INSTITUTION_UPDATE, ACTION_USER_CREATE,
    ACTION_USER_DELETE, ACTION_USER_UPDATE,
)
from app.services.metrics import (
    DEFAULT_DAYS, collect_metrics_dict, collect_platform_summary,
)

admin_platform_bp = Blueprint("admin_platform", __name__)


def _safe_int(raw, default: int) -> int:
    """Parse defensivo de inteiros vindos de form. Nao explode em 500 com lixo."""
    try:
        return int(raw) if raw not in (None, "") else default
    except (TypeError, ValueError):
        return default


# URL publica do totem: precisa ser HTTPS (Secure Origin) para liberar
# getUserMedia (microfone) em navegador. Aceitamos http://localhost apenas
# para conveniencia de dev — em producao a validacao real e' do navegador.
_PUBLIC_URL_RE = re.compile(
    r"^https://[A-Za-z0-9.\-]+(?::\d+)?(?:/[^\s]*)?$"
)


def _clean_public_url(raw: str | None) -> str | None:
    """Normaliza/valida a URL publica vinda do form.

    Regras:
      - Strip whitespace + barra final.
      - String vazia → None (apaga o campo).
      - Precisa bater com `_PUBLIC_URL_RE` (https://, hostname, opcional porta+path).
      - Tamanho maximo 255 (limite da coluna).

    Retorna None se nao houver nada a salvar; levanta ValueError em URL
    malformada (caller decide se aborta ou apenas avisa).
    """
    if raw is None:
        return None
    candidato = raw.strip().rstrip("/")
    if not candidato:
        return None
    if len(candidato) > 255:
        raise ValueError("URL publica excede 255 caracteres.")
    if not _PUBLIC_URL_RE.match(candidato):
        raise ValueError(
            "URL publica precisa comecar com https:// "
            "(Secure Origin exigido pelo navegador para microfone)."
        )
    return candidato


# ── Dashboard ──────────────────────────────────────────────────────────────────

@admin_platform_bp.route("/")
@super_admin_required
def dashboard():
    stats = {
        "institutions": Institution.query.count(),
        "users":        User.query.count(),
        "logs":         InteractionLog.query.count(),
        "auth_fails":   AuthLog.query.filter_by(success=False).count(),
    }
    institutions = Institution.query.order_by(Institution.name).all()
    recent_logs  = InteractionLog.query.order_by(InteractionLog.created_at.desc()).limit(10).all()

    # Resumo agregado por instituicao nos ultimos 30 dias.
    # Combina com a lista de instituicoes para que o template ja receba
    # cada inst com seus totais sem precisar de N queries no Jinja.
    summary_by_id = {row["institution_id"]: row
                     for row in collect_platform_summary(days=DEFAULT_DAYS)}
    institutions_with_metrics = []
    for inst in institutions:
        m = summary_by_id.get(inst.id, {
            "total": 0, "voice": 0, "text": 0, "translate": 0, "other": 0,
        })
        institutions_with_metrics.append({"inst": inst, **m})

    return render_template(
        "admin/platform/dashboard.html",
        stats=stats,
        institutions=institutions,
        institutions_metrics=institutions_with_metrics,
        recent_logs=recent_logs,
        period_days=DEFAULT_DAYS,
    )


# ── Metricas por instituicao ───────────────────────────────────────────────────

@admin_platform_bp.route("/metrics/<int:iid>")
@super_admin_required
def metrics_view(iid):
    """Pagina HTML de metricas de UMA instituicao."""
    inst = Institution.query.get_or_404(iid)
    days = max(1, min(365, request.args.get("days", default=DEFAULT_DAYS, type=int)))
    metrics = collect_metrics_dict(iid, days=days)
    return render_template(
        "admin/platform/metrics.html",
        inst=inst,
        metrics=metrics,
        days=days,
    )


@admin_platform_bp.route("/metrics/<int:iid>.json")
@super_admin_required
def metrics_json(iid):
    """JSON consumido por graficos client-side (Chart.js no template)."""
    Institution.query.get_or_404(iid)  # 404 se nao existe
    days = max(1, min(365, request.args.get("days", default=DEFAULT_DAYS, type=int)))
    return jsonify(collect_metrics_dict(iid, days=days))


# ── Institutions ───────────────────────────────────────────────────────────────

@admin_platform_bp.route("/institutions/")
@super_admin_required
def institution_list():
    institutions = Institution.query.order_by(Institution.name).all()
    return render_template("admin/platform/institution_list.html", institutions=institutions)


@admin_platform_bp.route("/institutions/new", methods=["GET", "POST"])
@super_admin_required
def institution_new():
    modules = Module.query.order_by(Module.name).all()
    if request.method == "POST":
        validate_csrf_token()
        try:
            public_url = _clean_public_url(request.form.get("public_url"))
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template("admin/platform/institution_form.html",
                                   inst=None, modules=modules, action="new")
        inst = Institution(
            slug            = slugify(request.form.get("slug") or request.form.get("name", "")),
            name            = request.form["name"],
            type            = request.form.get("type", "zoo"),
            tagline         = request.form.get("tagline", ""),
            primary_color   = request.form.get("primary_color", "#f4b860"),
            secondary_color = request.form.get("secondary_color", "#4dd9d0"),
            bg_color        = request.form.get("bg_color", "#040c10"),
            text_color      = request.form.get("text_color", "#ddeef7"),
            theme           = request.form.get("theme", "dark"),
            address         = request.form.get("address", ""),
            phone           = request.form.get("phone", ""),
            opening_hours   = request.form.get("opening_hours", ""),
            public_url      = public_url,
            ai_name         = request.form.get("ai_name", "Assistente"),
            ai_context      = request.form.get("ai_context", ""),
            daily_ai_quota  = max(0, _safe_int(request.form.get("daily_ai_quota"), 500)),
            active          = "active" in request.form,
        )
        logo = request.files.get("logo")
        if logo and logo.filename and allowed_file(logo.filename):
            ext = logo.filename.rsplit(".", 1)[1].lower()
            inst.logo_path = save_upload(logo, inst.slug, f"logo.{ext}")

        db.session.add(inst)
        db.session.flush()

        for mod in modules:
            if mod.slug in request.form.getlist("modules"):
                order = _safe_int(request.form.get(f"order_{mod.slug}"), 99)
                db.session.add(InstitutionModule(
                    institution_id=inst.id,
                    module_slug=mod.slug,
                    enabled=True,
                    order=order,
                ))

        audit_log(
            ACTION_INSTITUTION_CREATE,
            resource_type="institution", resource_id=inst.id,
            details={"name": inst.name, "slug": inst.slug, "type": inst.type},
        )
        db.session.commit()
        flash(f"Instituição '{inst.name}' criada com sucesso.", "success")
        return redirect(url_for("admin_platform.institution_list"))

    return render_template("admin/platform/institution_form.html",
                           inst=None, modules=modules, action="new")


@admin_platform_bp.route("/institutions/<int:iid>/edit", methods=["GET", "POST"])
@super_admin_required
def institution_edit(iid):
    inst    = Institution.query.get_or_404(iid)
    modules = Module.query.order_by(Module.name).all()

    if request.method == "POST":
        validate_csrf_token()
        try:
            public_url = _clean_public_url(request.form.get("public_url"))
        except ValueError as exc:
            flash(str(exc), "error")
            return render_template("admin/platform/institution_form.html",
                                   inst=inst, modules=modules, action="edit")
        inst.name            = request.form["name"]
        inst.slug            = slugify(request.form.get("slug") or inst.name)
        inst.type            = request.form.get("type", inst.type)
        inst.tagline         = request.form.get("tagline", "")
        inst.primary_color   = request.form.get("primary_color", inst.primary_color)
        inst.secondary_color = request.form.get("secondary_color", inst.secondary_color)
        inst.bg_color        = request.form.get("bg_color", inst.bg_color)
        inst.text_color      = request.form.get("text_color", inst.text_color)
        inst.theme           = request.form.get("theme", inst.theme)
        inst.address         = request.form.get("address", "")
        inst.phone           = request.form.get("phone", "")
        inst.opening_hours   = request.form.get("opening_hours", "")
        inst.public_url      = public_url
        inst.ai_name         = request.form.get("ai_name", "Assistente")
        inst.ai_context      = request.form.get("ai_context", "")
        inst.daily_ai_quota  = max(0, _safe_int(request.form.get("daily_ai_quota"), inst.daily_ai_quota or 500))
        inst.active          = "active" in request.form

        logo = request.files.get("logo")
        if logo and logo.filename and allowed_file(logo.filename):
            ext = logo.filename.rsplit(".", 1)[1].lower()
            inst.logo_path = save_upload(logo, inst.slug, f"logo.{ext}")

        enabled_slugs = set(request.form.getlist("modules"))
        existing = {m.module_slug: m for m in inst.modules}

        for mod in modules:
            if mod.slug in enabled_slugs:
                order = _safe_int(request.form.get(f"order_{mod.slug}"), 99)
                if mod.slug in existing:
                    existing[mod.slug].enabled = True
                    existing[mod.slug].order   = order
                else:
                    db.session.add(InstitutionModule(
                        institution_id=inst.id, module_slug=mod.slug,
                        enabled=True, order=order,
                    ))
            else:
                if mod.slug in existing:
                    existing[mod.slug].enabled = False

        audit_log(
            ACTION_INSTITUTION_UPDATE,
            resource_type="institution", resource_id=inst.id,
            details={"name": inst.name, "active": inst.active},
        )
        db.session.commit()
        flash(f"Instituição '{inst.name}' atualizada.", "success")
        return redirect(url_for("admin_platform.institution_list"))

    return render_template("admin/platform/institution_form.html",
                           inst=inst, modules=modules, action="edit")


@admin_platform_bp.route("/institutions/<int:iid>/delete", methods=["POST"])
@super_admin_required
def institution_delete(iid):
    validate_csrf_token()
    inst = Institution.query.get_or_404(iid)
    name = inst.name
    audit_log(
        ACTION_INSTITUTION_DELETE,
        resource_type="institution", resource_id=inst.id,
        details={"name": name, "slug": inst.slug},
    )
    db.session.delete(inst)
    db.session.commit()
    flash(f"Instituição '{name}' removida.", "warning")
    return redirect(url_for("admin_platform.institution_list"))


@admin_platform_bp.route("/institutions/<int:iid>/enter", methods=["POST"])
@super_admin_required
def institution_enter(iid):
    validate_csrf_token()
    Institution.query.get_or_404(iid)
    return redirect(url_for("admin_institution.dashboard", iid=iid))


# ── Pre-visualizacao de white-label (Trello: Modulo 1 - White Label 1.4) ──────
# Renderiza a home do totem aplicando atributos visuais propostos (cores,
# tema, tagline, ai_name) sem persistir nada. Permite ao super_admin ver o
# resultado antes de salvar.
#
# Defesa em profundidade contra commit acidental:
#   - `db.session.expunge(inst)` desliga o objeto da sessao. Mesmo que algo
#     mais tarde chamasse `db.session.commit()`, a inst nao seria persistida.
#   - Apos override, NAO re-adicionamos a sessao.
#   - Validacao de cada campo proposto antes de aplicar (hex valido, theme
#     conhecido, tamanho maximo) — entrada nao-confiavel nao rompe layout.

_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_THEME_VALUES = {"dark", "light"}
_PREVIEW_MAX_TAGLINE = 255
_PREVIEW_MAX_AI_NAME = 60


def _apply_preview_overrides(inst, src):
    """Aplica overrides validados sobre o objeto Institution (em memoria).

    Campos invalidos sao descartados silenciosamente — preview e' melhor
    cair no padrao do que dar 400 e quebrar o fluxo de edicao.
    """
    for field in ("primary_color", "secondary_color", "bg_color", "text_color"):
        v = (src.get(field) or "").strip()
        if v and _HEX_COLOR_RE.match(v):
            setattr(inst, field, v)

    theme = (src.get("theme") or "").strip().lower()
    if theme in _THEME_VALUES:
        inst.theme = theme

    tagline = (src.get("tagline") or "").strip()
    if tagline:
        inst.tagline = tagline[:_PREVIEW_MAX_TAGLINE]

    ai_name = (src.get("ai_name") or "").strip()
    if ai_name:
        inst.ai_name = ai_name[:_PREVIEW_MAX_AI_NAME]


def _apply_preview_modules(inst, src):
    """Aplica módulos e ordem enviados pelo formulário, somente em memória."""
    inst.modules = [
        InstitutionModule(
            module_slug=slug,
            enabled=True,
            order=_safe_int(src.get(f"order_{slug}"), 99),
        )
        for slug in dict.fromkeys(src.getlist("modules"))
    ]


@admin_platform_bp.route("/institutions/<int:iid>/preview", methods=["GET", "POST"])
@super_admin_required
def institution_preview(iid):
    """Renderiza a home da instituicao com overrides visuais sem persistir.

    GET aceita os campos via querystring; POST aceita via form (mais util
    quando ha muitos campos com caracteres especiais que escapariam em URL).
    Token CSRF validado em POST.
    """
    inst = Institution.query.get_or_404(iid)
    src = request.form if request.method == "POST" else request.args
    if request.method == "POST":
        validate_csrf_token()
        _apply_preview_modules(inst, request.form)

    # Mantemos `inst` atachada a sessao para que lazy loads (modules etc.)
    # funcionem no template. Mudancas em atributos NAO sao persistidas porque
    # esta rota NUNCA chama `db.session.commit()`. Apos a resposta, o teardown
    # do Flask-SQLAlchemy faz `session.remove()` que descarta a transacao
    # pendente. Belt + suspenders: rollback explicito ao final.
    _apply_preview_overrides(inst, src)

    # `g.institution` alimenta o context_processor que injeta `institution`
    # no Jinja. Marcar `preview_mode` permite ao base.html mostrar a barra
    # "PREVIEW — alteracoes nao salvas".
    g.institution = inst
    g.preview_mode = True
    template = "core/home_shopping.html" if inst.type == "shopping" else "core/home.html"
    rendered = render_template(template, institution=inst, preview_mode=True)
    # Garantia explicita: nada de mutacao sobrevive a este request.
    db.session.rollback()
    return rendered


@admin_platform_bp.route("/institutions/preview-new", methods=["POST"])
@super_admin_required
def institution_preview_new():
    """Preview de um cliente ainda nao salvo, sem criar registros no banco."""
    validate_csrf_token()
    src = request.form
    name = (src.get("name") or "Novo cliente").strip()[:120]
    inst = Institution(
        id=0,
        name=name or "Novo cliente",
        slug=slugify(src.get("slug") or name or "preview"),
        type=src.get("type", "zoo"),
        tagline="",
        primary_color="#f4b860",
        secondary_color="#4dd9d0",
        bg_color="#040c10",
        text_color="#ddeef7",
        theme="dark",
        ai_name="Assistente",
    )
    _apply_preview_overrides(inst, src)
    _apply_preview_modules(inst, request.form)
    g.institution = inst
    g.preview_mode = True
    template = "core/home_shopping.html" if inst.type == "shopping" else "core/home.html"
    rendered = render_template(template, institution=inst, preview_mode=True)
    db.session.rollback()
    return rendered


# ── Users ──────────────────────────────────────────────────────────────────────

@admin_platform_bp.route("/users/")
@super_admin_required
def user_list():
    users = User.query.order_by(User.name).all()
    return render_template("admin/platform/user_list.html", users=users)


@admin_platform_bp.route("/users/new", methods=["GET", "POST"])
@super_admin_required
def user_new():
    institutions = Institution.query.order_by(Institution.name).all()
    if request.method == "POST":
        validate_csrf_token()
        email    = (request.form.get("email", "") or "").strip().lower()
        password = request.form.get("password", "") or ""
        name     = request.form.get("name", "").strip()
        role     = request.form.get("role", "client_admin")
        iid_raw  = request.form.get("institution_id", "")

        errors = []
        if not email:
            errors.append("E-mail obrigatório.")
        errors.extend(validate_password_strength(password))
        if role not in ("super_admin", "client_admin", "operational"):
            errors.append("Role inválida.")
        if role in ("client_admin", "operational") and not iid_raw:
            errors.append("Client admin deve ter uma instituição vinculada.")
        institution = Institution.query.get(int(iid_raw)) if iid_raw.isdigit() else None
        if role in ("client_admin", "operational") and iid_raw and not institution:
            errors.append("Cliente inválido.")
        if User.query.filter_by(email=email).first():
            errors.append("E-mail já cadastrado.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("admin/platform/user_form.html",
                                   user=None, institutions=institutions, action="new")

        institution_id = int(iid_raw) if role in ("client_admin", "operational") and iid_raw else None
        user = User(
            email=email,
            name=name,
            role=role,
            institution_id=institution_id,
            active=True,
            # Senha definida pelo super_admin é tratada como temporária:
            # o usuário é forçado a trocá-la no primeiro login.
            must_change_password=True,
        )
        user.set_password(password)
        # set_password reseta must_change_password — re-aplicamos depois.
        user.must_change_password = True
        db.session.add(user)
        db.session.flush()
        audit_log(
            ACTION_USER_CREATE,
            resource_type="user", resource_id=user.id,
            details={"email": email, "role": role, "institution_id": institution_id},
        )
        db.session.commit()
        flash(f"Usuário '{name}' criado. Ele deverá trocar a senha no primeiro acesso.", "success")
        return redirect(url_for("admin_platform.user_list"))

    return render_template("admin/platform/user_form.html",
                           user=None, institutions=institutions, action="new")


@admin_platform_bp.route("/users/<int:uid>/edit", methods=["GET", "POST"])
@super_admin_required
def user_edit(uid):
    user         = User.query.get_or_404(uid)
    institutions = Institution.query.order_by(Institution.name).all()

    if request.method == "POST":
        validate_csrf_token()
        email    = (request.form.get("email", "") or "").strip().lower()
        name     = request.form.get("name", "").strip()
        role     = request.form.get("role", user.role)
        iid_raw  = request.form.get("institution_id", "")
        password = request.form.get("password", "") or ""

        errors = []
        if not email:
            errors.append("E-mail obrigatório.")
        if role not in ("super_admin", "client_admin", "operational"):
            errors.append("Role inválida.")
        if role in ("client_admin", "operational") and not iid_raw:
            errors.append("Client admin deve ter uma instituição vinculada.")
        institution = Institution.query.get(int(iid_raw)) if iid_raw.isdigit() else None
        if role in ("client_admin", "operational") and iid_raw and not institution:
            errors.append("Cliente inválido.")
        conflict = User.query.filter(User.email == email, User.id != uid).first()
        if conflict:
            errors.append("E-mail já usado por outro usuário.")
        if password:
            errors.extend(validate_password_strength(password))

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("admin/platform/user_form.html",
                                   user=user, institutions=institutions, action="edit")

        # Snapshot antes da mudança — útil para auditoria forense.
        before = {"email": user.email, "role": user.role,
                  "institution_id": user.institution_id, "active": user.active}

        user.email          = email
        user.name           = name
        user.role           = role
        user.institution_id = int(iid_raw) if role in ("client_admin", "operational") and iid_raw else None
        user.active         = "active" in request.form
        password_changed = False
        if password:
            user.set_password(password)
            # Se super_admin trocou a senha de outro usuário, força troca no
            # próximo login. Se trocou a propria, mantem normal.
            from flask_login import current_user as _cu
            if _cu.id != user.id:
                user.must_change_password = True
            # Reset lockout — se a senha foi resetada, o usuário pode entrar.
            user.failed_login_count = 0
            user.locked_until = None
            password_changed = True

        audit_log(
            ACTION_USER_UPDATE,
            resource_type="user", resource_id=user.id,
            details={
                "before": before,
                "after": {"email": email, "role": role,
                          "institution_id": user.institution_id,
                          "active": user.active},
                "password_changed": password_changed,
            },
        )
        db.session.commit()
        flash(f"Usuário '{user.name}' atualizado.", "success")
        return redirect(url_for("admin_platform.user_list"))

    return render_template("admin/platform/user_form.html",
                           user=user, institutions=institutions, action="edit")


@admin_platform_bp.route("/users/<int:uid>/delete", methods=["POST"])
@super_admin_required
def user_delete(uid):
    validate_csrf_token()
    user = User.query.get_or_404(uid)
    # Defesa: super_admin nao pode se auto-desativar (perderia acesso e
    # potencialmente derrubaria a unica conta privilegiada).
    from flask_login import current_user as _cu
    if user.id == _cu.id:
        flash("Você não pode desativar a própria conta.", "error")
        return redirect(url_for("admin_platform.user_list"))

    user.active = False  # soft delete — preserva AuthLog/AdminAuditLog
    audit_log(
        ACTION_USER_DELETE,
        resource_type="user", resource_id=user.id,
        details={"email": user.email, "name": user.name, "role": user.role},
    )
    db.session.commit()
    flash(f"Usuário '{user.name}' desativado.", "warning")
    return redirect(url_for("admin_platform.user_list"))


# ── Logs ───────────────────────────────────────────────────────────────────────

@admin_platform_bp.route("/logs")
@super_admin_required
def log_list():
    iid        = request.args.get("institution_id", type=int)
    log_type   = request.args.get("log_type", "ai")
    query_ai   = InteractionLog.query.order_by(InteractionLog.created_at.desc())
    if iid:
        query_ai = query_ai.filter_by(institution_id=iid)
    ai_logs      = query_ai.limit(200).all()
    auth_logs    = AuthLog.query.order_by(AuthLog.created_at.desc()).limit(100).all()
    institutions = Institution.query.order_by(Institution.name).all()
    return render_template(
        "admin/platform/log_list.html",
        ai_logs=ai_logs,
        auth_logs=auth_logs,
        institutions=institutions,
        active_iid=iid,
        log_type=log_type,
    )
