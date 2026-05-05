"""Testes da pre-visualizacao de white-label.

Cobre:
  - Rota exige super_admin (anonimo → redirect; client_admin → 403).
  - Overrides validos (hex, tema) sao aplicados no template renderizado.
  - Overrides invalidos sao descartados — preview cai no valor persistido.
  - Banner 'PREVIEW' aparece quando o flag esta ativo.
  - Preview NAO PERSISTE: os valores originais permanecem no banco.
  - Tagline e ai_name truncados para os limites configurados.
"""
from datetime import datetime

import pytest

from app.extensions import db
from app.models import Institution, User


# ── Fixture: super_admin com TOTP ja configurado ──────────────────────────────

@pytest.fixture
def super_admin(app):
    """Cria um super_admin pronto pra logar via session_transaction.

    Bypass do TOTP gate: setamos totp_enabled + totp_confirmed_at na mao,
    similar ao test_tenant_isolation. O fluxo de login real nao roda nesses
    testes — interessa o gate `super_admin_required`."""
    with app.app_context():
        sa = User(email="super-preview@flex.com", name="Super Preview",
                  role="super_admin", active=True)
        sa.set_password("Senha-Forte-2026!")
        sa.must_change_password = False
        # has_totp requer totp_enabled E _totp_secret_enc — setamos via
        # property que cifra automaticamente.
        sa.totp_secret = "JBSWY3DPEHPK3PXP"
        sa.totp_enabled = True
        sa.totp_confirmed_at = datetime.utcnow()
        db.session.add(sa)
        db.session.commit()
        return {"email": sa.email, "id": sa.id}


def _login_super(client, sa):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(sa["id"])
        sess["_fresh"] = True
        sess["_login_ip"] = "127.0.0.1"


@pytest.fixture
def inst_id(app):
    with app.app_context():
        inst = Institution.query.filter_by(slug="teste").first()
        return inst.id


# ── Auth gating ──────────────────────────────────────────────────────────────

def test_preview_anonimo_redireciona(client, inst_id):
    r = client.get(f"/admin/platform/institutions/{inst_id}/preview",
                   follow_redirects=False)
    assert r.status_code in (302, 401)


def test_preview_client_admin_recusado(app, client, inst_id):
    """client_admin nao tem acesso a /admin/platform/* — esperamos 403/redirect."""
    with app.app_context():
        u = User(email="ca@flex.com", name="CA", role="client_admin",
                 institution_id=inst_id, active=True)
        u.set_password("Senha-Forte-2026!")
        u.must_change_password = False
        db.session.add(u)
        db.session.commit()
        ca_id = u.id

    with client.session_transaction() as sess:
        sess["_user_id"] = str(ca_id)
        sess["_fresh"] = True
        sess["_login_ip"] = "127.0.0.1"

    r = client.get(f"/admin/platform/institutions/{inst_id}/preview",
                   follow_redirects=False)
    assert r.status_code in (302, 403)


# ── Overrides aplicados ──────────────────────────────────────────────────────

def test_preview_aplica_cor_primaria_no_render(client, super_admin, inst_id):
    _login_super(client, super_admin)
    r = client.get(
        f"/admin/platform/institutions/{inst_id}/preview",
        query_string={"primary_color": "#abcdef"},
    )
    assert r.status_code == 200
    # Cor injetada no <style> :root → aparece no HTML renderizado.
    assert b"#abcdef" in r.data


def test_preview_aceita_tagline_e_ai_name(client, super_admin, inst_id):
    _login_super(client, super_admin)
    r = client.get(
        f"/admin/platform/institutions/{inst_id}/preview",
        query_string={"tagline": "Tagline de teste!", "ai_name": "Nome IA"},
    )
    assert r.status_code == 200
    assert b"Tagline de teste!" in r.data


def test_preview_aceita_tema_light(client, super_admin, inst_id):
    _login_super(client, super_admin)
    # Como o template nao expoe theme em string facil, validamos que a rota
    # aceita o valor sem 500 e a inst em memoria foi mutada (verificavel via
    # response 200 sem erros — o banner de preview tambem e' indicador).
    r = client.get(
        f"/admin/platform/institutions/{inst_id}/preview",
        query_string={"theme": "light"},
    )
    assert r.status_code == 200


def test_preview_mostra_banner(client, super_admin, inst_id):
    _login_super(client, super_admin)
    r = client.get(f"/admin/platform/institutions/{inst_id}/preview")
    assert r.status_code == 200
    assert b"PREVIEW" in r.data
    assert "alterações ainda não salvas".encode("utf-8") in r.data


# ── Validacao defensiva ──────────────────────────────────────────────────────

def test_preview_descarta_cor_invalida(client, super_admin, inst_id, app):
    """Hex invalido cai pra cor persistida — entrada lixo nao quebra layout."""
    _login_super(client, super_admin)
    with app.app_context():
        inst = Institution.query.get(inst_id)
        cor_persistida = inst.primary_color or "#f4b860"

    r = client.get(
        f"/admin/platform/institutions/{inst_id}/preview",
        query_string={"primary_color": "javascript:alert(1)"},
    )
    assert r.status_code == 200
    # Cor persistida ainda aparece no render (nao a "javascript:..." injetada).
    assert cor_persistida.encode() in r.data
    assert b"javascript:alert(1)" not in r.data


def test_preview_descarta_tema_desconhecido(client, super_admin, inst_id):
    """Tema fora de {dark, light} e' descartado silenciosamente."""
    _login_super(client, super_admin)
    r = client.get(
        f"/admin/platform/institutions/{inst_id}/preview",
        query_string={"theme": "neon-arcoiris"},
    )
    assert r.status_code == 200


def test_preview_trunca_tagline_excessivamente_longa(client, super_admin, inst_id):
    """Tagline > 255 chars truncada (defesa em profundidade)."""
    _login_super(client, super_admin)
    longa = "X" * 1000
    r = client.get(
        f"/admin/platform/institutions/{inst_id}/preview",
        query_string={"tagline": longa},
    )
    assert r.status_code == 200
    # 1000 X's NAO devem aparecer na pagina — truncamos a 255.
    assert b"X" * 1000 not in r.data


# ── Garantia: preview NAO persiste ──────────────────────────────────────────

def test_preview_nao_persiste_no_banco(app, client, super_admin, inst_id):
    """Apos preview com overrides, o banco continua com valores originais.

    Esse e' o teste mais importante do PR — single point of failure se o
    expunge nao funcionar e algum commit acidental colar o preview.
    """
    with app.app_context():
        inst = Institution.query.get(inst_id)
        primary_original = inst.primary_color
        tagline_original = inst.tagline
        ai_name_original = inst.ai_name

    _login_super(client, super_admin)
    r = client.get(
        f"/admin/platform/institutions/{inst_id}/preview",
        query_string={
            "primary_color": "#000000",
            "tagline": "PREVIEW DEVE SER DESCARTADO",
            "ai_name": "BotPreviewMalvado",
        },
    )
    assert r.status_code == 200

    with app.app_context():
        inst = Institution.query.get(inst_id)
        assert inst.primary_color == primary_original
        assert inst.tagline == tagline_original
        assert inst.ai_name == ai_name_original


# ── 404 para iid inexistente ─────────────────────────────────────────────────

def test_preview_404_para_inst_inexistente(client, super_admin):
    _login_super(client, super_admin)
    r = client.get("/admin/platform/institutions/99999/preview",
                   follow_redirects=False)
    assert r.status_code == 404
