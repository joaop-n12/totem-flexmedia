"""Testes do modulo de sensores (DHT11/DHT22 + HC-SR04) e endpoints relacionados.

Cobre:
  - Modo mock automatico fora do Pi (sem RPi.GPIO instalado).
  - Dht22Sensor.start() emite leituras plausiveis.
  - /api/heartbeat aceita ambient_temp_c, ambient_humidity_pct e persiste no
    TotemDevice.
  - Sanity-check de range (DHT22 fora de -40..80 °C / 0..100% e' descartado).
  - /api/local/wake exige loopback + X-Wake-Secret.
  - /api/local/wake-stream nega acesso fora do loopback.
"""
import hashlib
import hmac
import json
import threading
from datetime import datetime

import pytest

from app.extensions import db
from app.models import Institution, TotemDevice
from app.models.device import generate_api_key_id, generate_api_key_secret
from app.sensors import Dht22Sensor, SensorReading, is_pi_hardware


# ════════════════════════════════════════════════════════════════════════════
# Sensores em si (mock mode)
# ════════════════════════════════════════════════════════════════════════════

def test_is_pi_hardware_falso_em_dev():
    """Em laptop/CI, /proc/device-tree/model nao existe → mock obrigatorio."""
    assert is_pi_hardware() is False


def test_dht22_sensor_emite_leitura_em_mock():
    received: list[SensorReading] = []
    evt = threading.Event()

    def cb(reading: SensorReading) -> None:
        received.append(reading)
        evt.set()

    dht = Dht22Sensor(interval_seconds=0.1)
    assert dht.mock_mode is True
    dht.start(cb)
    try:
        assert evt.wait(timeout=2.0), "DHT mock deveria ter emitido leitura"
        r = received[0]
        assert r.source == "dht22"
        # Mock devolve valores dentro do range plausivel.
        assert -40 <= r.temp_c <= 80
        assert 0 <= r.humidity_pct <= 100
    finally:
        dht.stop()


# ════════════════════════════════════════════════════════════════════════════
# Heartbeat — aceita telemetria de sensores
# ════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def device(app):
    with app.app_context():
        inst = Institution.query.filter_by(slug="teste").first()
        secret = generate_api_key_secret()
        d = TotemDevice(
            institution_id=inst.id,
            name="Totem Sensor 01",
            api_key_id=generate_api_key_id(),
            status="active",
        )
        d.set_secret(secret)
        db.session.add(d)
        db.session.commit()
        return {"id": d.id, "api_key_id": d.api_key_id, "secret": secret}


def _sign(api_key_id: str, secret: str, ts: str, body: bytes) -> str:
    return hmac.new(
        secret.encode("utf-8"),
        msg=f"{api_key_id}.{ts}.".encode("utf-8") + body,
        digestmod=hashlib.sha256,
    ).hexdigest()


def _hb(client, device, payload: dict):
    body = json.dumps(payload).encode("utf-8")
    ts = str(int(datetime.utcnow().timestamp()))
    sig = _sign(device["api_key_id"], device["secret"], ts, body)
    return client.post("/api/heartbeat", data=body, headers={
        "X-Totem-Key": device["api_key_id"],
        "X-Totem-Timestamp": ts,
        "X-Totem-Signature": sig,
        "Content-Type": "application/json",
    })


def test_heartbeat_persiste_telemetria_de_sensores(app, client, device):
    r = _hb(client, device, {
        "ambient_temp_c": 25.7,
        "ambient_humidity_pct": 62.0,
    })
    assert r.status_code == 200
    with app.app_context():
        d = TotemDevice.query.get(device["id"])
        assert d.ambient_temp_c == 25.7
        assert d.ambient_humidity_pct == 62.0


