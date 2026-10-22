"""Controle de acesso e fluxo de configuracao do usuario operacional."""
from app.extensions import db
from app.models import Institution, TotemDevice, User


def _user(email, role, institution_id=None):
    user = User(email=email, name=email, role=role, institution_id=institution_id, active=True)
    user.set_password("SenhaOperacional#2026")
    db.session.add(user)
    db.session.commit()
    return user


def _device(institution, name):
    device = TotemDevice(
        institution_id=institution.id,
        name=name,
        api_key_id=f"tk_{name.lower().replace(' ', '_')}",
        status="active",
    )
    device.set_secret("segredo-de-teste")
    db.session.add(device)
    db.session.commit()
    return device


def _login(client, email):
    return client.post(
        "/admin/login",
        data={"email": email, "password": "SenhaOperacional#2026"},
        follow_redirects=False,
    )


def _login_with_next(client, email, next_path):
    return client.post(
        f"/admin/login?next={next_path}",
        data={"email": email, "password": "SenhaOperacional#2026"},
        follow_redirects=False,
    )


def test_client_admin_login_continues_to_dashboard(client, inst):
    _user("admin@teste.local", "client_admin", inst.id)
    response = _login(client, "admin@teste.local")
    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/admin/institutions/{inst.id}/")


def test_operational_login_select_start_change_and_restore(client, inst):
    operator = _user("operador@teste.local", "operational")
    first = _device(inst, "Totem A")
    other_inst = Institution(slug="outra", name="Outra Empresa", type="shopping", active=True)
    db.session.add(other_inst)
    db.session.commit()
    second = _device(other_inst, "Totem B")

    response = _login(client, operator.email)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/operacional/")

    selection = client.get("/operacional/")
    assert selection.status_code == 200
    assert b"Totem A" in selection.data
    assert b"Totem B" in selection.data
    assert b"Dashboard" not in selection.data

    started = client.post("/operacional/", data={"device_id": first.id})
    assert started.status_code == 302
    assert started.headers["Location"].endswith("/teste/")
    assert client.get("/operacional/iniciar").headers["Location"].endswith("/teste/")

    changed = client.post("/operacional/", data={"device_id": second.id})
    assert changed.headers["Location"].endswith("/outra/")
    assert client.get("/operacional/iniciar").headers["Location"].endswith("/outra/")


def test_operational_cannot_access_administration(client, inst):
    operator = _user("restrito@teste.local", "operational")
    _login(client, operator.email)

    protected_urls = (
        "/admin/platform/",
        "/admin/platform/institutions/",
        "/admin/platform/users/",
        f"/admin/institutions/{inst.id}/",
    )
    for url in protected_urls:
        assert client.get(url).status_code == 403


def test_operational_ignores_admin_next_and_rejects_invalid_saved_device(client, inst):
    operator = _user("next@teste.local", "operational")
    device = _device(inst, "Totem Revogado")
    response = _login_with_next(client, operator.email, "/admin/platform/")
    assert response.headers["Location"].endswith("/operacional/")

    client.post("/operacional/", data={"device_id": device.id})
    device.status = "revoked"
    db.session.commit()
    response = client.get("/operacional/iniciar")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/operacional/")
    with client.session_transaction() as saved_session:
        assert "operational_device_id" not in saved_session


def test_admin_cannot_access_operational_selector(client, inst):
    admin = _user("cliente@teste.local", "client_admin", inst.id)
    _login(client, admin.email)
    assert client.get("/operacional/").status_code == 403
