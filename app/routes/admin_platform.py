"""Admin platform: dashboard global, CRUD de instituições e usuários (super_admin)."""
from flask import (
    Blueprint, flash, redirect, render_template,
    request, url_for,
)

from app.extensions import db
from app.helpers import (
    allowed_file, save_upload, slugify,
    super_admin_required, validate_csrf_token,
)
from app.models import (
    AuthLog, Institution, InteractionLog,
    Module, InstitutionModule, User,
)

admin_platform_bp = Blueprint("admin_platform", __name__)


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
    recent_auth  = AuthLog.query.order_by(AuthLog.created_at.desc()).limit(10).all()
    return render_template(
        "admin/platform/dashboard.html",
        stats=stats,
        institutions=institutions,
        recent_logs=recent_logs,
        recent_auth=recent_auth,
    )


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
            ai_name         = request.form.get("ai_name", "Assistente"),
            ai_context      = request.form.get("ai_context", ""),
            daily_ai_quota  = max(0, int(request.form.get("daily_ai_quota") or 500)),
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
                order = int(request.form.get(f"order_{mod.slug}", 99))
                db.session.add(InstitutionModule(
                    institution_id=inst.id,
                    module_slug=mod.slug,
                    enabled=True,
                    order=order,
                ))

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
        inst.ai_name         = request.form.get("ai_name", "Assistente")
        inst.ai_context      = request.form.get("ai_context", "")
        inst.daily_ai_quota  = max(0, int(request.form.get("daily_ai_quota") or inst.daily_ai_quota or 500))
        inst.active          = "active" in request.form

        logo = request.files.get("logo")
        if logo and logo.filename and allowed_file(logo.filename):
            ext = logo.filename.rsplit(".", 1)[1].lower()
            inst.logo_path = save_upload(logo, inst.slug, f"logo.{ext}")

        enabled_slugs = set(request.form.getlist("modules"))
        existing = {m.module_slug: m for m in inst.modules}

        for mod in modules:
            if mod.slug in enabled_slugs:
                order = int(request.form.get(f"order_{mod.slug}", 99))
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
        if len(password) < 10:
            errors.append("Senha deve ter ao menos 10 caracteres.")
        if role not in ("super_admin", "client_admin"):
            errors.append("Role inválida.")
        if role == "client_admin" and not iid_raw:
            errors.append("Client admin deve ter uma instituição vinculada.")
        if User.query.filter_by(email=email).first():
            errors.append("E-mail já cadastrado.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("admin/platform/user_form.html",
                                   user=None, institutions=institutions, action="new")

        institution_id = int(iid_raw) if iid_raw else None
        user = User(
            email=email,
            name=name,
            role=role,
            institution_id=institution_id,
            active=True,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash(f"Usuário '{name}' criado.", "success")
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
        if role not in ("super_admin", "client_admin"):
            errors.append("Role inválida.")
        if role == "client_admin" and not iid_raw:
            errors.append("Client admin deve ter uma instituição vinculada.")
        conflict = User.query.filter(User.email == email, User.id != uid).first()
        if conflict:
            errors.append("E-mail já usado por outro usuário.")
        if password and len(password) < 10:
            errors.append("Nova senha deve ter ao menos 10 caracteres.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("admin/platform/user_form.html",
                                   user=user, institutions=institutions, action="edit")

        user.email          = email
        user.name           = name
        user.role           = role
        user.institution_id = int(iid_raw) if iid_raw else None
        user.active         = "active" in request.form
        if password:
            user.set_password(password)

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
    user.active = False  # soft delete — preserva AuthLog
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
