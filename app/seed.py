"""Seed the database with initial data on first run."""
import json
import os

from app.extensions import db
from app.helpers import slugify
from app.models import (
    Animal, Event, FAQ, Institution, InstitutionModule, Module, Store, TotemDevice, User,
)
from app.models.device import generate_api_key_id, generate_api_key_secret

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


# Modulos descontinuados em versoes anteriores. Mantemos a lista para que
# `flask seed` em bancos antigos remova entradas orfas. O modulo "quiz" esta
# de volta na Sprint 4 — saiu desta lista e voltou ao catalogo principal.
OBSOLETE_MODULE_SLUGS: set[str] = set()


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
        dict(slug="quiz",        name="Quiz",          icon="🎯", description="Quiz com curiosidades",        compatible_types="all"),
        dict(slug="avaliacao",   name="Avaliação",     icon="⭐", description="Avaliação da experiência",     compatible_types="all"),
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


def _enable_modules(institution, slugs):
    """Ativa módulos demo sem duplicar vínculos existentes."""
    existing = {item.module_slug for item in institution.modules}
    for order, slug in enumerate(slugs):
        if slug not in existing:
            db.session.add(InstitutionModule(
                institution_id=institution.id,
                module_slug=slug,
                enabled=True,
                order=order,
            ))


def seed_neural_shopping():
    """Cria o cliente Neural Shopping, com conteúdo mínimo para o totem."""
    shopping = Institution.query.filter_by(slug="neural-shopping").first()
    if not shopping:
        shopping = Institution(
            slug="neural-shopping",
            name="Neural Shopping",
            type="shopping",
            tagline="Tudo que você precisa em um só lugar",
            primary_color="#f5b34a",
            secondary_color="#4dd9d0",
            bg_color="#040c10",
            text_color="#ddeef7",
            theme="dark",
            opening_hours="Seg-Sáb, 9h30 às 22h.",
            ai_name="Neural Guide",
            ai_context=(
                "Você é o assistente virtual do Neural Shopping. "
                "Responda em português sobre lojas, horários, alimentação e serviços."
            ),
        )
        db.session.add(shopping)
        db.session.flush()
        print("[seed] Shopping institution created.")

    _enable_modules(shopping, ["home", "lojas", "mapa", "programacao", "alimentacao", "ia"])
    if not Store.query.filter_by(institution_id=shopping.id).first():
        stores = [
            ("Nike", "Moda", "Piso 1"),
            ("Adidas", "Moda", "Piso 1"),
        ]
        for name, category, floor in stores:
            store = Store(
                institution_id=shopping.id,
                name=name,
                category=category,
                floor=floor,
                description=f"Loja demo {name}.",
                hours="10h às 22h",
            )
            store.generate_slug()
            db.session.add(store)
    db.session.commit()


def seed_demo_devices():
    """Provisiona um dispositivo fictício para cada cliente demo, uma vez."""
    for slug, name, location in (
        ("zoo", "Totem Zoo Demo", "Entrada principal"),
        ("neural-shopping", "Totem Shopping Demo", "Piso 1"),
    ):
        institution = Institution.query.filter_by(slug=slug).first()
        if not institution or TotemDevice.query.filter_by(institution_id=institution.id).first():
            continue
        device = TotemDevice(
            institution_id=institution.id,
            name=name,
            location=location,
            api_key_id=generate_api_key_id(),
            status="active",
        )
        # O segredo é aleatório e fica cifrado; o dispositivo demo não é uma
        # credencial operacional nem expõe segredo no repositório.
        device.set_secret(generate_api_key_secret())
        db.session.add(device)
        print(f"[seed] Totem demo criado para {institution.name}: {name}")
    db.session.commit()


def seed_super_admin():
    """
    Cria o primeiro super_admin a partir de variaveis de ambiente.
    Executa apenas uma vez (se nao existir nenhum super_admin).

    Variaveis aceitas (em ordem de preferencia):
      SUPERADMIN_PASSWORD  → senha definitiva (deve passar na politica forte)
      ADMIN_PASSWORD       → fallback (legado; mesmo tratamento)
      <nada>               → gera senha random forte e imprime no console

    Se a senha definida pelo operador nao cumprir a politica, criamos a conta
    com must_change_password=True para forcar troca no primeiro login. Nunca
    aceitamos um literal previsivel — o fallback antigo ("flexmedia2024") foi
    removido propositalmente.
    """
    import secrets as _secrets
    import string as _string

    from app.helpers import validate_password_strength

    if User.query.filter_by(role="super_admin").first():
        return

    email = os.environ.get("SUPERADMIN_EMAIL", "admin@flexmedia.com.br")
    name  = os.environ.get("SUPERADMIN_NAME", "FlexMedia Admin")
    password = os.environ.get("SUPERADMIN_PASSWORD") or os.environ.get("ADMIN_PASSWORD")
    senha_gerada = False

    if not password:
        # Gera senha forte: 20 chars com 4 classes garantidas. O operador
        # tem que copiar do log e trocar no primeiro login.
        alphabet = _string.ascii_letters + _string.digits + "!@#$%&*-_=+"
        password = "".join(_secrets.choice(alphabet) for _ in range(20))
        senha_gerada = True

    erros = validate_password_strength(password)
    senha_fraca = bool(erros) and not senha_gerada
    if senha_fraca:
        print(
            "[seed] AVISO: SUPERADMIN_PASSWORD nao cumpre a politica de senha forte:\n  - "
            + "\n  - ".join(erros)
            + "\n  Conta sera criada com must_change_password=True. "
            "Defina SUPERADMIN_PASSWORD com 12+ caracteres e variedade no .env."
        )

    user = User(
        email=email, name=name, role="super_admin", active=True,
        must_change_password=senha_fraca or senha_gerada,
    )
    user.set_password(password)
    # set_password reseta must_change_password — re-aplicamos se necessario.
    user.must_change_password = senha_fraca or senha_gerada
    db.session.add(user)
    db.session.commit()

    if senha_gerada:
        print(
            "[seed] Super admin criado SEM SUPERADMIN_PASSWORD definido.\n"
            f"       Email: {email}\n"
            f"       Senha temporaria: {password}\n"
            "       MUDE NO PRIMEIRO LOGIN — esta linha so aparece uma vez."
        )
    else:
        print(f"[seed] Super admin criado: {email}"
              + (" (TROCA DE SENHA OBRIGATORIA NO 1o LOGIN)" if senha_fraca else ""))


def run_seed():
    seed_modules()
    seed_zoo()
    seed_neural_shopping()
    seed_demo_devices()
    seed_super_admin()
