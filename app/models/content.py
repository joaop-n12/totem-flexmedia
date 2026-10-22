import re, unicodedata
from app.extensions import db


def _slugify(text: str) -> str:
    text = (text or "").strip().lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s-]+", "-", text).strip("-")
    return text or "item"


# ── Zoo module ────────────────────────────────────────────────────────────────

class Animal(db.Model):
    __tablename__ = "animals"

    id             = db.Column(db.Integer, primary_key=True)
    institution_id = db.Column(db.Integer, db.ForeignKey("institutions.id"), nullable=False)
    slug           = db.Column(db.String(100))
    nome           = db.Column(db.String(120), nullable=False)
    especie        = db.Column(db.String(80))
    especie_slug   = db.Column(db.String(80))
    habitat        = db.Column(db.String(80))
    area           = db.Column(db.String(80))
    descricao      = db.Column(db.Text)
    imagem         = db.Column(db.String(255))
    alimentacao    = db.Column(db.Text)
    curiosidades   = db.Column(db.Text)
    conservacao    = db.Column(db.Text)

    institution    = db.relationship("Institution", back_populates="animals")

    def generate_slug(self):
        self.slug = _slugify(self.nome)
        self.especie_slug = _slugify(self.especie or "outros")

    def __repr__(self):
        return f"<Animal {self.nome}>"


# ── Events / Programming module ────────────────────────────────────────────────

class Event(db.Model):
    __tablename__ = "events"

    id             = db.Column(db.Integer, primary_key=True)
    institution_id = db.Column(db.Integer, db.ForeignKey("institutions.id"), nullable=False)
    evento         = db.Column(db.String(150), nullable=False)
    horario        = db.Column(db.String(20))
    local          = db.Column(db.String(150))
    descricao      = db.Column(db.Text)
    active         = db.Column(db.Boolean, default=True)

    institution    = db.relationship("Institution", back_populates="events")

    def __repr__(self):
        return f"<Event {self.evento}>"


# ── Shopping module ────────────────────────────────────────────────────────────

class Store(db.Model):
    __tablename__ = "stores"

    id             = db.Column(db.Integer, primary_key=True)
    institution_id = db.Column(db.Integer, db.ForeignKey("institutions.id"), nullable=False)
    slug           = db.Column(db.String(100))
    name           = db.Column(db.String(150), nullable=False)
    category       = db.Column(db.String(80))
    floor          = db.Column(db.String(50))
    unit_code      = db.Column(db.String(30))
    x_pos          = db.Column(db.Float)  # posição percentual opcional na planta do piso
    y_pos          = db.Column(db.Float)
    description    = db.Column(db.Text)
    logo_path      = db.Column(db.String(255))
    hours          = db.Column(db.String(100))
    phone          = db.Column(db.String(50))
    on_promotion   = db.Column(db.Boolean, default=False)
    promo_text     = db.Column(db.String(255))

    institution    = db.relationship("Institution", back_populates="stores")

    def generate_slug(self):
        self.slug = _slugify(self.name)

    def __repr__(self):
        return f"<Store {self.name}>"


# ── Pharmacy module ────────────────────────────────────────────────────────────

class Product(db.Model):
    __tablename__ = "products"

    id             = db.Column(db.Integer, primary_key=True)
    institution_id = db.Column(db.Integer, db.ForeignKey("institutions.id"), nullable=False)
    name           = db.Column(db.String(150), nullable=False)
    category       = db.Column(db.String(80))
    description    = db.Column(db.Text)
    price          = db.Column(db.Float)
    on_sale        = db.Column(db.Boolean, default=False)
    sale_price     = db.Column(db.Float)
    image_path     = db.Column(db.String(255))

    institution    = db.relationship("Institution", back_populates="products")

    def __repr__(self):
        return f"<Product {self.name}>"


# ── FAQ (AI knowledge base) ────────────────────────────────────────────────────

class FAQ(db.Model):
    __tablename__ = "faqs"

    id             = db.Column(db.Integer, primary_key=True)
    institution_id = db.Column(db.Integer, db.ForeignKey("institutions.id"), nullable=False)
    question       = db.Column(db.String(255), nullable=False)
    answer         = db.Column(db.Text, nullable=False)
    category       = db.Column(db.String(80))

    institution    = db.relationship("Institution", back_populates="faqs")

    def __repr__(self):
        return f"<FAQ {self.question[:40]}>"


# ── Map areas ──────────────────────────────────────────────────────────────────

class MapArea(db.Model):
    __tablename__ = "map_areas"

    id             = db.Column(db.Integer, primary_key=True)
    institution_id = db.Column(db.Integer, db.ForeignKey("institutions.id"), nullable=False)
    slug           = db.Column(db.String(100))
    name           = db.Column(db.String(150), nullable=False)
    description    = db.Column(db.Text)
    floor          = db.Column(db.String(50), default="Terreo")
    category       = db.Column(db.String(80), default="Servicos")
    x_pos          = db.Column(db.Float, default=50.0)   # hotspot % left
    y_pos          = db.Column(db.Float, default=50.0)   # hotspot % top
    icon           = db.Column(db.String(10))

    institution    = db.relationship("Institution", back_populates="map_areas")

    def generate_slug(self):
        self.slug = _slugify(self.name)

    def __repr__(self):
        return f"<MapArea {self.name}>"
