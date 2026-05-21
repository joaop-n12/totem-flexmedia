"""Smoke tests das rotas criticas do totem publico.

Objetivo: garantir que nenhuma das paginas publicas quebra com um
refactor acidental. Nao testa conteudo, apenas HTTP 200 / redirect.
"""


def test_index_redirects(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (301, 302)
    assert r.headers["Location"].endswith("/admin/login")


def test_selector_route_removed(client):
    r = client.get("/select", follow_redirects=False)
    assert r.status_code in (301, 302)
    assert r.headers["Location"].endswith("/admin/login")


def test_home_page(client):
    r = client.get("/teste/")
    assert r.status_code == 200
    assert b"Totem Teste" in r.data


def test_privacidade_global(client):
    r = client.get("/privacidade")
    assert r.status_code == 200
    assert "Privacidade".encode("utf-8") in r.data


def test_privacidade_instituicao(client):
    r = client.get("/teste/privacidade")
    assert r.status_code == 200


def test_offline_page(client):
    r = client.get("/offline")
    assert r.status_code == 200


def test_service_worker_served(client):
    r = client.get("/sw.js")
    assert r.status_code == 200
    assert r.headers.get("Service-Worker-Allowed") == "/"
    assert b"CACHE_VERSION" in r.data


def test_ia_page_quando_modulo_ativo(client):
    r = client.get("/teste/ia")
    assert r.status_code == 200


def test_404_instituicao_inexistente(client):
    r = client.get("/instituicao-que-nao-existe/")
    assert r.status_code == 404


def test_admin_login_page(client):
    r = client.get("/admin/login")
    assert r.status_code == 200
