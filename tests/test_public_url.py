"""Testes da URL publica HTTPS por instituicao (Cloudflare Tunnel).

Cobre:
  - `Institution.effective_public_url()` resolve com precedencia correta
    (inst > env > None).
  - Helper `_clean_public_url` aceita HTTPS, rejeita HTTP/scheme malformado,
    e rejeita string > 255 chars.
  - Form de edicao persiste o campo e retorna erro em URL invalida.
  - Sidebar do admin renderiza o link com a URL publica quando definida,
    com o fallback do env, e com a rota interna em ultimo caso.
"""
from datetime import datetime

import pytest

from app.extensions import db
from app.models import Institution, User
from app.routes.admin_platform import _clean_public_url


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def super_admin(app):
    with app.app_context():
        sa = User(email="super-purl@flex.com", name="Super PURL",
                  role="super_admin", active=True)
        sa.set_password("Senha-Forte-2026!")
        sa.must_change_password = False
        sa.totp_secret = "JBSWY3DPEHPK3PXP"
        sa.totp_enabled = True
        sa.totp_confirmed_at = datetime.utcnow()
        db.session.add(sa)
        db.session.commit()
        return {"email": sa.email, "id": sa.id}


@pytest.fixture
def inst_id(app):
    with app.app_context():
        return Institution.query.filter_by(slug="teste").first().id


def _login_super(client, sa):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(sa["id"])
        sess["_fresh"] = True
        sess["_login_ip"] = "127.0.0.1"


# ── _clean_public_url ────────────────────────────────────────────────────────

def test_clean_aceita_https_valido():
    assert _clean_public_url("https://pi01.flextotem.uk") == "https://pi01.flextotem.uk"


def test_clean_remove_barra_final():
    assert _clean_public_url("https://pi01.flextotem.uk/") == "https://pi01.flextotem.uk"


def test_clean_aceita_porta_e_path():
    assert _clean_public_url("https://host.exemplo.com:8443/totem") == "https://host.exemplo.com:8443/totem"


def test_clean_string_vazia_vira_none():
    assert _clean_public_url("") is None
    assert _clean_public_url("   ") is None
    assert _clean_public_url(None) is None


def test_clean_rejeita_http_sem_tls():
    """getUserMedia exige Secure Origin — HTTP simples e' bloqueado."""
    with pytest.raises(ValueError, match="https://"):
        _clean_public_url("http://pi01.flextotem.uk")


def test_clean_rejeita_scheme_malformado():
    with pytest.raises(ValueError):
        _clean_public_url("javascript:alert(1)")
    with pytest.raises(ValueError):
        _clean_public_url("ftp://exemplo.com")
    with pytest.raises(ValueError):
        _clean_public_url("apenas-texto")


def test_clean_rejeita_url_muito_longa():
    longa = "https://" + ("a" * 260) + ".com"
    with pytest.raises(ValueError, match="255"):
        _clean_public_url(longa)


# ── Institution.effective_public_url ─────────────────────────────────────────

def test_effective_url_prefere_campo_da_instituicao(app, inst_id):
    with app.app_context():
        inst = db.session.get(Institution, inst_id)
        inst.public_url = "https://pi01.flextotem.uk"
        assert inst.effective_public_url("https://global.example.com") == "https://pi01.flextotem.uk"


def test_effective_url_cai_no_env_quando_campo_vazio(app, inst_id):
    with app.app_context():
        inst = db.session.get(Institution, inst_id)
        inst.public_url = None
        assert inst.effective_public_url("https://global.example.com") == "https://global.example.com"


def test_effective_url_remove_barra_final_em_qualquer_origem(app, inst_id):
    with app.app_context():
        inst = db.session.get(Institution, inst_id)
        inst.public_url = "https://pi01.flextotem.uk/"
        assert inst.effective_public_url(None) == "https://pi01.flextotem.uk"
        inst.public_url = None
        assert inst.effective_public_url("https://global.example.com/") == "https://global.example.com"


def test_effective_url_none_quando_tudo_vazio(app, inst_id):
    with app.app_context():
        inst = db.session.get(Institution, inst_id)
        inst.public_url = None
        assert inst.effective_public_url(None) is None
        assert inst.effective_public_url("") is None


# ── Form de edicao: persistencia + validacao ─────────────────────────────────

