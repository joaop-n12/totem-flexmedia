"""Seed the database with initial data on first run."""
import json
import os

from app.extensions import db
from app.helpers import slugify
from app.models import Animal, Event, FAQ, Institution, InstitutionModule, Module, User

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


OBSOLETE_MODULE_SLUGS = {"quiz"}


def seed_modules():
    """Cria o catálogo de módulos e remove módulos obsoletos de bancos antigos."""
    catalog = [
        dict(slug="home",        name="Home",          icon="🏠", description="Tela inicial",                compatible_types="all"),
        dict(slug="mapa",        name="Mapa",          icon="🗺️", description="Mapa interativo",             compatible_types="all"),
        dict(slug="programacao", name="Programação",   icon="📅", description="Eventos e horários",           compatible_types="all"),
        dict(slug="alimentacao", name="Alimentação",   icon="🍽️", description="Restaurantes e praça de alimentação", compatible_types="all"),
        dict(slug="ia",          name="Assistente IA", icon="💬", description="Assistente por voz e texto",   compatible_types="all"),
        dict(slug="animais",     name="Animais",       icon="🐾", description="Catálogo de animais",          compatible_types="zoo"),
        dict(slug="lojas",       name="Lojas",         icon="🛍️", description="Catálogo de lojas",            compatible_types="shopping"),
        dict(slug="produtos",    name="Produtos",      icon="💊", description="Catálogo de produtos",         compatible_types="pharmacy"),
    ]
    for item in catalog:
        if not Module.query.filter_by(slug=item["slug"]).first():
            db.session.add(Module(**item))

    # Remove módulos que existiam em versões antigas mas foram descontinuados.
    # Evita que apareçam como "ativáveis" no admin sem ter página correspondente.
    for slug in OBSOLETE_MODULE_SLUGS:
        InstitutionModule.query.filter_by(module_slug=slug).delete()
        Module.query.filter_by(slug=slug).delete()

    db.session.commit()


def seed_zoo():
    """Create the sample zoo institution from existing JSON data."""
    if Institution.query.filter_by(slug="zoo").first():
        return

    zoo = Institution(
        slug="zoo",
        name="Neural Crew Zoo",
        type="zoo",
        tagline="Vida Selvagem",
        logo_path="images/logo.jpeg",
        primary_color="#f4b860",
        secondary_color="#4dd9d0",
        bg_color="#040c10",
        text_color="#ddeef7",
        theme="dark",
        opening_hours="Todos os dias, 9h às 18h. Última entrada às 17h.",
        ai_name="Zoo AI",
        ai_context=(
            "Você é o Zoo AI, assistente virtual do Neural Crew Zoo. "
            "Responda em português, de forma clara e objetiva. "
            "Você conhece todos os animais, horários, áreas e eventos do zoológico."
        ),
    )
    db.session.add(zoo)
    db.session.flush()

    enabled = ["home", "animais", "mapa", "programacao", "alimentacao", "ia"]
    for order, slug in enumerate(enabled):
        db.session.add(InstitutionModule(
            institution_id=zoo.id,
            module_slug=slug,
            enabled=True,
            order=order,
        ))

    animals_path = os.path.join(DATA_DIR, "animais.json")
    if os.path.exists(animals_path):
        with open(animals_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        seen_slugs: set = set()
        for item in data:
            base = slugify(item.get("nome", "animal"))
            s, i = base, 2
            while s in seen_slugs:
                s = f"{base}-{i}"
                i += 1
            seen_slugs.add(s)
            db.session.add(Animal(
                institution_id=zoo.id,
                slug=s,
                nome=item.get("nome", ""),
                especie=item.get("especie", "Outros"),
                especie_slug=slugify(item.get("especie", "outros")),
                habitat=item.get("habitat", ""),
                area=item.get("area", ""),
                descricao=item.get("descricao", ""),
                imagem=item.get("imagem", ""),
                alimentacao=item.get("alimentacao", ""),
                curiosidades=item.get("curiosidades", ""),
                conservacao=item.get("conservacao", ""),
            ))

    eventos_path = os.path.join(DATA_DIR, "programacao.json")
    if os.path.exists(eventos_path):
        with open(eventos_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data:
            db.session.add(Event(
                institution_id=zoo.id,
                evento=item.get("evento", ""),
                horario=item.get("horario", ""),
                local=item.get("local", ""),
                active=True,
            ))

    faqs = [
        ("Qual o horário de funcionamento?", "O zoológico funciona todos os dias das 9h às 18h. A última entrada é às 17h."),
        ("Onde fica a praça de alimentação?", "A praça de alimentação fica no centro do parque, próximo à arena central."),
        ("Tem estacionamento?", "Sim, temos estacionamento próprio na entrada principal do parque."),
        ("Crianças precisam pagar ingresso?", "Crianças até 5 anos entram gratuitamente. Consulte a bilheteria para outras faixas etárias."),
    ]
    for q, a in faqs:
        db.session.add(FAQ(institution_id=zoo.id, question=q, answer=a, category="Geral"))

    db.session.commit()
    print("[seed] Zoo institution created and populated.")


def seed_super_admin():
    """
    Cria o primeiro super_admin a partir de variáveis de ambiente.
    Executa apenas uma vez (se não existir nenhum super_admin).
    Variáveis: SUPERADMIN_EMAIL, SUPERADMIN_PASSWORD (fallback: ADMIN_PASSWORD).
    """
    if User.query.filter_by(role="super_admin").first():
        return

    email    = os.environ.get("SUPERADMIN_EMAIL", "admin@flexmedia.com.br")
    password = os.environ.get("SUPERADMIN_PASSWORD") or os.environ.get("ADMIN_PASSWORD", "flexmedia2024")
    name     = os.environ.get("SUPERADMIN_NAME", "FlexMedia Admin")

    if len(password) < 10:
        print("[seed] AVISO: SUPERADMIN_PASSWORD tem menos de 10 caracteres. "
              "Defina SUPERADMIN_PASSWORD no .env com ao menos 10 caracteres.")
        password = password.ljust(10, "0")  # padding mínimo para não bloquear o boot

    user = User(email=email, name=name, role="super_admin", active=True)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    print(f"[seed] Super admin criado: {email}")


def run_seed():
    seed_modules()
    seed_zoo()
    seed_super_admin()
