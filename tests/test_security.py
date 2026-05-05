"""Testes do hardening de seguranca: lockout, auditoria e politica de senha."""
import pytest

from app.extensions import db
from app.helpers import validate_password_strength
from app.models import AdminAuditLog, AuthLog, User


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def user(app):
    """Cria um super_admin com senha forte para os testes."""
    with app.app_context():
        u = User(email="auditor@flex.com", name="Auditor", role="super_admin", active=True)
        u.set_password("Senha-Forte-2026!")
        db.session.add(u)
        db.session.commit()
        return u.id


def _login(client, email, password):
    return client.post(
        "/admin/login",
        data={"email": email, "password": password, "_csrf_token": "x"},
        # CSRF desligado em testing — qualquer valor passa.
        follow_redirects=False,
    )


# ── Politica de senha forte ───────────────────────────────────────────────────

def test_senha_curta_rejeitada():
    erros = validate_password_strength("abc123")
    assert any("12 caracteres" in e for e in erros)


def test_senha_sem_variedade_rejeitada():
    # Tem 12+ chars mas so uma classe (so minusculas).
    erros = validate_password_strength("abcdefghijkl")
    assert any("3 categorias" in e for e in erros)


def test_senha_em_lista_de_fracas_rejeitada():
    erros = validate_password_strength("flexmedia2024")
    assert any("comuns" in e for e in erros)


def test_senha_forte_aceita():
    assert validate_password_strength("Strong-Pass-2026!") == []


# ── Lockout por brute-force ──────────────────────────────────────────────────

def test_login_falho_incrementa_contador(app, client, user):
    """Cada senha errada incrementa failed_login_count."""
    for _ in range(3):
        _login(client, "auditor@flex.com", "errada")

    with app.app_context():
        u = User.query.get(user)
        assert u.failed_login_count == 3
        assert not u.is_locked()


def test_lockout_apos_atingir_threshold(app, client, user):
    """5 falhas seguidas (threshold default) bloqueiam a conta."""
    app.config["LOCKOUT_THRESHOLD"] = 5
    app.config["LOCKOUT_MINUTES"] = 15

    for _ in range(5):
        _login(client, "auditor@flex.com", "errada")

    with app.app_context():
        u = User.query.get(user)
        assert u.is_locked()
        assert u.failed_login_count == 5

    # Mesmo com a senha CERTA, login deve recusar enquanto bloqueado.
    r = _login(client, "auditor@flex.com", "Senha-Forte-2026!")
    assert r.status_code == 200  # renderiza login com erro, sem redirect


def test_login_sucesso_zera_contador(app, client, user):
    """Login bem-sucedido limpa failed_login_count e locked_until."""
    for _ in range(2):
        _login(client, "auditor@flex.com", "errada")
    _login(client, "auditor@flex.com", "Senha-Forte-2026!")

    with app.app_context():
        u = User.query.get(user)
        assert u.failed_login_count == 0
        assert u.locked_until is None
        assert u.last_login_at is not None


# ── Enumeracao de e-mail ─────────────────────────────────────────────────────

def test_email_inexistente_nao_vaza_enumeracao(client):
    """Resposta para email inexistente == resposta para senha errada."""
    r1 = _login(client, "naoexiste@flex.com", "qualquer")
    r2 = _login(client, "auditor@flex.com", "errada")
    # Ambos renderizam a pagina de login; nao usamos status diferente.
    assert r1.status_code == r2.status_code


# ── Audit log ────────────────────────────────────────────────────────────────

def test_audit_log_registra_login_ok(app, client, user):
    _login(client, "auditor@flex.com", "Senha-Forte-2026!")

    with app.app_context():
        actions = [e.action for e in AdminAuditLog.query.all()]
        assert "login.success" in actions


def test_audit_log_registra_login_fail(app, client, user):
    _login(client, "auditor@flex.com", "errada")

    with app.app_context():
        actions = [e.action for e in AdminAuditLog.query.all()]
        assert "login.fail" in actions


def test_authlog_registra_tentativa(app, client, user):
    _login(client, "auditor@flex.com", "errada")

    with app.app_context():
        log = AuthLog.query.first()
        assert log is not None
        assert log.success is False


# ── Headers de seguranca ─────────────────────────────────────────────────────

def test_headers_basicos_aplicados(client):
    r = client.get("/admin/login")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert r.headers.get("X-Frame-Options") == "DENY"
    assert "Permissions-Policy" in r.headers


def test_admin_tem_csp_restrita(client):
    r = client.get("/admin/login")
    csp = r.headers.get("Content-Security-Policy", "")
    assert "frame-ancestors 'none'" in csp
    # Admin nao deve permitir CDNs externas em script-src.
    assert "cdn.jsdelivr.net" not in csp.split("script-src")[1].split(";")[0] \
        if "script-src" in csp else True


def test_admin_no_cache(client):
    r = client.get("/admin/login")
    assert "no-store" in r.headers.get("Cache-Control", "")
