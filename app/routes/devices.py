"""Monitoramento da frota de totens.

Endpoint publico (porem autenticado por HMAC):
  POST /api/heartbeat    — totem reporta status (incl. telemetria PIR/DHT22)

Endpoint local-only (consumido pelo daemon de sensores rodando no proprio Pi):
  POST /api/local/wake   — daemon avisa o Flask local de presenca; Flask faz
                            fan-out via SSE para o kiosk acordar.
  GET  /api/local/wake-stream — SSE consumido pelo kiosk (event-stream).

Endpoints admin (super_admin):
  GET  /admin/platform/devices            — listagem com status online/offline
  POST /admin/platform/devices/new        — provisiona novo totem (gera segredo)
  POST /admin/platform/devices/<id>/revoke — invalida a chave em campo
  GET  /admin/platform/audit              — lista de eventos de auditoria

Modelo de autenticacao:
  - O totem em campo guarda apenas o segredo localmente (chmod 600).
  - Cada requisicao envia: X-Totem-Key (publico) + X-Totem-Timestamp +
    X-Totem-Signature.
  - O servidor decifra o segredo cifrado em repouso (Fernet) e recalcula
    HMAC-SHA256(secret, "<api_key_id>.<timestamp>." + body).
  - Janela de aceitacao do timestamp: +/- HEARTBEAT_CLOCK_SKEW_SECONDS.
    Replays fora dessa janela sao rejeitados.
  - O segredo NUNCA trafega na rede apos o provisionamento. Se o TLS quebrar
    e o trafego for capturado, o atacante nao consegue forjar requisicoes
    nem se passar por outro totem (api_key_id entra na assinatura).
"""
import hmac as _hmac
import json
import os
import queue
import threading
from datetime import datetime, timedelta

from flask import (
    Blueprint, Response, abort, current_app, flash, jsonify,
    redirect, render_template, request, stream_with_context, url_for,
)

from app.extensions import db, limiter
from app.helpers import audit_log, super_admin_required, validate_csrf_token
from app.models import AdminAuditLog, Institution, TotemDevice
from app.models.audit import ACTION_DEVICE_CREATE, ACTION_DEVICE_REVOKE
from app.models.device import generate_api_key_id, generate_api_key_secret

devices_bp = Blueprint("devices", __name__)


# ════════════════════════════════════════════════════════════════════════════
# API publica (consumida pelos totens em campo)
# ════════════════════════════════════════════════════════════════════════════

def _check_timestamp(timestamp_str: str, skew_seconds: int) -> bool:
    """Aceita apenas timestamps dentro de uma janela curta (anti-replay)."""
    try:
        ts = int(timestamp_str)
    except (TypeError, ValueError):
        return False
    now = int(datetime.utcnow().timestamp())
    return abs(now - ts) <= skew_seconds