def test_heartbeat_descarta_temp_fora_de_range(app, client, device):
    """Sensor com defeito reporta 999 °C? Ignoramos — nao corrompe a UI."""
    r = _hb(client, device, {"ambient_temp_c": 999.0, "ambient_humidity_pct": 50.0})
    assert r.status_code == 200
    with app.app_context():
        d = TotemDevice.query.get(device["id"])
        assert d.ambient_temp_c is None       # rejeitado
        assert d.ambient_humidity_pct == 50.0  # aceito


def test_heartbeat_descarta_humidade_fora_de_range(app, client, device):
    r = _hb(client, device, {"ambient_humidity_pct": 150.0})
    assert r.status_code == 200
    with app.app_context():
        d = TotemDevice.query.get(device["id"])
        assert d.ambient_humidity_pct is None


# ════════════════════════════════════════════════════════════════════════════
# Endpoints locais de wake-up (loopback only + secret)
# ════════════════════════════════════════════════════════════════════════════

def test_wake_local_recusa_sem_secret_configurado(client, monkeypatch):
    """Fail-closed — sem TOTEM_WAKE_SECRET no env, todo POST e' 503."""
    monkeypatch.delenv("TOTEM_WAKE_SECRET", raising=False)
    # Limpa tambem do app.config.
    r = client.post("/api/local/wake", json={})
    # Pode retornar 503 (sem secret) ou 401 (secret invalido) dependendo da
    # ordem de checks — ambos sao fail-closed.
    assert r.status_code in (401, 503)


def test_wake_local_aceita_com_secret(app, client, monkeypatch):
    monkeypatch.setenv("TOTEM_WAKE_SECRET", "segredo-de-teste")
    # Test client sempre chega como 127.0.0.1 → loopback OK.
    r = client.post(
        "/api/local/wake",
        json={"type": "distance", "distance_cm": 60.0, "source": "hcsr04"},
        headers={"X-Wake-Secret": "segredo-de-teste"},
    )
    assert r.status_code == 200
    assert r.json["ok"] is True


def test_wake_local_recusa_secret_errado(client, monkeypatch):
    monkeypatch.setenv("TOTEM_WAKE_SECRET", "segredo-real")
    r = client.post(
        "/api/local/wake",
        json={},
        headers={"X-Wake-Secret": "segredo-falso"},
    )
    assert r.status_code == 401


def test_wake_local_recusa_fora_de_loopback(app, client, monkeypatch):
    """Simula request vindo de IP de LAN — deve recusar mesmo com secret."""
    monkeypatch.setenv("TOTEM_WAKE_SECRET", "segredo")
    r = client.post(
        "/api/local/wake",
        json={},
        environ_base={"REMOTE_ADDR": "192.168.1.42"},
        headers={"X-Wake-Secret": "segredo"},
    )
    assert r.status_code == 403


def test_wake_stream_recusa_fora_de_loopback(client):
    r = client.get(
        "/api/local/wake-stream",
        environ_base={"REMOTE_ADDR": "10.0.0.5"},
    )
    assert r.status_code == 403


# ════════════════════════════════════════════════════════════════════════════
# Daemon — telemetria de ambiente no heartbeat
# ════════════════════════════════════════════════════════════════════════════

def test_daemon_inclui_telemetria_de_ambiente_no_heartbeat(app, client, device, monkeypatch):
    """Callback do DHT mock atualiza estado interno; heartbeat exporta."""
    from app.sensors.daemon import SensorDaemon
    monkeypatch.setenv("TOTEM_WAKE_SECRET", "segredo-integracao")

    daemon = SensorDaemon(
        wake_url="http://127.0.0.1:0/api/local/wake",   # nao usado aqui
        wake_secret="segredo-integracao",
        heartbeat_url="http://127.0.0.1:0/api/heartbeat",
        api_key_id=device["api_key_id"],
        api_key_secret=device["secret"],
    )
    daemon._on_env(SensorReading(source="dht22", timestamp=datetime.utcnow(),
                                 temp_c=26.5, humidity_pct=58.0))
    body = json.loads(daemon._heartbeat_payload())
    assert body["ambient_temp_c"] == 26.5
    assert body["ambient_humidity_pct"] == 58.0
