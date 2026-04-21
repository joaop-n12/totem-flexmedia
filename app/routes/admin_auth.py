"""Admin authentication: login, logout, forgot-password."""
from datetime import datetime

from flask import (
    Blueprint, flash, redirect, render_template,
    request, url_for,
)
from flask_login import current_user, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db, limiter
from app.helpers import generate_csrf_token, validate_csrf_token
from app.models import AuthLog, User

auth_bp = Blueprint("auth", __name__)

# Hash de referência para timing-safe check quando o e-mail não existe
_DUMMY_HASH = generate_password_hash("flexmedia-dummy-notreal-2024")


def _redirect_by_role(user: User):
    """Redireciona o usuário para o painel correto conforme sua role."""
    if user.is_super_admin:
        return redirect(url_for("admin_platform.dashboard"))
    return redirect(url_for("admin_institution.dashboard", iid=user.institution_id))


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("20 per minute; 100 per hour")
def login():
    if current_user.is_authenticated and current_user.active:
        return _redirect_by_role(current_user)

    error = None

    if request.method == "POST":
        validate_csrf_token()

        email = (request.form.get("email", "") or "").strip().lower()
        password = request.form.get("password", "") or ""

        user = User.query.filter_by(email=email).first()

        # Timing-safe: checa senha mesmo quando o usuário não existe
        if user:
            ok = user.check_password(password)
        else:
            check_password_hash(_DUMMY_HASH, password)
            ok = False

        ip = request.remote_addr or "unknown"
        logged_in = ok and user is not None and user.active

        db.session.add(AuthLog(
            email=email,
            user_id=user.id if user else None,
            success=logged_in,
            ip_address=ip,
        ))
        db.session.commit()

        if logged_in:
            user.last_login_at = datetime.utcnow()
            db.session.commit()
            login_user(user, remember=False)

            # Previne open redirect: só aceita paths internos do admin
            next_url = request.args.get("next", "")
            if next_url and next_url.startswith("/admin") and " " not in next_url:
                return redirect(next_url)
            return _redirect_by_role(user)

        error = "Credenciais inválidas."

    return render_template("admin/login.html", error=error)


@auth_bp.route("/logout")
def logout():
    logout_user()
    flash("Sessão encerrada.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/forgot-password")
def forgot_password():
    return render_template("admin/forgot_password.html")
