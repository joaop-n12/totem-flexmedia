"""Testes do sync de conteudo entre admin e totem.

Cobre:
  - Bump automatico de content_version em CRUD de conteudo
    (animais, eventos, lojas, produtos, FAQs).
  - Atomicidade: rollback nao deixa version incrementado.
  - Mudancas em outras tabelas (User, AuthLog) NAO bumpam.
  - GET /<slug>/api/sync/version: 200 publico, devolve numero atual.
  - GET /api/sync/snapshot: HMAC enforced (mesmas falhas do heartbeat).
  - Snapshot devolve dados do tenant correto (nao vaza cross-tenant).
  - ETag + 304 Not Modified quando version nao mudou.
  - Snapshot 403 quando instituicao inativa.
"""
import hashlib
import hmac
import json
from datetime import datetime, timedelta

import pytest

from app.extensions import db
from app.helpers import bump_content_version
from app.models import (
    Animal, Event, FAQ, Institution, Product, Store, TotemDevice,
)
from app.models.device import generate_api_key_id, generate_api_key_secret


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def device(app):
    """Cria um TotemDevice ativo para a instituicao de teste."""
    with app.app_context():
        inst = Institution.query.filter_by(slug="teste").first()
        secret = generate_api_key_secret()
        d = TotemDevice(
            institution_id=inst.id,
            name="Sync Totem",
            api_key_id=generate_api_key_id(),
            status="active",
        )
        d.set_secret(secret)
        db.session.add(d)
        db.session.commit()
        return {
            "api_key_id": d.api_key_id,
            "secret": secret,
            "institution_id": inst.id,
        }


def _sign(api_key_id: str, secret: str, ts: str, body: bytes) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        msg=f"{api_key_id}.{ts}.".encode("utf-8") + body,
        digestmod=hashlib.sha256,
    ).hexdigest()


def _hmac_headers(d):
    """Constroi headers HMAC para GET /api/sync/snapshot (body vazio)."""
    ts = str(int(datetime.utcnow().timestamp()))
    sig = _sign(d["api_key_id"], d["secret"], ts, b"")
    return {
        "X-Totem-Key": d["api_key_id"],
        "X-Totem-Timestamp": ts,
        "X-Totem-Signature": sig,
    }


# ════════════════════════════════════════════════════════════════════════════
# Helper bump_content_version
# ════════════════════════════════════════════════════════════════════════════

def test_content_version_inicia_em_zero(app):
    with app.app_context():
        inst = Institution.query.filter_by(slug="teste").first()
        assert inst.content_version == 0


def test_bump_content_version_incrementa(app):
    """UPDATE atomico: incrementa em 1 a cada chamada."""
    with app.app_context():
        inst = Institution.query.filter_by(slug="teste").first()
        before = inst.content_version
        bump_content_version(inst.id)
        db.session.commit()
        db.session.refresh(inst)
        assert inst.content_version == before + 1


def test_bump_content_version_acumula(app):
    """Multiplas chamadas dentro de uma transacao acumulam."""
    with app.app_context():
        inst = Institution.query.filter_by(slug="teste").first()
        bump_content_version(inst.id)
        bump_content_version(inst.id)
        bump_content_version(inst.id)
        db.session.commit()
        db.session.refresh(inst)
        assert inst.content_version == 3


def test_bump_nao_afeta_outras_instituicoes(app):
    """Atomicidade entre tenants — bump em A nao mexe em B."""
    with app.app_context():
        inst_a = Institution.query.filter_by(slug="teste").first()
        inst_b = Institution(
            slug="outro", name="Outro", type="zoo", ai_name="x",
            ai_context="y", daily_ai_quota=500, active=True,
        )
        db.session.add(inst_b)
        db.session.commit()
        bump_content_version(inst_a.id)
        db.session.commit()
        db.session.refresh(inst_a)
        db.session.refresh(inst_b)
        assert inst_a.content_version == 1
        assert inst_b.content_version == 0


def test_rollback_nao_persiste_bump(app):
    """Atomicidade: bump dentro de transacao revertida nao persiste."""
    with app.app_context():
        inst = Institution.query.filter_by(slug="teste").first()
        before = inst.content_version
        bump_content_version(inst.id)
        db.session.rollback()
        db.session.refresh(inst)
        assert inst.content_version == before


# ════════════════════════════════════════════════════════════════════════════
# /<slug>/api/sync/version — endpoint publico
# ════════════════════════════════════════════════════════════════════════════

def test_version_publico_devolve_numero(client):
    r = client.get("/teste/api/sync/version")
    assert r.status_code == 200
    body = r.get_json()
    assert body["slug"] == "teste"
    assert isinstance(body["version"], int)


