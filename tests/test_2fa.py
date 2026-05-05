"""Testes do 2FA TOTP — setup, challenge, codigos de backup e enforcement."""
import pyotp
import pytest

from app.extensions import db
from app.models import AdminAuditLog, User
from app.twofa import generate_backup_codes, generate_totp_secret, verify_totp


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def super_admin(app):
    """Super admin com senha forte e SEM 2FA configurado."""
    with app.app_context():
        u = User(email="adm@flex.com", name="Admin", role="super_admin", active=True)
        u.set_password("Senha-Forte-2026!")
        db.session.add(u)
        db.session.commit()
        return u.id


@pytest.fixture
def super_admin_com_2fa(app):
    """Super admin ja com 2FA ativo e segredo conhecido."""
    with app.app_context():
        secret = generate_totp_secret()
        u = User(email="adm2fa@flex.com", name="Admin 2FA", role="super_admin", active=True)
        u.set_password("Senha-Forte-2026!")
        u.totp_secret = secret
        u.totp_enabled = True
        u.set_backup_codes(["abcd-1234", "efgh-5678"])
        db.session.add(u)
        db.session.commit()
        return {"id": u.id, "secret": secret}


def _login(client, email, password):
    return client.post(
        "/admin/login",
        data={"email": email, "password": password, "_csrf_token": "x"},
        follow_redirects=False,
    )


def _challenge(client, code):
    return client.post(
        "/admin/2fa/challenge",
        data={"code": code, "_csrf_token": "x"},
        follow_redirects=False,
    )


# ── Helpers TOTP ──────────────────────────────────────────────────────────────

def test_verify_totp_aceita_codigo_correto():
    secret = generate_totp_secret()
    code = pyotp.TOTP(secret).now()
    assert verify_totp(secret, code) is True


def test_verify_totp_rejeita_codigo_invalido():
    secret = generate_totp_secret()
    assert verify_totp(secret, "000000") is False


def test_verify_totp_rejeita_formato_invalido():
    secret = generate_totp_secret()
    assert verify_totp(secret, "abc") is False
    assert verify_totp(secret, "") is False
    assert verify_totp(secret, "12345") is False  # 5 digitos


def test_backup_codes_sao_unicos_e_formatados():
    codes = generate_backup_codes()
    assert len(codes) == 10
    assert len(set(codes)) == 10
    for c in codes:
        assert len(c) == 9 and c[4] == "-"


# ── Login com 2FA ─────────────────────────────────────────────────────────────

def test_login_com_2fa_redireciona_para_challenge(client, super_admin_com_2fa):
    r = _login(client, "adm2fa@flex.com", "Senha-Forte-2026!")
    assert r.status_code == 302
    assert "/2fa/challenge" in r.headers["Location"]


def test_challenge_aceita_codigo_correto(app, client, super_admin_com_2fa):
    _login(client, "adm2fa@flex.com", "Senha-Forte-2026!")
    code = pyotp.TOTP(super_admin_com_2fa["secret"]).now()
    r = _challenge(client, code)
    assert r.status_code == 302
    # Apos sucesso vai para o dashboard de plataforma.
    assert "/admin/platform" in r.headers["Location"]


def test_challenge_aceita_codigo_de_backup(app, client, super_admin_com_2fa):
    _login(client, "adm2fa@flex.com", "Senha-Forte-2026!")
    r = _challenge(client, "abcd-1234")
    assert r.status_code == 302
    with app.app_context():
        u = User.query.get(super_admin_com_2fa["id"])
        # Codigo consumido — restou um.
        assert u.remaining_backup_codes() == 1


def test_challenge_rejeita_codigo_invalido(app, client, super_admin_com_2fa):
    _login(client, "adm2fa@flex.com", "Senha-Forte-2026!")
    r = _challenge(client, "000000")
    assert r.status_code == 200  # renderiza challenge com erro
    with app.app_context():
        u = User.query.get(super_admin_com_2fa["id"])
        assert u.failed_login_count == 1


def test_challenge_sem_pending_redireciona_login(client):
    r = _challenge(client, "123456")
    assert r.status_code == 302
    assert "/admin/login" in r.headers["Location"]


