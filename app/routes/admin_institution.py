"""Admin institution: CRUD de conteúdo por tenant (animais, eventos, lojas, produtos, FAQs, logs)."""
import unicodedata

from flask import (
    Blueprint, abort, flash, redirect, render_template,
    request, url_for,
)
from flask_login import current_user

from app.extensions import db
from app.helpers import (
    allowed_file, bump_content_version, client_admin_required, save_upload,
    tenant_get_or_404, tenant_query, validate_csrf_token,
)
from app.models import (
    Animal, Event, FAQ, Institution, InteractionLog,
    MapArea, Product, QuizQuestion, Store,
)
from app.models.quiz import (
    MAX_OPTIONS, MIN_OPTIONS, MAX_OPTION_LEN, MAX_QUESTION_LEN,
)

admin_institution_bp = Blueprint("admin_institution", __name__)


def _is_food_store(store):
    text = unicodedata.normalize("NFKD", " ".join((store.name or "", store.category or "", store.description or "")).lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    return any(word in text for word in ("aliment", "restaurante", "food", "praca", "lanchonete", "cafe", "cafeteria", "sorvete", "pizza", "hamburguer", "burger", "doces", "acai", "suco"))


def _save_store_logo(store, inst):
    logo = request.files.get("logo")
    if logo and logo.filename and allowed_file(logo.filename):
        ext = logo.filename.rsplit(".", 1)[1].lower()
        store.logo_path = save_upload(
            logo, f"{inst.slug}/stores/{store.slug}", f"logo.{ext}"
        )


def _map_coordinate(raw):
    raw = (raw or "").strip().replace(",", ".")
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return "invalid"
    return value if 0 <= value <= 100 else "invalid"


def _store_map_fields(store):
    x_pos = _map_coordinate(request.form.get("x_pos"))
    y_pos = _map_coordinate(request.form.get("y_pos"))
    if x_pos == "invalid" or y_pos == "invalid" or ((x_pos is None) != (y_pos is None)):
        flash("Informe as duas coordenadas entre 0 e 100, ou deixe ambas vazias.", "error")
        return False
    store.floor = (request.form.get("floor") or "Terreo").strip()
    store.unit_code = (request.form.get("unit_code") or "").strip() or None
    store.x_pos, store.y_pos = x_pos, y_pos
    return True


@admin_institution_bp.route("/institutions/<int:iid>/map-points")
@client_admin_required
def map_point_list(iid):
    inst = Institution.query.get_or_404(iid)
    points = MapArea.query.filter_by(institution_id=iid).order_by(MapArea.floor, MapArea.category, MapArea.name).all()
    return render_template("admin/institution/map_points.html", inst=inst, points=points)


@admin_institution_bp.route("/institutions/<int:iid>/map-points/new", methods=["GET", "POST"])
@client_admin_required
def map_point_new(iid):
    inst = Institution.query.get_or_404(iid)
    if request.method == "POST":
        validate_csrf_token()
        x_pos, y_pos = _map_coordinate(request.form.get("x_pos")), _map_coordinate(request.form.get("y_pos"))
        if x_pos == "invalid" or y_pos == "invalid" or x_pos is None or y_pos is None:
            flash("Informe a posição X e Y entre 0 e 100 para o ponto.", "error")
        else:
            point = MapArea(institution_id=iid, name=request.form["name"].strip(),
                            description=request.form.get("description", "").strip(),
                            floor=(request.form.get("floor") or "Terreo").strip(),
                            category=(request.form.get("category") or "Servicos").strip(),
                            icon=(request.form.get("icon") or "•").strip()[:10],
                            x_pos=x_pos, y_pos=y_pos)
            point.generate_slug()
            db.session.add(point)
            bump_content_version(iid)
            db.session.commit()
            flash("Ponto de interesse cadastrado.", "success")
            return redirect(url_for("admin_institution.map_point_list", iid=iid))
    return render_template("admin/institution/map_point_form.html", inst=inst, point=None)


@admin_institution_bp.route("/institutions/<int:iid>/map-points/<int:mid>/edit", methods=["GET", "POST"])
@client_admin_required
def map_point_edit(iid, mid):
    inst = Institution.query.get_or_404(iid)
    point = tenant_get_or_404(MapArea, mid, iid)
    if request.method == "POST":
        validate_csrf_token()
        x_pos, y_pos = _map_coordinate(request.form.get("x_pos")), _map_coordinate(request.form.get("y_pos"))
        if x_pos == "invalid" or y_pos == "invalid" or x_pos is None or y_pos is None:
            flash("Informe a posição X e Y entre 0 e 100 para o ponto.", "error")
        else:
            point.name = request.form["name"].strip()
            point.description = request.form.get("description", "").strip()
            point.floor = (request.form.get("floor") or "Terreo").strip()
            point.category = (request.form.get("category") or "Servicos").strip()
            point.icon = (request.form.get("icon") or "•").strip()[:10]
            point.x_pos, point.y_pos = x_pos, y_pos
            point.generate_slug()
            bump_content_version(iid)
            db.session.commit()
            flash("Ponto de interesse atualizado.", "success")
            return redirect(url_for("admin_institution.map_point_list", iid=iid))
    return render_template("admin/institution/map_point_form.html", inst=inst, point=point)


@admin_institution_bp.route("/institutions/<int:iid>/map-points/<int:mid>/delete", methods=["POST"])
@client_admin_required
def map_point_delete(iid, mid):
    validate_csrf_token()
    point = tenant_get_or_404(MapArea, mid, iid)
    db.session.delete(point)
    bump_content_version(iid)
    db.session.commit()
    flash("Ponto de interesse removido.", "warning")
    return redirect(url_for("admin_institution.map_point_list", iid=iid))


@admin_institution_bp.route("/institutions/<int:iid>/food")
@client_admin_required
def food_list(iid):
    inst = Institution.query.get_or_404(iid)
    stores = Store.query.filter_by(institution_id=iid).order_by(Store.name).all()
    food_stores = [store for store in stores if _is_food_store(store)]
    return render_template("admin/institution/food_list.html", inst=inst, stores=food_stores)


@admin_institution_bp.route("/institutions/<int:iid>/food/new", methods=["GET", "POST"])
@client_admin_required
def food_new(iid):
    inst = Institution.query.get_or_404(iid)
    if request.method == "POST":
        validate_csrf_token()
        store = Store(institution_id=iid, name=request.form["name"].strip(),
                      category=request.form.get("category", "Alimentacao").strip() or "Alimentacao",
                      floor=request.form.get("floor", "Piso 2"),
                      description=request.form.get("description", "").strip(),
                      hours=request.form.get("hours", "").strip(),
                      phone=request.form.get("phone", "").strip())
        if not _store_map_fields(store):
            return render_template("admin/institution/food_form.html", inst=inst, store=store)
        store.generate_slug()
        _save_store_logo(store, inst)
        db.session.add(store)
        bump_content_version(iid)
        db.session.commit()
        flash(f"Ponto de alimentacao '{store.name}' adicionado.", "success")
        return redirect(url_for("admin_institution.food_list", iid=iid))
    return render_template("admin/institution/food_form.html", inst=inst, store=None)


@admin_institution_bp.route("/institutions/<int:iid>/food/<int:sid>/edit", methods=["GET", "POST"])
@client_admin_required
def food_edit(iid, sid):
    inst = Institution.query.get_or_404(iid)
    store = tenant_get_or_404(Store, sid, iid)
    if not _is_food_store(store):
        from flask import abort
        abort(404)
    if request.method == "POST":
        validate_csrf_token()
        store.name = request.form["name"].strip()
        store.category = request.form.get("category", "Alimentacao").strip() or "Alimentacao"
        store.floor = request.form.get("floor", "Piso 2")
        store.description = request.form.get("description", "").strip()
        store.hours = request.form.get("hours", "").strip()
        store.phone = request.form.get("phone", "").strip()
        if not _store_map_fields(store):
            return render_template("admin/institution/food_form.html", inst=inst, store=store)
        store.generate_slug()
        _save_store_logo(store, inst)
        bump_content_version(iid)
        db.session.commit()
        flash(f"Ponto de alimentacao '{store.name}' atualizado.", "success")
        return redirect(url_for("admin_institution.food_list", iid=iid))
    return render_template("admin/institution/food_form.html", inst=inst, store=store)


@admin_institution_bp.route("/institutions/<int:iid>/food/<int:sid>/delete", methods=["POST"])
@client_admin_required
def food_delete(iid, sid):
    validate_csrf_token()
    store = tenant_get_or_404(Store, sid, iid)
    if not _is_food_store(store):
        from flask import abort
        abort(404)
    db.session.delete(store)
    bump_content_version(iid)
    db.session.commit()
    flash("Ponto de alimentacao removido.", "warning")
    return redirect(url_for("admin_institution.food_list", iid=iid))


# ── Root redirect ──────────────────────────────────────────────────────────────

@admin_institution_bp.route("/")
def index():
    """Redireciona para o painel correto conforme a role do usuário."""
    if not current_user.is_authenticated or not current_user.active:
        return redirect(url_for("auth.login"))
    if current_user.is_super_admin:
        return redirect(url_for("admin_platform.dashboard"))
    if current_user.is_operational:
        return redirect(url_for("operational.select_totem"))
    return redirect(url_for("admin_institution.dashboard",
                            iid=current_user.institution_id))


# ── Dashboard da instituição ───────────────────────────────────────────────────

@admin_institution_bp.route("/institutions/<int:iid>/")
@client_admin_required
def dashboard(iid):
    inst  = Institution.query.get_or_404(iid)
    stats = {
        "animals":  Animal.query.filter_by(institution_id=iid).count(),
        "events":   Event.query.filter_by(institution_id=iid).count(),
        "stores":   Store.query.filter_by(institution_id=iid).count(),
        "products": Product.query.filter_by(institution_id=iid).count(),
        "faqs":     FAQ.query.filter_by(institution_id=iid).count(),
        "logs":     InteractionLog.query.filter_by(institution_id=iid).count(),
    }
    recent_logs = (
        InteractionLog.query
        .filter_by(institution_id=iid)
        .order_by(InteractionLog.created_at.desc())
        .limit(8).all()
    )
    return render_template("admin/institution/dashboard.html",
                           inst=inst, stats=stats, recent_logs=recent_logs)


# ── Animals ────────────────────────────────────────────────────────────────────

@admin_institution_bp.route("/institutions/<int:iid>/animals")
@client_admin_required
def animal_list(iid):
    inst    = Institution.query.get_or_404(iid)
    animals = (Animal.query
               .filter_by(institution_id=iid)
               .order_by(Animal.especie, Animal.nome).all())
    return render_template("admin/institution/content_animals.html",
                           inst=inst, animals=animals)


@admin_institution_bp.route("/institutions/<int:iid>/animals/new", methods=["GET", "POST"])
@client_admin_required
def animal_new(iid):
    inst = Institution.query.get_or_404(iid)
    if request.method == "POST":
        validate_csrf_token()
        a = Animal(
            institution_id=iid,
            nome         = request.form["nome"],
            especie      = request.form.get("especie", ""),
            habitat      = request.form.get("habitat", ""),
            area         = request.form.get("area", ""),
            descricao    = request.form.get("descricao", ""),
            alimentacao  = request.form.get("alimentacao", ""),
            curiosidades = request.form.get("curiosidades", ""),
            conservacao  = request.form.get("conservacao", ""),
        )
        a.generate_slug()
        img = request.files.get("imagem")
        if img and img.filename and allowed_file(img.filename):
            ext = img.filename.rsplit(".", 1)[1].lower()
            a.imagem = save_upload(img, f"{inst.slug}/animals", f"{a.slug}.{ext}")
        db.session.add(a)
        bump_content_version(iid)
        db.session.commit()
        flash(f"Animal '{a.nome}' adicionado.", "success")
        return redirect(url_for("admin_institution.animal_list", iid=iid))
    return render_template("admin/institution/animal_form.html", inst=inst, animal=None)


@admin_institution_bp.route("/institutions/<int:iid>/animals/<int:aid>/edit",
                             methods=["GET", "POST"])
@client_admin_required
def animal_edit(iid, aid):
    inst   = Institution.query.get_or_404(iid)
    # filter_by garante que o animal pertence à instituição correta (isolamento de tenant)
    animal = tenant_get_or_404(Animal, aid, iid)
    if request.method == "POST":
        validate_csrf_token()
        animal.nome         = request.form["nome"]
        animal.especie      = request.form.get("especie", "")
        animal.habitat      = request.form.get("habitat", "")
        animal.area         = request.form.get("area", "")
        animal.descricao    = request.form.get("descricao", "")
        animal.alimentacao  = request.form.get("alimentacao", "")
        animal.curiosidades = request.form.get("curiosidades", "")
        animal.conservacao  = request.form.get("conservacao", "")
        animal.generate_slug()
        img = request.files.get("imagem")
        if img and img.filename and allowed_file(img.filename):
            ext = img.filename.rsplit(".", 1)[1].lower()
            animal.imagem = save_upload(img, f"{inst.slug}/animals", f"{animal.slug}.{ext}")
        bump_content_version(iid)
        db.session.commit()
        flash(f"Animal '{animal.nome}' atualizado.", "success")
        return redirect(url_for("admin_institution.animal_list", iid=iid))
    return render_template("admin/institution/animal_form.html", inst=inst, animal=animal)


@admin_institution_bp.route("/institutions/<int:iid>/animals/<int:aid>/delete",
                             methods=["POST"])
@client_admin_required
def animal_delete(iid, aid):
    validate_csrf_token()
    animal = tenant_get_or_404(Animal, aid, iid)
    db.session.delete(animal)
    bump_content_version(iid)
    db.session.commit()
    flash("Animal removido.", "warning")
    return redirect(url_for("admin_institution.animal_list", iid=iid))


# ── Events ─────────────────────────────────────────────────────────────────────

@admin_institution_bp.route("/institutions/<int:iid>/events")
@client_admin_required
def event_list(iid):
    inst   = Institution.query.get_or_404(iid)
    events = (Event.query
              .filter_by(institution_id=iid)
              .order_by(Event.horario).all())
    return render_template("admin/institution/content_events.html",
                           inst=inst, events=events)


@admin_institution_bp.route("/institutions/<int:iid>/events/new", methods=["GET", "POST"])
@client_admin_required
def event_new(iid):
    inst = Institution.query.get_or_404(iid)
    if request.method == "POST":
        validate_csrf_token()
        ev = Event(
            institution_id=iid,
            evento    = request.form["evento"],
            horario   = request.form.get("horario", ""),
            local     = request.form.get("local", ""),
            descricao = request.form.get("descricao", ""),
            active    = "active" in request.form,
        )
        db.session.add(ev)
        bump_content_version(iid)
        db.session.commit()
        flash(f"Evento '{ev.evento}' adicionado.", "success")
        return redirect(url_for("admin_institution.event_list", iid=iid))
    return render_template("admin/institution/event_form.html", inst=inst, event=None)


@admin_institution_bp.route("/institutions/<int:iid>/events/<int:eid>/edit",
                             methods=["GET", "POST"])
@client_admin_required
def event_edit(iid, eid):
    inst  = Institution.query.get_or_404(iid)
    event = tenant_get_or_404(Event, eid, iid)
    if request.method == "POST":
        validate_csrf_token()
        event.evento    = request.form["evento"]
        event.horario   = request.form.get("horario", "")
        event.local     = request.form.get("local", "")
        event.descricao = request.form.get("descricao", "")
        event.active    = "active" in request.form
        bump_content_version(iid)
        db.session.commit()
        flash(f"Evento '{event.evento}' atualizado.", "success")
        return redirect(url_for("admin_institution.event_list", iid=iid))
    return render_template("admin/institution/event_form.html", inst=inst, event=event)


@admin_institution_bp.route("/institutions/<int:iid>/events/<int:eid>/delete",
                             methods=["POST"])
@client_admin_required
def event_delete(iid, eid):
    validate_csrf_token()
    event = tenant_get_or_404(Event, eid, iid)
    db.session.delete(event)
    bump_content_version(iid)
    db.session.commit()
    flash("Evento removido.", "warning")
    return redirect(url_for("admin_institution.event_list", iid=iid))


# ── Stores ─────────────────────────────────────────────────────────────────────

@admin_institution_bp.route("/institutions/<int:iid>/stores")
@client_admin_required
def store_list(iid):
    inst   = Institution.query.get_or_404(iid)
    stores = (Store.query
              .filter_by(institution_id=iid)
              .order_by(Store.name).all())
    return render_template("admin/institution/content_stores.html",
                           inst=inst, stores=stores)


@admin_institution_bp.route("/institutions/<int:iid>/stores/new", methods=["GET", "POST"])
@client_admin_required
def store_new(iid):
    inst = Institution.query.get_or_404(iid)
    if request.method == "POST":
        validate_csrf_token()
        s = Store(
            institution_id=iid,
            name         = request.form["name"],
            category     = request.form.get("category", ""),
            floor        = request.form.get("floor", ""),
            description  = request.form.get("description", ""),
            hours        = request.form.get("hours", ""),
            phone        = request.form.get("phone", ""),
            on_promotion = "on_promotion" in request.form,
            promo_text   = request.form.get("promo_text", ""),
        )
        if not _store_map_fields(s):
            return render_template("admin/institution/store_form.html", inst=inst, store=s)
        s.generate_slug()
        _save_store_logo(s, inst)
        db.session.add(s)
        bump_content_version(iid)
        db.session.commit()
        flash(f"Loja '{s.name}' adicionada.", "success")
        return redirect(url_for("admin_institution.store_list", iid=iid))
    return render_template("admin/institution/store_form.html", inst=inst, store=None)


@admin_institution_bp.route("/institutions/<int:iid>/stores/<int:sid>/edit",
                             methods=["GET", "POST"])
@client_admin_required
def store_edit(iid, sid):
    inst  = Institution.query.get_or_404(iid)
    store = tenant_get_or_404(Store, sid, iid)
    if request.method == "POST":
        validate_csrf_token()
        store.name         = request.form["name"]
        store.category     = request.form.get("category", "")
        store.floor        = request.form.get("floor", "")
        store.description  = request.form.get("description", "")
        store.hours        = request.form.get("hours", "")
        store.phone        = request.form.get("phone", "")
        store.on_promotion = "on_promotion" in request.form
        store.promo_text   = request.form.get("promo_text", "")
        if not _store_map_fields(store):
            return render_template("admin/institution/store_form.html", inst=inst, store=store)
        store.generate_slug()
        _save_store_logo(store, inst)
        bump_content_version(iid)
        db.session.commit()
        flash(f"Loja '{store.name}' atualizada.", "success")
        return redirect(url_for("admin_institution.store_list", iid=iid))
    return render_template("admin/institution/store_form.html", inst=inst, store=store)


@admin_institution_bp.route("/institutions/<int:iid>/stores/<int:sid>/delete",
                             methods=["POST"])
@client_admin_required
def store_delete(iid, sid):
    validate_csrf_token()
    store = tenant_get_or_404(Store, sid, iid)
    db.session.delete(store)
    bump_content_version(iid)
    db.session.commit()
    flash("Loja removida.", "warning")
    return redirect(url_for("admin_institution.store_list", iid=iid))


# ── Products ───────────────────────────────────────────────────────────────────

@admin_institution_bp.route("/institutions/<int:iid>/products")
@client_admin_required
def product_list(iid):
    inst     = Institution.query.get_or_404(iid)
    products = (Product.query
                .filter_by(institution_id=iid)
                .order_by(Product.category, Product.name).all())
    return render_template("admin/institution/content_products.html",
                           inst=inst, products=products)


@admin_institution_bp.route("/institutions/<int:iid>/products/new", methods=["GET", "POST"])
@client_admin_required
def product_new(iid):
    inst = Institution.query.get_or_404(iid)
    if request.method == "POST":
        validate_csrf_token()
        try:
            price      = float(request.form.get("price") or 0)
            sale_price = float(request.form.get("sale_price") or 0)
        except ValueError:
            flash("Preço inválido. Use números (ex: 9.90).", "error")
            return render_template("admin/institution/product_form.html",
                                   inst=inst, product=None)
        p = Product(
            institution_id=iid,
            name        = request.form["name"],
            category    = request.form.get("category", ""),
            description = request.form.get("description", ""),
            price       = price,
            on_sale     = "on_sale" in request.form,
            sale_price  = sale_price,
        )
        db.session.add(p)
        bump_content_version(iid)
        db.session.commit()
        flash(f"Produto '{p.name}' adicionado.", "success")
        return redirect(url_for("admin_institution.product_list", iid=iid))
    return render_template("admin/institution/product_form.html", inst=inst, product=None)


@admin_institution_bp.route("/institutions/<int:iid>/products/<int:pid>/edit",
                             methods=["GET", "POST"])
@client_admin_required
def product_edit(iid, pid):
    inst    = Institution.query.get_or_404(iid)
    product = tenant_get_or_404(Product, pid, iid)
    if request.method == "POST":
        validate_csrf_token()
        product.name        = request.form["name"]
        product.category    = request.form.get("category", "")
        product.description = request.form.get("description", "")
        try:
            product.price      = float(request.form.get("price") or 0)
            product.sale_price = float(request.form.get("sale_price") or 0)
        except ValueError:
            flash("Preço inválido. Use números (ex: 9.90).", "error")
            return render_template("admin/institution/product_form.html",
                                   inst=inst, product=product)
        product.on_sale     = "on_sale" in request.form
        bump_content_version(iid)
        db.session.commit()
        flash(f"Produto '{product.name}' atualizado.", "success")
        return redirect(url_for("admin_institution.product_list", iid=iid))
    return render_template("admin/institution/product_form.html",
                           inst=inst, product=product)


@admin_institution_bp.route("/institutions/<int:iid>/products/<int:pid>/delete",
                             methods=["POST"])
@client_admin_required
def product_delete(iid, pid):
    validate_csrf_token()
    product = tenant_get_or_404(Product, pid, iid)
    db.session.delete(product)
    bump_content_version(iid)
    db.session.commit()
    flash("Produto removido.", "warning")
    return redirect(url_for("admin_institution.product_list", iid=iid))


# ── FAQs ───────────────────────────────────────────────────────────────────────

@admin_institution_bp.route("/institutions/<int:iid>/faq")
@client_admin_required
def faq_list(iid):
    inst = Institution.query.get_or_404(iid)
    faqs = (FAQ.query
            .filter_by(institution_id=iid)
            .order_by(FAQ.category, FAQ.id).all())
    return render_template("admin/institution/faq_list.html", inst=inst, faqs=faqs)


@admin_institution_bp.route("/institutions/<int:iid>/faq/new", methods=["GET", "POST"])
@client_admin_required
def faq_new(iid):
    inst = Institution.query.get_or_404(iid)
    if request.method == "POST":
        validate_csrf_token()
        faq = FAQ(
            institution_id=iid,
            question = request.form["question"],
            answer   = request.form["answer"],
            category = request.form.get("category", "Geral"),
        )
        db.session.add(faq)
        bump_content_version(iid)
        db.session.commit()
        flash("FAQ adicionada.", "success")
        return redirect(url_for("admin_institution.faq_list", iid=iid))
    return render_template("admin/institution/faq_form.html", inst=inst, faq=None)


@admin_institution_bp.route("/institutions/<int:iid>/faq/<int:fid>/edit",
                             methods=["GET", "POST"])
@client_admin_required
def faq_edit(iid, fid):
    inst = Institution.query.get_or_404(iid)
    faq = tenant_get_or_404(FAQ, fid, iid)
    if request.method == "POST":
        validate_csrf_token()
        faq.question = request.form["question"]
        faq.answer   = request.form["answer"]
        faq.category = request.form.get("category", "Geral")
        bump_content_version(iid)
        db.session.commit()
        flash("FAQ atualizada.", "success")
        return redirect(url_for("admin_institution.faq_list", iid=iid))
    return render_template("admin/institution/faq_form.html", inst=inst, faq=faq)


@admin_institution_bp.route("/institutions/<int:iid>/faq/<int:fid>/delete",
                             methods=["POST"])
@client_admin_required
def faq_delete(iid, fid):
    validate_csrf_token()
    faq = tenant_get_or_404(FAQ, fid, iid)
    db.session.delete(faq)
    bump_content_version(iid)
    db.session.commit()
    flash("FAQ removida.", "warning")
    return redirect(url_for("admin_institution.faq_list", iid=iid))


# ── Quiz / Curiosidades ────────────────────────────────────────────────────────
# Trello: Modulo 2 - Quiz [Baixa]. Conteudo gerenciado pelo client_admin
# como qualquer outro (animais, eventos, etc.) — bump_content_version chamado
# antes do commit para que o totem detecte e recarregue.

def _parse_quiz_form(q, src):
    """Aplica campos do form a uma QuizQuestion (nova ou existente).

    Retorna lista de erros (vazia = ok). Validacao no servidor — front pode
    facilitar mas nao e' fonte da verdade.
    """
    errors: list[str] = []
    pergunta = (src.get("question") or "").strip()
    if not pergunta:
        errors.append("Pergunta é obrigatória.")
    if len(pergunta) > MAX_QUESTION_LEN:
        errors.append(f"Pergunta excede {MAX_QUESTION_LEN} caracteres.")

    raw_opts = src.getlist("options") if hasattr(src, "getlist") else (src.get("options") or [])
    opts = [(o or "").strip() for o in raw_opts]
    opts = [o for o in opts if o]
    if not (MIN_OPTIONS <= len(opts) <= MAX_OPTIONS):
        errors.append(f"Forneça entre {MIN_OPTIONS} e {MAX_OPTIONS} alternativas não vazias.")
    if any(len(o) > MAX_OPTION_LEN for o in opts):
        errors.append(f"Alternativa excede {MAX_OPTION_LEN} caracteres.")

    try:
        correct_index = int(src.get("correct_index") or 0)
    except (TypeError, ValueError):
        correct_index = -1
    if not (0 <= correct_index < len(opts)):
        errors.append("Selecione qual alternativa é a correta.")

    if errors:
        return errors

    q.question = pergunta
    q.options = opts
    q.correct_index = correct_index
    q.curiosity = (src.get("curiosity") or "").strip() or None
    q.category = (src.get("category") or "").strip() or None
    q.order = _safe_order(src.get("order"))
    q.active = "active" in src
    return []


def _safe_order(raw):
    try:
        return max(0, int(raw)) if raw not in (None, "") else 0
    except (TypeError, ValueError):
        return 0


@admin_institution_bp.route("/institutions/<int:iid>/quiz")
@client_admin_required
def quiz_list(iid):
    inst = Institution.query.get_or_404(iid)
    questions = (
        tenant_query(QuizQuestion, iid)
        .order_by(QuizQuestion.order, QuizQuestion.id)
        .all()
    )
    return render_template("admin/institution/quiz_list.html",
                           inst=inst, questions=questions)


@admin_institution_bp.route("/institutions/<int:iid>/quiz/new", methods=["GET", "POST"])
@client_admin_required
def quiz_new(iid):
    inst = Institution.query.get_or_404(iid)
    if request.method == "POST":
        validate_csrf_token()
        q = QuizQuestion(institution_id=iid, options_json="[]")
        errors = _parse_quiz_form(q, request.form)
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("admin/institution/quiz_form.html",
                                   inst=inst, question=q, action="new")
        db.session.add(q)
        bump_content_version(iid)
        db.session.commit()
        flash("Pergunta adicionada.", "success")
        return redirect(url_for("admin_institution.quiz_list", iid=iid))
    return render_template("admin/institution/quiz_form.html",
                           inst=inst, question=None, action="new")


@admin_institution_bp.route("/institutions/<int:iid>/quiz/<int:qid>/edit",
                             methods=["GET", "POST"])
@client_admin_required
def quiz_edit(iid, qid):
    inst = Institution.query.get_or_404(iid)
    q = tenant_get_or_404(QuizQuestion, qid, iid)
    if request.method == "POST":
        validate_csrf_token()
        errors = _parse_quiz_form(q, request.form)
        if errors:
            for e in errors:
                flash(e, "error")
            return render_template("admin/institution/quiz_form.html",
                                   inst=inst, question=q, action="edit")
        bump_content_version(iid)
        db.session.commit()
        flash("Pergunta atualizada.", "success")
        return redirect(url_for("admin_institution.quiz_list", iid=iid))
    return render_template("admin/institution/quiz_form.html",
                           inst=inst, question=q, action="edit")


@admin_institution_bp.route("/institutions/<int:iid>/quiz/<int:qid>/delete",
                             methods=["POST"])
@client_admin_required
def quiz_delete(iid, qid):
    validate_csrf_token()
    q = tenant_get_or_404(QuizQuestion, qid, iid)
    db.session.delete(q)
    bump_content_version(iid)
    db.session.commit()
    flash("Pergunta removida.", "warning")
    return redirect(url_for("admin_institution.quiz_list", iid=iid))


# ── Logs de interação ──────────────────────────────────────────────────────────

@admin_institution_bp.route("/institutions/<int:iid>/logs")
@client_admin_required
def log_list(iid):
    inst = Institution.query.get_or_404(iid)
    logs = (InteractionLog.query
            .filter_by(institution_id=iid)
            .order_by(InteractionLog.created_at.desc())
            .limit(200).all())
    return render_template("admin/institution/log_list.html", inst=inst, logs=logs)