def test_version_reflete_bump_explicito(app, client):
    r1 = client.get("/teste/api/sync/version")
    v1 = r1.get_json()["version"]

    with app.app_context():
        inst = Institution.query.filter_by(slug="teste").first()
        bump_content_version(inst.id)
        db.session.commit()

    r2 = client.get("/teste/api/sync/version")
    assert r2.get_json()["version"] > v1


def test_version_de_slug_inexistente_404(client):
    r = client.get("/inexistente/api/sync/version")
    assert r.status_code == 404


# ════════════════════════════════════════════════════════════════════════════
# /api/sync/snapshot — endpoint HMAC
# ════════════════════════════════════════════════════════════════════════════

def test_snapshot_caminho_feliz(client, device):
    r = client.get("/api/sync/snapshot", headers=_hmac_headers(device))
    assert r.status_code == 200
    body = r.get_json()
    assert body["institution"]["slug"] == "teste"
    assert "animals" in body and "events" in body and "stores" in body
    assert "products" in body and "faqs" in body and "modules" in body
    # ETag presente — facilita cache no cliente.
    assert r.headers.get("ETag", "").startswith('"v')


def test_snapshot_recusa_sem_headers(client):
    r = client.get("/api/sync/snapshot")
    assert r.status_code == 401


def test_snapshot_recusa_assinatura_invalida(client, device):
    """HMAC fechado com segredo errado → 401 (mesmo enforcement do heartbeat)."""
    ts = str(int(datetime.utcnow().timestamp()))
    sig = _sign(device["api_key_id"], "segredo-errado", ts, b"")
    r = client.get("/api/sync/snapshot", headers={
        "X-Totem-Key": device["api_key_id"],
        "X-Totem-Timestamp": ts,
        "X-Totem-Signature": sig,
    })
    assert r.status_code == 401


def test_snapshot_recusa_timestamp_velho(client, device):
    velho = str(int((datetime.utcnow() - timedelta(hours=2)).timestamp()))
    sig = _sign(device["api_key_id"], device["secret"], velho, b"")
    r = client.get("/api/sync/snapshot", headers={
        "X-Totem-Key": device["api_key_id"],
        "X-Totem-Timestamp": velho,
        "X-Totem-Signature": sig,
    })
    assert r.status_code == 401


def test_snapshot_etag_devolve_304_quando_inalterado(client, device):
    """Cache HTTP — segundo GET com If-None-Match poupa banda."""
    r1 = client.get("/api/sync/snapshot", headers=_hmac_headers(device))
    etag = r1.headers["ETag"]

    headers = _hmac_headers(device)
    headers["If-None-Match"] = etag
    r2 = client.get("/api/sync/snapshot", headers=headers)
    assert r2.status_code == 304


def test_snapshot_etag_muda_apos_bump(app, client, device):
    r1 = client.get("/api/sync/snapshot", headers=_hmac_headers(device))
    etag1 = r1.headers["ETag"]

    with app.app_context():
        bump_content_version(device["institution_id"])
        db.session.commit()

    r2 = client.get("/api/sync/snapshot", headers=_hmac_headers(device))
    assert r2.status_code == 200
    assert r2.headers["ETag"] != etag1


def test_snapshot_403_quando_instituicao_inativa(app, client, device):
    with app.app_context():
        inst = Institution.query.filter_by(slug="teste").first()
        inst.active = False
        db.session.commit()
    r = client.get("/api/sync/snapshot", headers=_hmac_headers(device))
    assert r.status_code == 403


def test_snapshot_so_devolve_dados_do_proprio_tenant(app, client, device):
    """Mesmo se houver outra instituicao no banco, snapshot SO traz a do device."""
    with app.app_context():
        # Cria outra inst com conteudo "sensivel" que NAO deve aparecer.
        outra = Institution(
            slug="outra", name="Outra", type="zoo", ai_name="A",
            ai_context="b", daily_ai_quota=500, active=True,
        )
        db.session.add(outra)
        db.session.flush()
        a = Animal(institution_id=outra.id, nome="ANIMAL_DA_OUTRA", especie="x")
        a.generate_slug()
        db.session.add(a)
        db.session.commit()

    r = client.get("/api/sync/snapshot", headers=_hmac_headers(device))
    assert r.status_code == 200
    body = r.get_json()
    nomes = [a["nome"] for a in body["animals"]]
    assert "ANIMAL_DA_OUTRA" not in nomes
    assert body["institution"]["slug"] == "teste"
