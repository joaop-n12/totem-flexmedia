"""Testes do endpoint de heartbeat dos totens.

Cobre os cenarios principais:
  - Sucesso (HMAC valido) → 200
  - Falta de header → 401
  - Timestamp fora da janela (replay) → 401
  - Assinatura invalida → 401
  - Chave revogada → 401
  - Corpo alterado apos assinatura → 401
  - api_key_id alheio na assinatura → 401

Importante: o segredo NAO trafega no header — apenas a assinatura HMAC
calculada localmente pelo totem.
"""
import hashlib
import hmac
import json
import os
import time
from datetime import datetime, timedelta
from unittest.mock import patch

import pytest

from app.extensions import db
from app.models import Institution, TotemDevice
from app.models.device import generate_api_key_id, generate_api_key_secret


@pytest.fixture
def device(app):
    """Cria um dispositivo provisionado com segredo conhecido."""
    with app.app_context():
        inst = Institution.query.filter_by(slug="teste").first()
        secret = generate_api_key_secret()
        d = TotemDevice(
            institution_id=inst.id,
            name="Totem Teste 01",
            api_key_id=generate_api_key_id(),
            status="active",
        )
        d.set_secret(secret)
        db.session.add(d)
        db.session.commit()
        # Retornamos os dados em texto puro (so disponiveis na criacao).
        return {
            "id": d.id,
            "api_key_id": d.api_key_id,
            "secret": secret,
        }


def _sign(api_key_id: str, secret: str, timestamp: str, body: bytes) -> str:
    """HMAC mesma formula do servidor: '<api_key_id>.<timestamp>.' + body."""
    return hmac.new(
        key=secret.encode("utf-8"),
        msg=f"{api_key_id}.{timestamp}.".encode("utf-8") + body,
        digestmod=hashlib.sha256,
    ).hexdigest()


def _headers(api_key_id, timestamp, signature):
    """Headers do heartbeat — sem X-Totem-Secret (segredo nao trafega)."""
    return {
        "X-Totem-Key": api_key_id,
        "X-Totem-Timestamp": timestamp,
        "X-Totem-Signature": signature,
        "Content-Type": "application/json",
    }


def test_heartbeat_sucesso(app, client, device):
    body = json.dumps({"app_version": "1.0.0", "cpu_temp_c": 48.3,
                       "free_disk_mb": 2300, "uptime_seconds": 3600}).encode()
    ts = str(int(time.time()))
    sig = _sign(device["api_key_id"], device["secret"], ts, body)

    r = client.post(
        "/api/heartbeat",
        data=body,
        headers=_headers(device["api_key_id"], ts, sig),
    )
    assert r.status_code == 200
    assert r.json["status"] == "ok"

    with app.app_context():
        d = TotemDevice.query.get(device["id"])
        assert d.last_seen_at is not None
        assert d.app_version == "1.0.0"
        assert d.cpu_temp_c == 48.3


def test_heartbeat_sem_headers_recusa(client):
    r = client.post("/api/heartbeat", data="{}", content_type="application/json")
    assert r.status_code == 401


def test_heartbeat_timestamp_velho_recusa(client, device):
    """Replay attack: timestamp 1 hora no passado nao deve passar."""
    body = b"{}"
    velho = str(int(time.time() - 3600))
    sig = _sign(device["api_key_id"], device["secret"], velho, body)

    r = client.post(
        "/api/heartbeat",
        data=body,
        headers=_headers(device["api_key_id"], velho, sig),
    )
    assert r.status_code == 401
    assert r.json["error"] == "timestamp_out_of_window"


def test_heartbeat_assinatura_invalida_recusa(client, device):
    body = b'{"app_version":"1.0.0"}'
    ts = str(int(time.time()))
    # Assinatura calculada com segredo errado.
    sig = _sign(device["api_key_id"], "segredo-errado", ts, body)

    r = client.post(
        "/api/heartbeat",
        data=body,
        headers=_headers(device["api_key_id"], ts, sig),
    )
    assert r.status_code == 401


def test_heartbeat_chave_revogada_recusa(app, client, device):
    with app.app_context():
        d = TotemDevice.query.get(device["id"])
        d.status = "revoked"
        db.session.commit()

    body = b"{}"
    ts = str(int(time.time()))
    sig = _sign(device["api_key_id"], device["secret"], ts, body)

    r = client.post(
        "/api/heartbeat",
        data=body,
        headers=_headers(device["api_key_id"], ts, sig),
    )
    assert r.status_code == 401


def test_heartbeat_corpo_alterado_recusa(client, device):
    """Corpo alterado apos assinatura → HMAC nao bate, recusa."""
    body_assinado = b'{"app_version":"1.0.0"}'
    ts = str(int(time.time()))
    sig = _sign(device["api_key_id"], device["secret"], ts, body_assinado)

    # Envia corpo diferente do que foi assinado.
    body_alterado = b'{"app_version":"9.9.9-malicioso"}'
    r = client.post(
        "/api/heartbeat",
        data=body_alterado,
        headers=_headers(device["api_key_id"], ts, sig),
    )
    assert r.status_code == 401


def test_heartbeat_api_key_id_diferente_recusa(client, device):
    """Assinatura com outro api_key_id no payload nao deve bater.

    Garante que api_key_id entra na mensagem assinada — sem isso, atacante
    poderia copiar assinatura de um totem para o pedido de outro.
    """
    body = b"{}"
    ts = str(int(time.time()))
    # Assinatura calculada com api_key_id "errado", mas envia o real no header.
    sig = _sign("tk_outro_qualquer", device["secret"], ts, body)

    r = client.post(
        "/api/heartbeat",
        data=body,
        headers=_headers(device["api_key_id"], ts, sig),
    )
    assert r.status_code == 401


def test_heartbeat_aceita_timestamp_independente_de_tz(client, device, monkeypatch):
    """Servidor deve comparar timestamps em UTC real (time.time), nao via
    datetime.utcnow().timestamp() — esse ultimo e' interpretado como hora
    local em datetime naive, gerando skew falso de varias horas em hosts com
    TZ != UTC.

    Regressao: em maio/2026 daemon em Pi com TZ=America/Sao_Paulo enviava
    time.time() correto, servidor calculava utcnow().timestamp() e cuspia
    'timestamp_out_of_window' apesar de 0s de diferenca real.
    """
    # Simula host em fuso horario distante de UTC. time.time() ignora TZ,
    # entao a verificacao server-side deve passar mesmo assim.
    monkeypatch.setenv("TZ", "America/Sao_Paulo")
    if hasattr(time, "tzset"):
        time.tzset()
    try:
        body = b'{"app_version":"tz-test"}'
        ts = str(int(time.time()))
        sig = _sign(device["api_key_id"], device["secret"], ts, body)
        r = client.post(
            "/api/heartbeat",
            data=body,
            headers=_headers(device["api_key_id"], ts, sig),
        )
        assert r.status_code == 200, (
            "Heartbeat falhou sob TZ nao-UTC — provavelmente o servidor voltou "
            "a usar datetime.utcnow().timestamp()."
        )
    finally:
        monkeypatch.delenv("TZ", raising=False)
        if hasattr(time, "tzset"):
            time.tzset()
