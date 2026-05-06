"""Daemon de sensores que roda no Raspberry Pi (NAO no servidor remoto).

Funcoes:
  1. Le PIR e DHT22 via threads.
  2. Em PIR alta: POST local em http://127.0.0.1:8000/api/local/wake (shared
     secret no .env do totem) — Flask faz fan-out via SSE para o kiosk
     acordar/iniciar interacao.
  3. Agrega temp/humid e envia ao servidor central junto com o heartbeat
     HMAC. Reusa o segredo (api_key_secret) que ja existe no totem.

Por que separar do Flask?
  - GPIO precisa de privilegio + thread fixa, ruim em workers Gunicorn.
  - Se o backend Flask cair/reinicia, sensores continuam funcionando.
  - Daemon e' systemd service independente; resiliencia maior.

Em laptop/CI, o daemon roda em mock e ainda exercita o caminho HTTP — util
para desenvolver a UI de wake-up sem Pi fisico.
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime

import urllib.error
import urllib.request

from .base import SensorReading
from .dht22 import Dht22Sensor
from .hcsr04 import DistanceReading, Hcsr04Sensor
from .pir import PirSensor

logger = logging.getLogger("totem.sensor_daemon")


class SensorDaemon:
    def __init__(
        self,
        wake_url: str,
        wake_secret: str,
        heartbeat_url: str,
        api_key_id: str,
        api_key_secret: str,
        pir_pin: int = 17,
        dht_pin: int = 4,
        hcsr04_trig_pin: int = 23,
        hcsr04_echo_pin: int = 24,
        heartbeat_interval: float = 60.0,
        distance_post_interval: float = 1.0,
        distance_change_threshold_cm: float = 5.0,
    ) -> None:
        self.wake_url = wake_url
        self.wake_secret = wake_secret
        self.heartbeat_url = heartbeat_url
        self.api_key_id = api_key_id
        self.api_key_secret = api_key_secret
        self.heartbeat_interval = heartbeat_interval

        self.pir = PirSensor(gpio_pin=pir_pin)
        # Modelo do DHT vem do env DHT_MODEL (resolvido dentro do driver).
        # Em Sprint 4 academico, definir DHT_MODEL=DHT11 no .env do Pi.
        self.dht = Dht22Sensor(gpio_pin=dht_pin)
        self.hcsr04 = Hcsr04Sensor(
            trig_pin=hcsr04_trig_pin,
            echo_pin=hcsr04_echo_pin,
        )

        # Estado compartilhado entre threads — protegido por lock simples.
        self._lock = threading.Lock()
        self._last_motion: datetime | None = None
        self._last_temp: float | None = None
        self._last_hum: float | None = None
        self._last_distance: float | None = None
        # Throttle do POST de distancia: evita 3-4 req/s para o Flask local.
        # Manda quando muda significativamente OU quando passou tempo demais.
        self._last_distance_post_ts = 0.0
        self._last_distance_posted: float | None = None
        self._distance_post_interval = distance_post_interval
        self._distance_change_threshold = distance_change_threshold_cm
        self._stop = threading.Event()

    # ── callbacks dos sensores ─────────────────────────────────────────────

    def _on_motion(self, reading: SensorReading) -> None:
        if not reading.motion:
            return
        with self._lock:
            self._last_motion = reading.timestamp
        self._post_wake({
            "type": "presence",
            "ts": int(time.time()),
            "source": "pir",
        })
        logger.info("Presenca detectada — wake local enviado")

    def _on_env(self, reading: SensorReading) -> None:
        if reading.error:
            logger.debug("DHT22 leitura com erro: %s", reading.error)
            return
        with self._lock:
            if reading.temp_c is not None:
                self._last_temp = reading.temp_c
            if reading.humidity_pct is not None:
                self._last_hum = reading.humidity_pct

    def _on_distance(self, reading: DistanceReading) -> None:
        """Recebe leitura do HC-SR04 e empurra para o Flask local quando vale.

        Regra de throttle (if-else complementar exigido pelo enunciado):
          - Se nunca postamos antes → posta.
          - Se distancia mudou mais que `_distance_change_threshold` → posta.
          - Se passou mais que `_distance_post_interval` segundos → posta.
          - Caso contrario, engole para nao saturar o servidor.
        """
        d = reading.distance_cm
        with self._lock:
            self._last_distance = d
            now = time.time()
            prev = self._last_distance_posted
            elapsed = now - self._last_distance_post_ts

            should_post = False
            if prev is None and d is not None:
                should_post = True
            elif d is None and prev is not None:
                # Saiu do alcance — vale notificar.
                should_post = True
            elif d is not None and prev is not None:
                if abs(d - prev) >= self._distance_change_threshold:
                    should_post = True
            if elapsed >= self._distance_post_interval and (d != prev):
                should_post = True

            if not should_post:
                return

            self._last_distance_posted = d
            self._last_distance_post_ts = now

        self._post_wake({"type": "distance", "distance_cm": d, "source": "hcsr04"})

    def _post_wake(self, body: dict) -> None:
        """POST autenticado em /api/local/wake. Falha silenciosa (Flask pode
        estar reiniciando); proxima leitura tenta de novo."""
        try:
            payload = json.dumps(body, default=str).encode("utf-8")
            req = urllib.request.Request(
                self.wake_url,
                data=payload,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "X-Wake-Secret": self.wake_secret,
                },
            )
            urllib.request.urlopen(req, timeout=2).read()
        except (urllib.error.URLError, TimeoutError) as exc:
            logger.debug("Wake (%s) falhou: %s", body.get("type"), exc)

    # ── heartbeat para o servidor ──────────────────────────────────────────

    def _heartbeat_payload(self) -> bytes:
        with self._lock:
            payload = {
                "app_version": os.environ.get("TOTEM_APP_VERSION", "sensor-daemon"),
                "ambient_temp_c": self._last_temp,
                "ambient_humidity_pct": self._last_hum,
                "last_motion_at": self._last_motion.isoformat() if self._last_motion else None,
            }
        return json.dumps(payload, default=str).encode("utf-8")

    def _send_heartbeat(self) -> None:
        body = self._heartbeat_payload()
        ts = str(int(time.time()))
        msg = f"{self.api_key_id}.{ts}.".encode("utf-8") + body
        sig = hmac.new(
            self.api_key_secret.encode("utf-8"),
            msg=msg,
            digestmod=hashlib.sha256,
        ).hexdigest()
        try:
            req = urllib.request.Request(
                self.heartbeat_url,
                data=body,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "X-Totem-Key": self.api_key_id,
                    "X-Totem-Timestamp": ts,
                    "X-Totem-Signature": sig,
                },
            )
            urllib.request.urlopen(req, timeout=5).read()
            logger.debug("Heartbeat enviado")
        except urllib.error.HTTPError as exc:
            logger.warning("Heartbeat HTTP %s: %s", exc.code, exc.reason)
        except (urllib.error.URLError, TimeoutError) as exc:
            logger.warning("Heartbeat falhou: %s", exc)

    def _heartbeat_loop(self) -> None:
        while not self._stop.is_set():
            self._send_heartbeat()
            if self._stop.wait(self.heartbeat_interval):
                return

    # ── ciclo de vida ──────────────────────────────────────────────────────

    def start(self) -> None:
        self.pir.start(self._on_motion)
        self.dht.start(self._on_env)
        self.hcsr04.start(self._on_distance)
        threading.Thread(
            target=self._heartbeat_loop, name="heartbeat", daemon=True,
        ).start()
        logger.info(
            "SensorDaemon online (pir mock=%s, dht mock=%s, hcsr04 mock=%s)",
            self.pir.mock_mode, self.dht.mock_mode, self.hcsr04.mock_mode,
        )

    def stop(self) -> None:
        self._stop.set()
        self.pir.stop()
        self.dht.stop()
        self.hcsr04.stop()


def _load_env_file(path: str) -> dict:
    """Le um .env simplificado (KEY=VALUE) — evita dep python-dotenv aqui."""
    env: dict[str, str] = {}
    if not os.path.exists(path):
        return env
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Daemon de sensores do Totem FlexMedia")
    parser.add_argument(
        "--env-file", default="/etc/totem/credenciais.env",
        help="Arquivo com TOTEM_API_KEY_ID, TOTEM_API_KEY_SECRET, TOTEM_WAKE_SECRET, "
             "TOTEM_HEARTBEAT_URL e TOTEM_WAKE_URL."
    )
    parser.add_argument("--pir-pin", type=int, default=17)
    parser.add_argument("--dht-pin", type=int, default=4)
    parser.add_argument("--hcsr04-trig-pin", type=int, default=23)
    parser.add_argument("--hcsr04-echo-pin", type=int, default=24)
    parser.add_argument("--heartbeat-interval", type=float, default=60.0)
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    env = {**_load_env_file(args.env_file), **os.environ}
    required = ["TOTEM_API_KEY_ID", "TOTEM_API_KEY_SECRET", "TOTEM_WAKE_SECRET"]
    missing = [k for k in required if not env.get(k)]
    if missing:
        logger.error("Variaveis obrigatorias ausentes: %s", ", ".join(missing))
        return 2

    daemon = SensorDaemon(
        wake_url=env.get("TOTEM_WAKE_URL", "http://127.0.0.1:8000/api/local/wake"),
        wake_secret=env["TOTEM_WAKE_SECRET"],
        heartbeat_url=env.get("TOTEM_HEARTBEAT_URL", "http://127.0.0.1:8000/api/heartbeat"),
        api_key_id=env["TOTEM_API_KEY_ID"],
        api_key_secret=env["TOTEM_API_KEY_SECRET"],
        pir_pin=args.pir_pin,
        dht_pin=args.dht_pin,
        hcsr04_trig_pin=args.hcsr04_trig_pin,
        hcsr04_echo_pin=args.hcsr04_echo_pin,
        heartbeat_interval=args.heartbeat_interval,
    )

    def _stop(signum, _frame):
        logger.info("Sinal %s — encerrando", signum)
        daemon.stop()

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    daemon.start()
    # Loop ocioso — threads daemon fazem o trabalho.
    while not daemon._stop.is_set():  # noqa: SLF001
        time.sleep(1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
