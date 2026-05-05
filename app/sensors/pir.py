"""Sensor PIR (Passive Infrared) — detecta presenca de visitantes.

Trello: Modulo 1 - Sensores/Hardware [Alta] 1.1, 1.2, 1.4, 1.5, 1.6.

Pinagem padrao no Pi 3 B:
  VCC → 5V (pino 2)        DATA → GPIO 17 (pino 11)        GND → GND (pino 6)

Fluxo:
  1. Daemon registra callback `on_motion()` em `PirSensor.start()`.
  2. Quando o GPIO sobe, callback dispara um POST local (`/api/local/wake`)
     que faz o Flask servir um SSE event para o browser do kiosk reagir.
  3. PIR sensores baratos (HC-SR501) tem auto-retrigger e cooldown propios —
     nao precisamos debounce no software, mas adicionamos throttle para nao
     spamar o servidor (`min_interval_seconds`).
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Callable, Optional

from .base import SensorReading, is_pi_hardware

logger = logging.getLogger(__name__)

MotionCallback = Callable[[SensorReading], None]


class PirSensor:
    """Watcher de PIR via GPIO. Mock automatico fora do Pi.

    Args:
      gpio_pin: numero do GPIO (BCM). Default 17.
      min_interval_seconds: throttle — eventos mais proximos sao engolidos.
      mock_period_seconds: em modo mock, gera evento a cada N segundos.
    """

    def __init__(
        self,
        gpio_pin: int = 17,
        min_interval_seconds: float = 5.0,
        mock_period_seconds: float = 30.0,
    ) -> None:
        self.gpio_pin = gpio_pin
        self.min_interval = min_interval_seconds
        self.mock_period = mock_period_seconds
        self._last_event_ts = 0.0
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[MotionCallback] = None
        self._mock_mode = not is_pi_hardware()

    @property
    def mock_mode(self) -> bool:
        return self._mock_mode

    def start(self, callback: MotionCallback) -> None:
        """Comeca a observar o sensor numa thread daemon."""
        if self._thread and self._thread.is_alive():
            return
        self._callback = callback
        self._stop.clear()
        target = self._run_mock if self._mock_mode else self._run_real
        self._thread = threading.Thread(target=target, name="pir-sensor", daemon=True)
        self._thread.start()
        logger.info(
            "PIR iniciado (modo=%s, gpio=%s)",
            "mock" if self._mock_mode else "real",
            self.gpio_pin,
        )

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    # ── implementacoes ─────────────────────────────────────────────────────

    def _emit(self, motion: bool) -> None:
        now = time.monotonic()
        if motion and (now - self._last_event_ts) < self.min_interval:
            return  # throttle — PIR rebotando
        self._last_event_ts = now if motion else self._last_event_ts
        if self._callback is None:
            return
        try:
            self._callback(SensorReading(
                source="pir",
                timestamp=datetime.utcnow(),
                motion=motion,
            ))
        except Exception:  # noqa: BLE001 — nao podemos derrubar a thread
            logger.exception("PIR callback falhou")

    def _run_real(self) -> None:
        try:
            import RPi.GPIO as GPIO  # type: ignore[import-not-found]
        except ImportError:
            logger.warning("RPi.GPIO nao instalado — caindo para mock")
            self._mock_mode = True
            self._run_mock()
            return

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.gpio_pin, GPIO.IN)
        try:
            while not self._stop.is_set():
                # Polling de 200ms — sensor PIR tem rise time de ~1s, nao
                # vale interrupcao. Polling e' suficiente e portavel.
                if GPIO.input(self.gpio_pin):
                    self._emit(motion=True)
                self._stop.wait(0.2)
        finally:
            GPIO.cleanup(self.gpio_pin)

    def _run_mock(self) -> None:
        """Em laptop/CI: emite presenca a cada `mock_period` segundos.

        Util para desenvolver a logica de wake-up sem hardware. Em testes
        unitarios, prefira chamar `_emit(True)` diretamente.
        """
        while not self._stop.is_set():
            if self._stop.wait(self.mock_period):
                return
            self._emit(motion=True)
