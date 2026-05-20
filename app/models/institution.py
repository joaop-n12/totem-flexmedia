from datetime import datetime
from app.extensions import db


class Institution(db.Model):
    """Represents a tenant — zoo, shopping, pharmacy, museum, etc."""
    __tablename__ = "institutions"

    id            = db.Column(db.Integer, primary_key=True)
    slug          = db.Column(db.String(50), unique=True, nullable=False)   # URL key: 'zoo', 'shopping'
    name          = db.Column(db.String(120), nullable=False)
    type          = db.Column(db.String(50), nullable=False, default="zoo") # zoo|shopping|pharmacy|park|museum|aquarium|other
    tagline       = db.Column(db.String(255))

    # Branding
    logo_path     = db.Column(db.String(255))                               # relative to static/
    primary_color = db.Column(db.String(20), default="#f4b860")
    secondary_color = db.Column(db.String(20), default="#4dd9d0")
    bg_color      = db.Column(db.String(20), default="#040c10")
    text_color    = db.Column(db.String(20), default="#ddeef7")
    theme         = db.Column(db.String(10), default="dark")                # dark|light

    # Info
    address       = db.Column(db.String(255))
    phone         = db.Column(db.String(50))
    opening_hours = db.Column(db.String(255))                               # "Seg-Dom: 9h–18h"
    website       = db.Column(db.String(255))

    # URL publica HTTPS do totem (Cloudflare Tunnel: pi01.flextotem.uk, etc).
    # Quando definida, o link "Ver Totem" no painel admin abre o kiosk via
    # HTTPS publico em vez da rota interna (http://127.0.0.1:5000/<slug>/).
    # Necessario para liberar getUserMedia (microfone) fora de localhost:
    # navegadores so consideram Secure Origin localhost ou https://.
    # Quando vazia, cai no env TOTEM_PUBLIC_URL; e' apenas para 1 Pi = 1 institui-
    # cao com tunel dedicado (cenario do piloto Flexmedia).
    public_url    = db.Column(db.String(255))

    # AI
    ai_name       = db.Column(db.String(60), default="Assistente")
    ai_context    = db.Column(db.Text)                                      # base system prompt
    # Quota diaria de chamadas ao assistente (voz + texto somados) por tenant.
    # Protege contra uso abusivo / loops maliciosos que gerariam custo na OpenAI.
    # 0 = ilimitado. Default conservador (500/dia ~ R$ 10-30/dia em gpt-4o-mini).
    daily_ai_quota = db.Column(db.Integer, default=500, nullable=False)

    # State
    active        = db.Column(db.Boolean, default=True)
    created_at    = db.Column(db.DateTime, default=datetime.utcnow)

    # Versionamento de conteudo — incrementado a cada CRUD do client_admin.
    # Totem em campo polla /api/sync/version e recarrega quando muda. Permite
    # atualizar conteudo sem reiniciar o kiosk (Trello: Modulo 3 - Atualizacao
    # de conteudo, criterios 3.5 e 3.6).
    content_version = db.Column(db.Integer, nullable=False, default=0)

    # Relationships
    modules       = db.relationship("InstitutionModule", back_populates="institution",
                                    cascade="all, delete-orphan", order_by="InstitutionModule.order")
    animals       = db.relationship("Animal",   back_populates="institution", cascade="all, delete-orphan")
    events        = db.relationship("Event",    back_populates="institution", cascade="all, delete-orphan")
    stores        = db.relationship("Store",    back_populates="institution", cascade="all, delete-orphan")
    products      = db.relationship("Product",  back_populates="institution", cascade="all, delete-orphan")
    faqs          = db.relationship("FAQ",      back_populates="institution", cascade="all, delete-orphan")
    map_areas     = db.relationship("MapArea",  back_populates="institution", cascade="all, delete-orphan")
    logs          = db.relationship("InteractionLog", back_populates="institution", cascade="all, delete-orphan")

    def enabled_modules(self):
        return [m for m in self.modules if m.enabled]

    def has_module(self, slug: str) -> bool:
        return any(m.module_slug == slug and m.enabled for m in self.modules)

    def ai_calls_today(self) -> int:
        """Conta quantas chamadas ao assistente foram feitas hoje (UTC)."""
        from datetime import datetime, timedelta
        from app.models.log import InteractionLog
        start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        return InteractionLog.query.filter(
            InteractionLog.institution_id == self.id,
            InteractionLog.created_at >= start,
        ).count()

    def ai_quota_exceeded(self) -> bool:
        """True se a quota diaria foi atingida (0 = ilimitado)."""
        if not self.daily_ai_quota or self.daily_ai_quota <= 0:
            return False
        return self.ai_calls_today() >= self.daily_ai_quota

    def effective_public_url(self, env_fallback: str | None = None) -> str | None:
        """URL HTTPS publica do totem para esta instituicao.

        Ordem de prioridade:
          1. `self.public_url` (definida no painel super_admin por instituicao).
          2. `env_fallback` (TOTEM_PUBLIC_URL do .env — fonte unica em deploys
             com 1 tunel global).
          3. None → o caller deve cair na rota interna (`core.home`).

        Sempre normaliza removendo barra final para evitar `//` na concatenacao.
        """
        candidato = (self.public_url or env_fallback or "").strip()
        if not candidato:
            return None
        return candidato.rstrip("/")

    def __repr__(self):
        return f"<Institution {self.slug}>"


class Module(db.Model):
    """Catalog of all available modules."""
    __tablename__ = "modules"

    id               = db.Column(db.Integer, primary_key=True)
    slug             = db.Column(db.String(50), unique=True, nullable=False)
    name             = db.Column(db.String(100), nullable=False)
    description      = db.Column(db.String(255))
    icon             = db.Column(db.String(10))
    compatible_types = db.Column(db.String(255), default="all")             # 'all' or 'zoo,shopping'

    def __repr__(self):
        return f"<Module {self.slug}>"


class InstitutionModule(db.Model):
    """Which modules are active per institution."""
    __tablename__ = "institution_modules"

    institution_id = db.Column(db.Integer, db.ForeignKey("institutions.id"), primary_key=True)
    module_slug    = db.Column(db.String(50), primary_key=True)
    enabled        = db.Column(db.Boolean, default=True)
    order          = db.Column(db.Integer, default=0)                       # display order in nav

    institution    = db.relationship("Institution", back_populates="modules")

    def __repr__(self):
        return f"<InstitutionModule {self.institution_id}:{self.module_slug}>"