def test_codigo_backup_nao_pode_ser_reusado(app, client, super_admin_com_2fa):
    _login(client, "adm2fa@flex.com", "Senha-Forte-2026!")
    r1 = _challenge(client, "abcd-1234")
    assert r1.status_code == 302

    # Logout e tenta de novo com o mesmo codigo.
    client.get("/admin/logout")
    _login(client, "adm2fa@flex.com", "Senha-Forte-2026!")
    r2 = _challenge(client, "abcd-1234")
    assert r2.status_code == 200  # rejeitado


def test_2fa_falhas_acionam_lockout(app, client, super_admin_com_2fa):
    """Brute-force no challenge tambem incrementa contador de lockout."""
    app.config["LOCKOUT_THRESHOLD"] = 3
    _login(client, "adm2fa@flex.com", "Senha-Forte-2026!")
    for _ in range(3):
        _challenge(client, "000000")

    with app.app_context():
        u = User.query.get(super_admin_com_2fa["id"])
        assert u.is_locked()


# ── Enforcement: super_admin sem 2FA ──────────────────────────────────────────

def test_super_admin_sem_2fa_redireciona_para_setup(client, super_admin):
    """Apos login, super_admin sem TOTP cai no setup forcado.

    No novo fluxo, login_user NAO acontece para super_admin sem TOTP — a
    sessao fica em estado "pending_totp_setup" e o redirect ja vai direto
    para /admin/2fa/setup. Tentativa de acessar /admin/platform/ sem auth
    real cai no login.
    """
    r = _login(client, "adm@flex.com", "Senha-Forte-2026!")
    assert r.status_code == 302
    assert "/2fa/setup" in r.headers["Location"]

    # Sem auth real, /admin/platform/ deve redirecionar para o login.
    bloqueio = client.get("/admin/platform/", follow_redirects=False)
    assert bloqueio.status_code == 302
    assert "/admin/login" in bloqueio.headers["Location"]


def test_setup_aceita_codigo_valido_e_ativa_2fa(app, client, super_admin):
    """Fluxo completo de cadastro: GET → POST com codigo do app."""
    _login(client, "adm@flex.com", "Senha-Forte-2026!")
    # GET cria o segredo provisorio na sessao.
    r_get = client.get("/admin/2fa/setup")
    assert r_get.status_code == 200

    with client.session_transaction() as sess:
        secret = sess["_2fa_pending_secret"]

    code = pyotp.TOTP(secret).now()
    r_post = client.post(
        "/admin/2fa/setup",
        data={"code": code, "_csrf_token": "x"},
    )
    assert r_post.status_code == 200
    # Deve renderizar a pagina de codigos de backup.
    assert b"backup" in r_post.data.lower() or b"codigo" in r_post.data.lower()

    with app.app_context():
        u = User.query.get(super_admin)
        assert u.totp_enabled is True
        assert u.totp_secret == secret
        assert u.remaining_backup_codes() == 10


# ── Auditoria ─────────────────────────────────────────────────────────────────

def test_audit_log_registra_2fa_enabled(app, client, super_admin):
    _login(client, "adm@flex.com", "Senha-Forte-2026!")
    client.get("/admin/2fa/setup")
    with client.session_transaction() as sess:
        secret = sess["_2fa_pending_secret"]
    client.post("/admin/2fa/setup", data={"code": pyotp.TOTP(secret).now(), "_csrf_token": "x"})

    with app.app_context():
        actions = [e.action for e in AdminAuditLog.query.all()]
        assert "user.2fa_enabled" in actions


def test_audit_log_registra_2fa_fail(app, client, super_admin_com_2fa):
    _login(client, "adm2fa@flex.com", "Senha-Forte-2026!")
    _challenge(client, "000000")

    with app.app_context():
        actions = [e.action for e in AdminAuditLog.query.all()]
        assert "user.2fa_fail" in actions


def test_audit_log_registra_uso_de_backup(app, client, super_admin_com_2fa):
    _login(client, "adm2fa@flex.com", "Senha-Forte-2026!")
    _challenge(client, "abcd-1234")

    with app.app_context():
        actions = [e.action for e in AdminAuditLog.query.all()]
        assert "user.2fa_backup_used" in actions
