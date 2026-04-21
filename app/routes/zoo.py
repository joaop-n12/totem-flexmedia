"""Zoo module routes: species, animal list, animal detail."""
from flask import Blueprint, render_template, abort, request
from app.models import Animal
from app.helpers import load_institution, require_module

zoo_bp = Blueprint("zoo", __name__)


@zoo_bp.route("/<slug>/animais")
@require_module("animais")
def especies(slug):
    """Species selector — groups animals by especie."""
    inst = load_institution(slug)
    animals = Animal.query.filter_by(institution_id=inst.id).all()

    especies_map: dict = {}
    for a in animals:
        key = a.especie_slug or "outros"
        if key not in especies_map:
            especies_map[key] = {
                "nome": a.especie or "Outros",
                "slug": key,
                "count": 0,
                "imagem": a.imagem,
            }
        especies_map[key]["count"] += 1

    especies = sorted(especies_map.values(), key=lambda x: x["nome"])
    return render_template("modules/zoo/especies.html",
                           institution=inst, especies=especies)


@zoo_bp.route("/<slug>/animais/<especie_slug>")
@require_module("animais")
def animais_lista(slug, especie_slug):
    """Animals filtered by species."""
    inst = load_institution(slug)
    q = (request.args.get("q") or "").strip().lower()
    animais = Animal.query.filter_by(institution_id=inst.id, especie_slug=especie_slug).all()

    if not animais:
        abort(404)

    especie_nome = animais[0].especie
    if q:
        animais = [a for a in animais if q in a.nome.lower()]

    return render_template("modules/zoo/lista.html",
                           institution=inst,
                           animais=animais,
                           especie_nome=especie_nome,
                           especie_slug=especie_slug,
                           q=request.args.get("q", ""))


@zoo_bp.route("/<slug>/animal/<animal_slug>")
@require_module("animais")
def animal_detalhe(slug, animal_slug):
    """Single animal detail page."""
    inst = load_institution(slug)
    animal = Animal.query.filter_by(institution_id=inst.id, slug=animal_slug).first_or_404()
    return render_template("modules/zoo/detalhe.html",
                           institution=inst, animal=animal)


@zoo_bp.route("/<slug>/animais/area/<area_slug>")
@require_module("animais")
def animais_por_area(slug, area_slug):
    """Animals filtered by map area."""
    inst = load_institution(slug)
    q = (request.args.get("q") or "").strip().lower()
    animais = Animal.query.filter_by(institution_id=inst.id, area=area_slug).all()

    if not animais:
        # Área sem animais cadastrados → vai para o catálogo geral
        from flask import redirect, url_for
        return redirect(url_for("zoo.catalogo", slug=slug))

    area_nome = area_slug.replace("-", " ").title()
    if q:
        animais = [a for a in animais if q in a.nome.lower()]

    return render_template("modules/zoo/lista.html",
                           institution=inst,
                           animais=animais,
                           especie_nome=area_nome,
                           especie_slug=area_slug,
                           q=request.args.get("q", ""))


@zoo_bp.route("/<slug>/catalogo")
@require_module("animais")
def catalogo(slug):
    """Full animal catalog with client-side filtering."""
    inst = load_institution(slug)
    animais = Animal.query.filter_by(institution_id=inst.id).all()

    especies = sorted({(a.especie, a.especie_slug) for a in animais if a.especie},
                      key=lambda x: x[0])
    habitats = sorted({a.habitat for a in animais if a.habitat})

    return render_template("modules/zoo/catalogo.html",
                           institution=inst,
                           animais=animais,
                           especies=especies,
                           habitats=habitats)