@devices_bp.route("/api/heartbeat", methods=["POST"])
@limiter.limit("60 per minute")
def heartbeat():
    """Recebe telemetria do totem.

    Headers obrigatorios:
      X-Totem-Key       — api_key_id publico (ex.: tk_a1b2c3...)
      X-Totem-Timestamp — unix timestamp em segundos (string)
      X-Totem-Signature — HMAC-SHA256(secret, "<api_key_id>.<timestamp>." + body) hex

    O segredo NAO trafega — fica apenas no totem e em forma cifrada no banco
    do servidor. O servidor decifra para recomputar a assinatura.

    Corpo JSON aceitando opcionalmente:
      app_version, cpu_temp_c, free_disk_mb, uptime_seconds
    """
    api_key_id = request.headers.get("X-Totem-Key", "").strip()
    timestamp = request.headers.get("X-Totem-Timestamp", "").strip()
    signature = request.headers.get("X-Totem-Signature", "").strip()

    if not (api_key_id and timestamp and signature):
        return jsonify(error="missing_auth_headers"), 401

    # 1. Janela de timestamp — defesa contra replay.
    skew = current_app.config.get("HEARTBEAT_CLOCK_SKEW_SECONDS", 300)
    if not _check_timestamp(timestamp, skew):
        return jsonify(error="timestamp_out_of_window"), 401

    # 2. Lookup do dispositivo. Resposta generica para nao vazar enumeracao.
    device = TotemDevice.query.filter_by(api_key_id=api_key_id).first()
    if not device or not device.is_active:
        # Resposta intencionalmente generica (nao revela se a chave existe).
        return jsonify(error="auth_failed"), 401

    # 3. Verifica HMAC em tempo constante. A mensagem inclui api_key_id —
    # impede que assinatura de um totem seja reutilizada com outro key id.
    raw_body = request.get_data() or b""
    if not device.verify_hmac(timestamp, raw_body, signature):
        return jsonify(error="invalid_signature"), 401

    # 4. Parsea telemetria — campos sao opcionais e tolerantes a tipo errado.
    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except (ValueError, UnicodeDecodeError):
        payload = {}

    def _maybe_float(v):
        try: return float(v) if v is not None else None
        except (TypeError, ValueError): return None

    def _maybe_int(v):
        try: return int(v) if v is not None else None
        except (TypeError, ValueError): return None

    # `is not None` (nao `or`) preserva valores zero legitimos (uptime=0,
    # cpu_temp=0.0). Antes, _maybe_int(0) or device.x descartava o zero.
    new_app_version = (payload.get("app_version") or "")[:40]
    new_cpu = _maybe_float(payload.get("cpu_temp_c"))
    new_disk = _maybe_int(payload.get("free_disk_mb"))
    new_uptime = _maybe_int(payload.get("uptime_seconds"))
    # Telemetria de sensores fisicos (PIR + DHT22) — opcional.
    new_temp = _maybe_float(payload.get("ambient_temp_c"))
    new_hum = _maybe_float(payload.get("ambient_humidity_pct"))

    device.last_seen_at = datetime.utcnow()
    device.last_ip = request.remote_addr or device.last_ip
    if new_app_version:
        device.app_version = new_app_version
    if new_cpu is not None:
        device.cpu_temp_c = new_cpu
    if new_disk is not None:
        device.free_disk_mb = new_disk
    if new_uptime is not None:
        device.uptime_seconds = new_uptime
    if new_temp is not None:
        # Sanity-check: DHT22 spec e' -40..80 °C. Fora disso e' ruido.
        if -40.0 <= new_temp <= 80.0:
            device.ambient_temp_c = new_temp
    if new_hum is not None:
        if 0.0 <= new_hum <= 100.0:
            device.ambient_humidity_pct = new_hum
    motion_iso = payload.get("last_motion_at")
    if isinstance(motion_iso, str) and motion_iso:
        try:
            device.last_motion_at = datetime.fromisoformat(motion_iso.replace("Z", ""))
        except ValueError:
            pass
    db.session.commit()

    # Devolve eventuais comandos pendentes para o totem (placeholder p/ OTA futuro).
    return jsonify(
        status="ok",
        server_time=int(datetime.utcnow().timestamp()),
        commands=[],  # futuro: ["restart", "update:1.2.3", ...]
    ), 200


# ════════════════════════════════════════════════════════════════════════════
# Wake-up local (daemon de sensores → Flask local → kiosk via SSE)
# ════════════════════════════════════════════════════════════════════════════
#
# Este par de endpoints existe APENAS quando Flask e o daemon de sensores
# rodam na mesma maquina (cenario do Pi single-tenant). NAO sao usados
# quando o servidor e' remoto.
#
# Seguranca:
#  - /api/local/wake exige X-Wake-Secret (env TOTEM_WAKE_SECRET) e tambem
#    rejeita qualquer IP que nao seja loopback.
#  - /api/local/wake-stream e' acessivel sem auth — e' o proprio kiosk em
#    127.0.0.1 que se inscreve. Nao trafega segredo nenhum.
#
# Implementacao do fan-out: lista de Queues. Quando uma motion chega, um
# evento JSON e' enfileirado em todas as filas inscritas. Sem Redis — o
# kiosk e o Flask sao o mesmo processo logico.

_wake_lock = threading.Lock()
_wake_subscribers: list[queue.Queue] = []


def _broadcast_wake(payload: dict) -> int:
    """Envia evento para todos os listeners SSE conectados. Retorna a contagem."""
    msg = json.dumps(payload, default=str)
    with _wake_lock:
        listeners = list(_wake_subscribers)
    delivered = 0
    for q in listeners:
        try:
            q.put_nowait(msg)
            delivered += 1
        except queue.Full:
            # Cliente lento — descartar e' ok. PIR re-dispara em segundos.
            pass
    return delivered


def _is_loopback() -> bool:
    """Aceita apenas 127.0.0.1 / ::1. Defesa contra acesso por LAN se o
    Flask for exposto sem firewall."""
    addr = (request.remote_addr or "").strip()
    return addr in {"127.0.0.1", "::1", "localhost"}


@devices_bp.route("/api/local/wake", methods=["POST"])
def local_wake():
    """Daemon de sensores publica presenca aqui. Loopback + secret obrigatorios."""
    if not _is_loopback():
        return jsonify(error="forbidden"), 403
    secret_expected = (current_app.config.get("TOTEM_WAKE_SECRET")
                       or os.environ.get("TOTEM_WAKE_SECRET", ""))
    if not secret_expected:
        # Sem segredo configurado, recusamos por seguranca (fail-closed).
        return jsonify(error="wake_secret_not_configured"), 503
    secret_got = request.headers.get("X-Wake-Secret", "")
    if not _hmac.compare_digest(secret_expected, secret_got):
        return jsonify(error="invalid_wake_secret"), 401

    body = request.get_json(silent=True) or {}
    payload = {
        "type": "presence",
        "at": int(datetime.utcnow().timestamp()),
        "source": body.get("source", "pir"),
    }
    n = _broadcast_wake(payload)
    return jsonify(ok=True, listeners=n), 200


