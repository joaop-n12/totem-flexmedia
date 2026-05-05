"""Testes de isolamento entre tenants (multi-instituicao).

Cenario: a plataforma e' white label, varias instituicoes coexistem no
mesmo banco. Um client_admin de uma instituicao NAO pode, sob nenhuma
combinacao de URL, ler ou escrever dados de outra.

Cobre:
  - tenant_get_or_404: 404 (e nao 403) quando o id pertence a outro tenant.
  - tenant_get_or_404: levanta TypeError se o modelo nao tem institution_id.
  - tenant_query: nao retorna registros de outro tenant.
  - client_admin_required: redireciona/403 quando iid != institution_id do user.
  - Tentativa cross-tenant grava ACTION_TENANT_DENIED em AdminAuditLog.
  - super_admin atravessa instituicoes (comportamento esperado).

Importante: este e' o teste que pega regressao silenciosa. Se um futuro
PR adicionar uma rota nova esquecendo o filtro por institution_id, o
escopo do dano e' limitado pela politica reforcada aqui.
"""
import pytest
from werkzeug.exceptions import HTTPException

from app.extensions import db
from app.helpers import tenant_get_or_404, tenant_query
from app.models import (
    AdminAuditLog, Animal, Event, FAQ, Institution, InteractionLog,
    Product, Store, User,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def two_tenants(app):
    """Cria duas instituicoes (A e B) cada uma com um animal/evento/loja
    /produto/FAQ/log e um client_admin proprio."""
    with app.app_context():
        a = Institution(slug="zoo-a", name="Zoo A", type="zoo",
                        ai_name="A", ai_context="b",
                        daily_ai_quota=500, active=True)
        b = Institution(slug="zoo-b", name="Zoo B", type="zoo",
                        ai_name="A", ai_context="b",
                        daily_ai_quota=500, active=True)
        db.session.add_all([a, b])
        db.session.flush()

        # Conteudo de cada tenant — ids vao sair em sequencia.
        animal_a = Animal(institution_id=a.id, nome="Leao A", especie="Felino")
        animal_a.generate_slug()
        animal_b = Animal(institution_id=b.id, nome="Leao B", especie="Felino")
        animal_b.generate_slug()
        event_a = Event(institution_id=a.id, evento="Show A")
        event_b = Event(institution_id=b.id, evento="Show B")
        store_a = Store(institution_id=a.id, name="Loja A")
        store_a.generate_slug()
        store_b = Store(institution_id=b.id, name="Loja B")
        store_b.generate_slug()
        product_a = Product(institution_id=a.id, name="P A")
        product_b = Product(institution_id=b.id, name="P B")
        faq_a = FAQ(institution_id=a.id, question="qa", answer="ra")
        faq_b = FAQ(institution_id=b.id, question="qb", answer="rb")

        db.session.add_all([animal_a, animal_b, event_a, event_b,
                            store_a, store_b, product_a, product_b,
                            faq_a, faq_b])

        # client_admin de cada tenant.
        admin_a = User(email="admin-a@flex.com", name="Admin A",
                       role="client_admin", institution_id=a.id, active=True)
        admin_a.set_password("Senha-Forte-2026!")
        admin_a.must_change_password = False
        admin_b = User(email="admin-b@flex.com", name="Admin B",
                       role="client_admin", institution_id=b.id, active=True)
        admin_b.set_password("Senha-Forte-2026!")
        admin_b.must_change_password = False
        db.session.add_all([admin_a, admin_b])
        db.session.commit()

        return {
            "a_id": a.id, "b_id": b.id,
            "admin_a_email": admin_a.email,
            "admin_b_email": admin_b.email,
            "animal_a_id": animal_a.id, "animal_b_id": animal_b.id,
            "event_a_id":  event_a.id,  "event_b_id":  event_b.id,
            "store_a_id":  store_a.id,  "store_b_id":  store_b.id,
            "product_a_id": product_a.id, "product_b_id": product_b.id,
            "faq_a_id":    faq_a.id,    "faq_b_id":    faq_b.id,
        }


# ── tenant_get_or_404 ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("model_name,a_key,b_key", [
    ("Animal",  "animal_a_id",  "animal_b_id"),
    ("Event",   "event_a_id",   "event_b_id"),
    ("Store",   "store_a_id",   "store_b_id"),
    ("Product", "product_a_id", "product_b_id"),
    ("FAQ",     "faq_a_id",     "faq_b_id"),
])
def test_tenant_get_or_404_recusa_id_de_outro_tenant(app, two_tenants, model_name, a_key, b_key):
    """Pedir um id que existe mas pertence a outro tenant deve dar 404."""
    Model = {"Animal": Animal, "Event": Event, "Store": Store,
             "Product": Product, "FAQ": FAQ}[model_name]
    with app.app_context():
        # Tenant A pedindo o id do recurso de B.
        with pytest.raises(HTTPException) as exc:
            tenant_get_or_404(Model, two_tenants[b_key], two_tenants["a_id"])
        assert exc.value.code == 404


