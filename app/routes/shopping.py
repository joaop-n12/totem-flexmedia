"""Shopping module routes: store catalog."""
from flask import Blueprint, render_template, request
from app.models import Store
from app.helpers import load_institution, require_module

shopping_bp = Blueprint("shopping", __name__)


@shopping_bp.route("/<slug>/lojas")
@require_module("lojas")
def lojas(slug):
    inst = load_institution(slug)
    q = (request.args.get("q") or "").strip().lower()
    category = request.args.get("categoria", "")

    stores = Store.query.filter_by(institution_id=inst.id).all()
    categories = sorted({s.category for s in stores if s.category})

    if q:
        stores = [s for s in stores if q in s.name.lower() or q in (s.description or "").lower()]
    if category:
        stores = [s for s in stores if s.category == category]

    return render_template("modules/shopping/lojas.html",
                           institution=inst,
                           stores=stores,
                           categories=categories,
                           q=request.args.get("q", ""),
                           active_category=category)


@shopping_bp.route("/<slug>/lojas/<loja_slug>")
@require_module("lojas")
def loja_detalhe(slug, loja_slug):
    inst = load_institution(slug)
    store = Store.query.filter_by(institution_id=inst.id, slug=loja_slug).first_or_404()
    return render_template("modules/shopping/loja_detalhe.html",
                           institution=inst, store=store)