@devices_bp.route("/api/local/wake-stream")
def local_wake_stream():
    """SSE stream consumido pelo kiosk para reagir a presenca.

    O browser do kiosk faz `new EventSource('/api/local/wake-stream')` e
    recebe eventos JSON `{type: "presence", ...}`. Sem auth porque so o
    kiosk em 127.0.0.1 acessa.
    """
    if not _is_loopback():
        return jsonify(error="forbidden"), 403

    q: queue.Queue = queue.Queue(maxsize=10)
    with _wake_lock:
        _wake_subscribers.append(q)

    def _stream():
        try:
            # Greeting inicial — confirma para o cliente que o stream abriu.
            yield "event: ready\ndata: {}\n\n"
            while True:
                # timeout pequeno para enviar comentario keep-alive e
                # detectar desconexao do client (Flask fecha o gerador).
                try:
                    msg = q.get(timeout=15)
                    yield f"event: presence\ndata: {msg}\n\n"
                except queue.Empty:
                    yield ": keep-alive\n\n"
        finally:
            with _wake_lock:
                if q in _wake_subscribers:
                    _wake_subscribers.remove(q)

    return Response(
        stream_with_context(_stream()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # desativa buffer do Nginx
        },
    )


# ════════════════════════════════════════════════════════════════════════════
# Painel admin — frota e auditoria
# ════════════════════════════════════════════════════════════════════════════

ONLINE_THRESHOLD_MINUTES = 5  # totem que nao reportou em 5min e considerado offline


@devices_bp.route("/admin/platform/devices/")
@super_admin_required
def device_list():
    devices = TotemDevice.query.order_by(TotemDevice.created_at.desc()).all()
    institutions = Institution.query.order_by(Institution.name).all()
    cutoff = datetime.utcnow() - timedelta(minutes=ONLINE_THRESHOLD_MINUTES)

    items = []
    for d in devices:
        online = bool(d.last_seen_at and d.last_seen_at >= cutoff and d.is_active)
        items.append({"device": d, "online": online})

    return render_template(
        "admin/platform/device_list.html",
        items=items,
        institutions=institutions,
        threshold_min=ONLINE_THRESHOLD_MINUTES,
    )


@devices_bp.route("/admin/platform/devices/new", methods=["POST"])
@super_admin_required
def device_new():
    """Provisiona um novo totem. Exibe o segredo UMA UNICA VEZ."""
    validate_csrf_token()

    iid = request.form.get("institution_id", type=int)
    name = (request.form.get("name", "") or "").strip()
    location = (request.form.get("location", "") or "").strip()

    if not iid or not name:
        flash("Informe instituição e nome do totem.", "error")
        return redirect(url_for("devices.device_list"))

    inst = Institution.query.get_or_404(iid)
    api_key_id = generate_api_key_id()
    secret_plain = generate_api_key_secret()

    device = TotemDevice(
        institution_id=inst.id,
        name=name[:120],
        location=location[:200] or None,
        api_key_id=api_key_id,
        status="active",
    )
    device.set_secret(secret_plain)
    db.session.add(device)
    db.session.flush()
    audit_log(
        ACTION_DEVICE_CREATE,
        resource_type="device", resource_id=device.id,
        details={"api_key_id": api_key_id, "institution_id": inst.id, "name": device.name},
    )
    db.session.commit()

    return render_template(
        "admin/platform/device_credentials.html",
        device=device,
        api_key_id=api_key_id,
        api_key_secret=secret_plain,
    )


@devices_bp.route("/admin/platform/devices/<int:did>/revoke", methods=["POST"])
@super_admin_required
def device_revoke(did):
    validate_csrf_token()
    device = TotemDevice.query.get_or_404(did)
    device.status = "revoked"
    audit_log(
        ACTION_DEVICE_REVOKE,
        resource_type="device", resource_id=device.id,
        details={"api_key_id": device.api_key_id},
    )
    db.session.commit()
    flash(f"Chave do totem '{device.name}' revogada.", "warning")
    return redirect(url_for("devices.device_list"))


@devices_bp.route("/admin/platform/audit")
@super_admin_required
def audit_list():
    page = max(1, request.args.get("page", default=1, type=int))
    per_page = 50
    q = AdminAuditLog.query.order_by(AdminAuditLog.created_at.desc())
    total = q.count()
    entries = q.offset((page - 1) * per_page).limit(per_page).all()
    return render_template(
        "admin/platform/audit_list.html",
        entries=entries,
        page=page,
        per_page=per_page,
        total=total,
    )
