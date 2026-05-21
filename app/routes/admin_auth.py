"""Admin authentication: login, logout, troca obrigatoria de senha, 2FA TOTP.

Hardening aplicado:
  - Rate limit de IP (Flask-Limiter) — defesa de primeira camada.
  - Lockout por usuario apos N falhas — defesa contra brute-force distribuido
    (varios IPs atacando a mesma conta).
  - Timing-safe check mesmo quando o e-mail nao existe — nao vaza enumeracao.
  - Auditoria de toda tentativa (sucesso, falha, conta bloqueada, 2FA).
  - Forca troca de senha quando must_change_password=True.
  - 2FA TOTP: super_admin obrigatorio; opcional para client_admin. Login em
    duas etapas — senha primeiro, codigo TOTP (ou backup) depois. Estado
    intermediario fica na sessao via _pending_2fa_user_id, sem login_user.
"""
from datetime import datetime

from flask import (
    Blueprint, abort, current_app, flash, redirect, render_template,
    request, session, url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db, limiter
from app.helpers import (
    audit_log, generate_csrf_token, validate_csrf_token,
    validate_password_strength,
)
from app.models import AuthLog, User
from app.models.audit import (
    ACTION_2FA_BACKUP_REGEN, ACTION_2FA_BACKUP_USED, ACTION_2FA_DISABLED,
    ACTION_2FA_ENABLED, ACTION_2FA_FAIL,
    ACTION_LOGIN_FAIL, ACTION_LOGIN_LOCKED, ACTION_LOGIN_OK,
    ACTION_LOGOUT, ACTION_PASSWORD_CHANGE,
)
from app.twofa import (
    generate_backup_codes, generate_totp_secret, provisioning_uri,
    qr_code_data_uri, verify_totp,
)

auth_bp = Blueprint("auth", __name__)

# Hash de referencia para timing-safe check quando o e-mail nao existe.
_DUMMY_HASH = generate_password_hash("flexmedia-dummy-notreal-2024")


def _redirect_by_role(user: User):
    """Redireciona o usuario para o painel correto conforme sua role."""
    if user.is_super_admin:
        return redirect(url_for("admin_platform.dashboard"))
    return redirect(url_for("admin_institution.dashboard", iid=user.institution_id))


def _next_url_safe(default_redirect):
    """Sanitiza ?next= para evitar open redirect.

    So aceita paths internos do admin (sem '//' que poderia virar
    protocolo-relativo, sem espacos, sem caracteres de quebra).
    """
    next_url = request.args.get("next", "") or request.form.get("next", "")
    if (
        next_url
        and next_url.startswith("/admin")
        and not next_url.startswith("//")
        and "\\" not in next_url
        and "\n" not in next_url
        and " " not in next_url
    ):
        return redirect(next_url)
    return default_redirect


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("20 per minute; 100 per hour")
def login():
    if current_user.is_authenticated and current_user.active:
        if request.method == "GET":
            audit_log(ACTION_LOGOUT, actor=current_user, commit=True)
            logout_user()
            session.clear()
        elif current_user.must_change_password:
            return redirect(url_for("auth.change_password"))
        else:
            return _redirect_by_role(current_user)

    error = None

    if request.method == "POST":
        validate_csrf_token()

        email = (request.form.get("email", "") or "").strip().lower()
        password = request.form.get("password", "") or ""

        user = User.query.filter_by(email=email).first()

        # Timing-safe: sempre executa o check_password_hash, mesmo sem usuario.
        if user:
            password_ok = user.check_password(password)
        else:
            check_password_hash(_DUMMY_HASH, password)
            password_ok = False

        ip = request.remote_addr or "unknown"
        threshold = current_app.config.get("LOCKOUT_THRESHOLD", 5)
        lockout_minutes = current_app.config.get("LOCKOUT_MINUTES", 15)

        # Decisao em tres niveis:
        # 1. Conta existe e esta bloqueada → recusa, mesmo com senha certa.
        # 2. Senha errada → incrementa contador, talvez bloqueie.
        # 3. OK → reseta contador, autentica.
        locked = bool(user and user.is_locked())
        success = bool(user and user.active and password_ok and not locked)

        # AuthLog (registro tecnico) — uma linha por tentativa.
        db.session.add(AuthLog(
            email=email,
            user_id=user.id if user else None,
            success=success,
            ip_address=ip,
        ))

        if locked:
            # Mensagem genérica para nao confirmar que o e-mail existe.
            audit_log(
                ACTION_LOGIN_LOCKED,
                actor=user, actor_email=email,
                resource_type="user", resource_id=user.id,
                details={"locked_until": user.locked_until.isoformat()},
            )
            db.session.commit()
            error = "Credenciais invalidas."
        elif success:
            # Etapa 1 (senha) OK. Se o usuario ja tem 2FA, NAO chama login_user
            # ainda — guarda o id em sessao temporaria e redireciona para o
            # challenge. Sem 2FA confirmado, login_user nunca acontece.
            if user.has_totp:
                # Limpa qualquer pending anterior (login concorrente).
                session.pop("_pending_2fa_user_id", None)
                session["_pending_2fa_user_id"] = user.id
                session["_pending_2fa_at"] = datetime.utcnow().isoformat()
                # Preserva ?next= para pos-2FA.
                next_url = (request.args.get("next") or "").strip()
                if next_url:
                    session["_pending_2fa_next"] = next_url
                # Senha OK ainda nao zera o lockout — so apos o 2FA bater.
                db.session.commit()
                return redirect(url_for("auth.totp_challenge"))

            # Super_admin SEM 2FA configurado: NAO autentica ainda. Cria
            # sessao limitada (_pending_totp_setup_user_id) que so pode
            # acessar /admin/2fa/setup. Antes, dava login_user e dependia
            # do decorator empurrar para setup — se o atacante interrompesse
            # a navegacao, ja tinha sessao autenticada.
            if user.is_super_admin and not user.has_totp:
                session.pop("_pending_totp_setup_user_id", None)
                session["_pending_totp_setup_user_id"] = user.id
                session["_pending_totp_setup_at"] = datetime.utcnow().isoformat()
                user.register_successful_login()
                audit_log(
                    ACTION_LOGIN_OK,
                    actor=user, actor_email=email,
                    resource_type="user", resource_id=user.id,
                    details={"twofa": False, "pending_setup": True},
                )
                db.session.commit()
                flash("Configure a autenticacao de dois fatores antes de continuar.", "warning")
                return redirect(url_for("auth.totp_setup"))

            user.register_successful_login()
            audit_log(
                ACTION_LOGIN_OK,
                actor=user, actor_email=email,
                resource_type="user", resource_id=user.id,
                details={"twofa": False},
            )
            db.session.commit()
            login_user(user, remember=False)
            session["_login_at"] = datetime.utcnow().isoformat()

            if user.must_change_password:
                flash("Voce precisa definir uma nova senha antes de continuar.", "warning")
                return redirect(url_for("auth.change_password"))

            return _next_url_safe(_redirect_by_role(user))
        else:
            if user:
                user.register_failed_login(threshold, lockout_minutes)
            audit_log(
                ACTION_LOGIN_FAIL,
                actor=None, actor_email=email,
                resource_type="user",
                resource_id=user.id if user else None,
                details={"failed_count": user.failed_login_count if user else None},
            )
            db.session.commit()
            error = "Credenciais invalidas."

    return render_template("admin/login.html", error=error)


@auth_bp.route("/logout")
def logout():
    if current_user.is_authenticated:
        audit_log(ACTION_LOGOUT, actor=current_user, commit=True)
    logout_user()
    session.clear()
    flash("Sessao encerrada.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    """Troca de senha. Obrigatoria quando must_change_password=True."""
    error = None

    if request.method == "POST":
        validate_csrf_token()
        atual = request.form.get("current_password", "") or ""
        nova = request.form.get("new_password", "") or ""
        confirma = request.form.get("confirm_password", "") or ""

        if not current_user.check_password(atual):
            error = "Senha atual incorreta."
        elif nova != confirma:
            error = "As senhas nao conferem."
        else:
            erros = validate_password_strength(nova)
            if current_user.check_password(nova):
                erros.append("A nova senha deve ser diferente da atual.")
            if erros:
                error = " ".join(erros)
            else:
                current_user.set_password(nova)
                audit_log(
                    ACTION_PASSWORD_CHANGE,
                    actor=current_user,
                    resource_type="user",
                    resource_id=current_user.id,
                )
                db.session.commit()
                flash("Senha alterada com sucesso.", "success")
                return _redirect_by_role(current_user)

    return render_template("admin/change_password.html", error=error)


@auth_bp.route("/forgot-password")
def forgot_password():
    return render_template("admin/forgot_password.html")


# ─── 2FA TOTP ──────────────────────────────────────────────────────────────────
# Janela maxima entre senha-OK e codigo TOTP. Se o usuario demora demais,
# forcamos refazer o login. 5 min cobre confusao com o app autenticador
# sem deixar a sessao parcial pendurada.
_PENDING_2FA_MAX_SECONDS = 300

# Setup de TOTP de super_admin que ainda nao se autenticou. Janela maior
# (10 min) porque inclui escanear QR e digitar codigo.
_PENDING_SETUP_MAX_SECONDS = 600


def _clear_pending_2fa():
    session.pop("_pending_2fa_user_id", None)
    session.pop("_pending_2fa_at", None)
    session.pop("_pending_2fa_next", None)


def _clear_pending_setup():
    session.pop("_pending_totp_setup_user_id", None)
    session.pop("_pending_totp_setup_at", None)


def _load_pending_setup_user() -> User | None:
    """Recupera super_admin que passou na senha mas precisa configurar TOTP."""
    uid = session.get("_pending_totp_setup_user_id")
    started = session.get("_pending_totp_setup_at")
    if not uid or not started:
        return None
    try:
        started_dt = datetime.fromisoformat(started)
    except ValueError:
        _clear_pending_setup()
        return None
    if (datetime.utcnow() - started_dt).total_seconds() > _PENDING_SETUP_MAX_SECONDS:
        _clear_pending_setup()
        return None
    user = User.query.get(int(uid))
    if not user or not user.active or user.has_totp:
        _clear_pending_setup()
        return None
    return user


def _load_pending_2fa_user() -> User | None:
    """Recupera o usuario que passou pela senha mas ainda nao validou TOTP."""
    uid = session.get("_pending_2fa_user_id")
    started = session.get("_pending_2fa_at")
    if not uid or not started:
        return None
    try:
        started_dt = datetime.fromisoformat(started)
    except ValueError:
        _clear_pending_2fa()
        return None
    if (datetime.utcnow() - started_dt).total_seconds() > _PENDING_2FA_MAX_SECONDS:
        _clear_pending_2fa()
        return None
    user = User.query.get(int(uid))
    if not user or not user.active or not user.has_totp:
        _clear_pending_2fa()
        return None
    return user


@auth_bp.route("/2fa/challenge", methods=["GET", "POST"])
@limiter.limit("10 per minute; 30 per hour")
def totp_challenge():
    """Etapa 2 do login: valida codigo TOTP ou codigo de backup.

    Aceita codigo de 6 digitos (app autenticador) OU codigo de backup no
    formato xxxx-xxxx. Falhas contam para o lockout do usuario tambem,
    pois um atacante que descobriu a senha nao deve ter brute-force livre.
    """
    user = _load_pending_2fa_user()
    if not user:
        flash("Sessao expirada. Faca login novamente.", "info")
        return redirect(url_for("auth.login"))

    error = None
    if request.method == "POST":
        validate_csrf_token()
        code = (request.form.get("code", "") or "").strip()
        used_backup = False
        ok = False

        if len(code.replace("-", "").replace(" ", "")) == 6 and code.replace(" ", "").replace("-", "").isdigit():
            ok = verify_totp(user.totp_secret, code)
        else:
            ok = user.consume_backup_code(code)
            used_backup = ok

        threshold = current_app.config.get("LOCKOUT_THRESHOLD", 5)
        lockout_minutes = current_app.config.get("LOCKOUT_MINUTES", 15)

        if not ok:
            user.register_failed_login(threshold, lockout_minutes)
            audit_log(
                ACTION_2FA_FAIL,
                actor=user, actor_email=user.email,
                resource_type="user", resource_id=user.id,
                details={"failed_count": user.failed_login_count},
            )
            db.session.commit()
            # Conta acabou de bloquear na ultima falha — descarta pending.
            if user.is_locked():
                _clear_pending_2fa()
                flash("Muitas tentativas. Conta temporariamente bloqueada.", "error")
                return redirect(url_for("auth.login"))
            error = "Codigo invalido."
        else:
            user.register_successful_login()
            details = {"twofa": True, "backup": used_backup}
            if used_backup:
                details["remaining_backup_codes"] = user.remaining_backup_codes()
                audit_log(
                    ACTION_2FA_BACKUP_USED,
                    actor=user, actor_email=user.email,
                    resource_type="user", resource_id=user.id,
                    details=details,
                )
            audit_log(
                ACTION_LOGIN_OK,
                actor=user, actor_email=user.email,
                resource_type="user", resource_id=user.id,
                details=details,
            )
            db.session.commit()

            next_url = session.get("_pending_2fa_next") or ""
            _clear_pending_2fa()
            login_user(user, remember=False)
            session["_login_at"] = datetime.utcnow().isoformat()

            if used_backup and user.remaining_backup_codes() <= 2:
                flash(
                    "Voce usou um codigo de backup. "
                    f"Restam {user.remaining_backup_codes()}. Gere novos em breve.",
                    "warning",
                )

            if user.must_change_password:
                flash("Voce precisa definir uma nova senha antes de continuar.", "warning")
                return redirect(url_for("auth.change_password"))

            # Reaproveita _next_url_safe simulando ?next=
            if next_url and next_url.startswith("/admin") and not next_url.startswith("//"):
                return redirect(next_url)
            return _redirect_by_role(user)

    return render_template("admin/totp_challenge.html", error=error)


@auth_bp.route("/2fa/setup", methods=["GET", "POST"])
def totp_setup():
    """Configura 2FA: mostra QR + segredo, valida codigo, gera backup codes.

    Aceita dois caminhos:
      a) Usuario ja autenticado que esta optando por 2FA (client_admin).
      b) Super_admin que passou pela senha mas ainda nao tem TOTP — neste
         caso a sessao guarda _pending_totp_setup_user_id e o usuario nao
         esta logado (login_user so acontece apos confirmar o codigo).

    Usa um segredo provisorio guardado em sessao ate o usuario confirmar
    com um codigo valido. Ate la, totp_enabled fica False — e o segredo
    em sessao some se o usuario fechar a aba.
    """
    # Resolve qual usuario esta configurando.
    target_user = None
    via_pending = False
    if current_user.is_authenticated:
        target_user = current_user
    else:
        target_user = _load_pending_setup_user()
        via_pending = bool(target_user)

    if not target_user:
        flash("Sessao expirada. Faca login novamente.", "info")
        return redirect(url_for("auth.login"))

    if target_user.has_totp:
        flash("2FA ja esta ativado nesta conta.", "info")
        if current_user.is_authenticated:
            return _redirect_by_role(current_user)
        return redirect(url_for("auth.login"))

    # Segredo provisorio — so se torna definitivo apos confirmar.
    pending_secret = session.get("_2fa_pending_secret")
    if not pending_secret:
        pending_secret = generate_totp_secret()
        session["_2fa_pending_secret"] = pending_secret

    error = None

    if request.method == "POST":
        validate_csrf_token()
        code = (request.form.get("code", "") or "").strip()
        if not verify_totp(pending_secret, code):
            error = "Codigo invalido. Verifique o relogio do seu dispositivo."
        else:
            target_user.totp_secret = pending_secret
            target_user.totp_enabled = True
            target_user.totp_confirmed_at = datetime.utcnow()
            backup_codes_to_show = generate_backup_codes()
            target_user.set_backup_codes(backup_codes_to_show)
            audit_log(
                ACTION_2FA_ENABLED,
                actor=target_user,
                resource_type="user", resource_id=target_user.id,
            )
            db.session.commit()
            session.pop("_2fa_pending_secret", None)
            # Se chegamos via pending (super_admin sem auth), agora sim
            # autentica de fato — o 2FA acabou de ser confirmado.
            if via_pending:
                _clear_pending_setup()
                login_user(target_user, remember=False)
                session["_login_at"] = datetime.utcnow().isoformat()
            # Renderiza com os codigos em claro UMA UNICA VEZ.
            return render_template(
                "admin/totp_backup_codes.html",
                codes=backup_codes_to_show,
                first_time=True,
            )

    uri = provisioning_uri(pending_secret, target_user.email)
    qr = qr_code_data_uri(uri)
    return render_template(
        "admin/totp_setup.html",
        secret=pending_secret,
        qr_data_uri=qr,
        error=error,
    )


@auth_bp.route("/2fa/disable", methods=["POST"])
@login_required
def totp_disable():
    """Desativa 2FA. Exige senha atual — defesa contra session hijack.

    Super_admin nao pode desativar (politica). Em caso de dispositivo perdido,
    outro super_admin reseta via interface administrativa.
    """
    validate_csrf_token()
    if current_user.is_super_admin:
        flash("Super administrador nao pode desativar 2FA.", "error")
        return _redirect_by_role(current_user)
    senha = request.form.get("password", "") or ""
    if not current_user.check_password(senha):
        flash("Senha incorreta.", "error")
        return _redirect_by_role(current_user)
    current_user.disable_totp()
    audit_log(
        ACTION_2FA_DISABLED,
        actor=current_user,
        resource_type="user", resource_id=current_user.id,
    )
    db.session.commit()
    flash("2FA desativado.", "info")
    return _redirect_by_role(current_user)


@auth_bp.route("/2fa/backup-codes", methods=["GET", "POST"])
@login_required
def totp_backup_codes():
    """Regera codigos de backup. Exige senha (proxy de re-autenticacao)."""
    if not current_user.has_totp:
        return redirect(url_for("auth.totp_setup"))

    if request.method == "POST":
        validate_csrf_token()
        senha = request.form.get("password", "") or ""
        if not current_user.check_password(senha):
            flash("Senha incorreta.", "error")
            return redirect(url_for("auth.totp_backup_codes"))
        novos = generate_backup_codes()
        current_user.set_backup_codes(novos)
        audit_log(
            ACTION_2FA_BACKUP_REGEN,
            actor=current_user,
            resource_type="user", resource_id=current_user.id,
        )
        db.session.commit()
        return render_template(
            "admin/totp_backup_codes.html",
            codes=novos,
            first_time=False,
        )

    return render_template(
        "admin/totp_backup_codes_regen.html",
        remaining=current_user.remaining_backup_codes(),
    )
