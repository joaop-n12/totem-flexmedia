"""Fluxo leve usado pelo instalador/operador para iniciar um Totem."""
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_login import current_user

from app.helpers import validate_csrf_token
from app.models import Institution, TotemDevice


operational_bp = Blueprint("operational", __name__)


def operational_required(view):
    """Autoriza exclusivamente contas operacionais ativas."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.active:
            return redirect(url_for("auth.login", next=request.path))
        if not current_user.is_operational:
            abort(403)
        return view(*args, **kwargs)
    return wrapper


@operational_bp.route("/", methods=["GET", "POST"])
@operational_required
def select_totem():
    """Seleciona um dispositivo ativo e abre a interface Totem existente."""
    devices = (
        TotemDevice.query.join(Institution)
        .filter(
            TotemDevice.status == "active",
            Institution.active.is_(True),
            TotemDevice.institution_id == current_user.institution_id,
        )
        .order_by(Institution.name, TotemDevice.name)
        .all()
    )
    institution = Institution.query.filter_by(
        id=current_user.institution_id, active=True
    ).first()
    institutions = [institution] if institution else []

    if request.method == "POST":
        validate_csrf_token()
        device_id = request.form.get("device_id", type=int)
        device = TotemDevice.query.filter_by(
            id=device_id,
            status="active",
            institution_id=current_user.institution_id,
        ).first()
        if not device or not device.institution or not device.institution.active:
            flash("Selecione um Totem ativo.", "error")
        else:
            session["operational_device_id"] = device.id
            session.permanent = True
            return redirect(url_for("core.home", slug=device.institution.slug))

    selected_id = session.get("operational_device_id")
    selected = next((device for device in devices if device.id == selected_id), None)
    return render_template(
        "operational/select_totem.html",
        institutions=institutions,
        devices=devices,
        selected=selected,
    )


@operational_bp.route("/iniciar")
@operational_required
def start_totem():
    """Reabre o Totem persistido, quando ele ainda e valido."""
    device = TotemDevice.query.filter_by(
        id=session.get("operational_device_id"),
        status="active",
        institution_id=current_user.institution_id,
    ).first()
    if not device or not device.institution or not device.institution.active:
        session.pop("operational_device_id", None)
        return redirect(url_for("operational.select_totem"))
    return redirect(url_for("core.home", slug=device.institution.slug))