def test_tenant_get_or_404_aceita_id_proprio(app, two_tenants):
    with app.app_context():
        a = tenant_get_or_404(Animal, two_tenants["animal_a_id"], two_tenants["a_id"])
        assert a.institution_id == two_tenants["a_id"]


def test_tenant_get_or_404_recusa_modelo_sem_institution_id(app, two_tenants):
    """Defesa programatica — usar o helper com modelo errado e' bug."""
    with app.app_context():
        # User tem institution_id (FK opcional) — usamos AdminAuditLog que tambem
        # nao tem coluna institution_id. Caso falhe, escolhemos User invertido.
        with pytest.raises(TypeError):
            # Module: institution e' tabela de associacao via InstitutionModule;
            # o proprio Module nao tem institution_id. Garantimos via Mock leve.
            class _SemColuna:  # noqa: N801
                __name__ = "SemColuna"
            tenant_get_or_404(_SemColuna, 1, 1)


# ── tenant_query ──────────────────────────────────────────────────────────────

def test_tenant_query_filtra_por_instituicao(app, two_tenants):
    with app.app_context():
        only_a = tenant_query(Animal, two_tenants["a_id"]).all()
        assert len(only_a) == 1
        assert all(x.institution_id == two_tenants["a_id"] for x in only_a)


# ── client_admin_required (rotas reais) ──────────────────────────────────────

def _login_session(client, email):
    """Login direto via session_transaction — evita dance do TOTP em testes
    de isolamento, que nao envolvem 2FA."""
    with client.session_transaction() as sess:
        # Recupera o user_id pelo email.
        from app.models import User as _U
        u = _U.query.filter_by(email=email).first()
        sess["_user_id"] = str(u.id)
        sess["_fresh"] = True
        sess["_login_ip"] = "127.0.0.1"


def test_client_admin_acessa_propria_instituicao(app, client, two_tenants):
    _login_session(client, two_tenants["admin_a_email"])
    r = client.get(f"/admin/institutions/{two_tenants['a_id']}/")
    # Pode ser 200 (dashboard render) ou 302 (must_change_password redirect)
    # Importante: NAO e' 403.
    assert r.status_code != 403


def test_client_admin_recusa_outra_instituicao(app, client, two_tenants):
    """Coracao do PR — admin de A pedindo URL de B deve receber 403."""
    _login_session(client, two_tenants["admin_a_email"])
    r = client.get(f"/admin/institutions/{two_tenants['b_id']}/",
                   follow_redirects=False)
    assert r.status_code == 403


def test_cross_tenant_gera_audit_log(app, client, two_tenants):
    """Tentativa cross-tenant deixa rastro forense."""
    _login_session(client, two_tenants["admin_a_email"])
    client.get(f"/admin/institutions/{two_tenants['b_id']}/animals",
               follow_redirects=False)
    with app.app_context():
        entry = (AdminAuditLog.query
                 .filter_by(action="tenant.access_denied")
                 .order_by(AdminAuditLog.id.desc())
                 .first())
        assert entry is not None
        assert entry.actor_email == two_tenants["admin_a_email"]
        assert entry.resource_type == "institution"
        assert str(two_tenants["b_id"]) == entry.resource_id


def test_client_admin_recusa_recurso_de_outro_tenant_via_url(app, client, two_tenants):
    """URL bem formada para o proprio iid mas com child_id de outro tenant.

    Como `iid` esta correto, o client_admin_required passa. Mas o
    `tenant_get_or_404` na rota pega — devolve 404 (nao revela existencia).
    """
    _login_session(client, two_tenants["admin_a_email"])
    # Edita o animal de B passando-o como /institutions/<a_id>/animals/<animal_b_id>/edit
    r = client.get(
        f"/admin/institutions/{two_tenants['a_id']}/animals/{two_tenants['animal_b_id']}/edit",
        follow_redirects=False,
    )
    assert r.status_code == 404


# ── super_admin atravessa instituicoes ────────────────────────────────────────

def test_super_admin_acessa_qualquer_instituicao(app, client, two_tenants):
    """Comportamento esperado — super_admin existe pra investigar."""
    with app.app_context():
        sa = User(email="super@flex.com", name="Super",
                  role="super_admin", active=True)
        sa.set_password("Senha-Forte-2026!")
        sa.must_change_password = False
        # Bypass do TOTP gate para o teste — deixa has_totp True via
        # totp_enabled+totp_confirmed_at; o login session-only nao passa
        # pelo /admin/login que verifica TOTP.
        sa.totp_enabled = True
        from datetime import datetime as _dt
        sa.totp_confirmed_at = _dt.utcnow()
        db.session.add(sa)
        db.session.commit()

    _login_session(client, "super@flex.com")
    # super_admin pode entrar em /institutions/<a_id>/ E em /institutions/<b_id>/.
    r1 = client.get(f"/admin/institutions/{two_tenants['a_id']}/animals",
                    follow_redirects=False)
    r2 = client.get(f"/admin/institutions/{two_tenants['b_id']}/animals",
                    follow_redirects=False)
    assert r1.status_code != 403
    assert r2.status_code != 403