def test_form_persiste_public_url(client, super_admin, inst_id, app):
    _login_super(client, super_admin)
    r = client.post(
        f"/admin/platform/institutions/{inst_id}/edit",
        data={
            "name": "Totem Teste",
            "slug": "teste",
            "type": "zoo",
            "tagline": "",
            "primary_color": "#f4b860",
            "secondary_color": "#4dd9d0",
            "bg_color": "#040c10",
            "text_color": "#ddeef7",
            "theme": "dark",
            "address": "",
            "phone": "",
            "opening_hours": "",
            "public_url": "https://pi01.flextotem.uk/",  # com barra final
            "ai_name": "Guia",
            "ai_context": "",
            "daily_ai_quota": "500",
            "active": "on",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    with app.app_context():
        inst = db.session.get(Institution, inst_id)
        # Salvo sem barra final.
        assert inst.public_url == "https://pi01.flextotem.uk"


def test_form_rejeita_http_inseguro(client, super_admin, inst_id, app):
    _login_super(client, super_admin)
    r = client.post(
        f"/admin/platform/institutions/{inst_id}/edit",
        data={
            "name": "Totem Teste",
            "slug": "teste",
            "type": "zoo",
            "primary_color": "#f4b860",
            "secondary_color": "#4dd9d0",
            "bg_color": "#040c10",
            "text_color": "#ddeef7",
            "theme": "dark",
            "public_url": "http://pi01.flextotem.uk",  # HTTP — bloqueado
            "ai_name": "Guia",
            "daily_ai_quota": "500",
        },
        follow_redirects=False,
    )
    # Form re-renderiza com flash de erro (200), nao redireciona.
    assert r.status_code == 200
    with app.app_context():
        inst = db.session.get(Institution, inst_id)
        # Campo NAO foi persistido.
        assert (inst.public_url or "") != "http://pi01.flextotem.uk"


def test_form_apaga_public_url_quando_vazio(client, super_admin, inst_id, app):
    """Submeter com public_url vazio limpa o campo (volta a usar fallback do env)."""
    with app.app_context():
        inst = db.session.get(Institution, inst_id)
        inst.public_url = "https://antigo.flextotem.uk"
        db.session.commit()

    _login_super(client, super_admin)
    r = client.post(
        f"/admin/platform/institutions/{inst_id}/edit",
        data={
            "name": "Totem Teste",
            "slug": "teste",
            "type": "zoo",
            "primary_color": "#f4b860",
            "secondary_color": "#4dd9d0",
            "bg_color": "#040c10",
            "text_color": "#ddeef7",
            "theme": "dark",
            "public_url": "",
            "ai_name": "Guia",
            "daily_ai_quota": "500",
            "active": "on",
        },
        follow_redirects=False,
    )
    assert r.status_code in (302, 303)
    with app.app_context():
        inst = db.session.get(Institution, inst_id)
        assert inst.public_url is None


# ── Sidebar do admin: link "Ver Totem" usa a URL publica ─────────────────────

def test_sidebar_link_usa_public_url_da_instituicao(client, super_admin, inst_id, app):
    """Quando a inst tem public_url, o link do sidebar aponta pra HTTPS publico."""
    with app.app_context():
        inst = db.session.get(Institution, inst_id)
        inst.public_url = "https://pi01.flextotem.uk"
        db.session.commit()

    _login_super(client, super_admin)
    r = client.get(f"/admin/institutions/{inst_id}/")
    assert r.status_code == 200
    assert b"https://pi01.flextotem.uk" in r.data
    # Nao deve linkar a rota interna do totem quando ha URL publica.
    assert b'href="/teste/"' not in r.data


def test_sidebar_link_cai_no_env_quando_inst_vazia(client, super_admin, inst_id, app):
    with app.app_context():
        inst = db.session.get(Institution, inst_id)
        inst.public_url = None
        db.session.commit()
        app.config["TOTEM_PUBLIC_URL"] = "https://global.flextotem.uk"

    _login_super(client, super_admin)
    r = client.get(f"/admin/institutions/{inst_id}/")
    assert r.status_code == 200
    assert b"https://global.flextotem.uk" in r.data


def test_sidebar_link_cai_na_rota_interna_quando_tudo_vazio(client, super_admin, inst_id, app):
    with app.app_context():
        inst = db.session.get(Institution, inst_id)
        inst.public_url = None
        db.session.commit()
        app.config["TOTEM_PUBLIC_URL"] = ""

    _login_super(client, super_admin)
    r = client.get(f"/admin/institutions/{inst_id}/")
    assert r.status_code == 200
    # Fallback: rota interna /<slug>/.
    assert b'href="/teste/"' in r.data
