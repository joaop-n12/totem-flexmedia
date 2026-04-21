"""Pharmacy module routes: product catalog."""
from flask import Blueprint, render_template, request
from app.models import Product
from app.helpers import load_institution, require_module

pharmacy_bp = Blueprint("pharmacy", __name__)


@pharmacy_bp.route("/<slug>/produtos")
@require_module("produtos")
def produtos(slug):
    inst = load_institution(slug)
    q = (request.args.get("q") or "").strip().lower()
    category = request.args.get("categoria", "")
    on_sale = request.args.get("promocao") == "1"

    items = Product.query.filter_by(institution_id=inst.id).all()
    categories = sorted({p.category for p in items if p.category})

    if q:
        items = [p for p in items if q in p.name.lower() or q in (p.description or "").lower()]
    if category:
        items = [p for p in items if p.category == category]
    if on_sale:
        items = [p for p in items if p.on_sale]

    return render_template("modules/pharmacy/produtos.html",
                           institution=inst,
                           products=items,
                           categories=categories,
                           q=request.args.get("q", ""),
                           active_category=category,
                           on_sale=on_sale)
