"""Sensor ultrassonico HC-SR04 — mede distancia do visitante ao totem.

Sprint 4: alimenta a maquina de estados de sessao (espera/convite/ativa)
com base na proximidade. Pinagem padrao no Pi 3 B:

  VCC  → 5V (pino 2)
  TRIG → GPIO 23 (pino 16)
  ECHO → GPIO 24 (pino 18) com divisor resistivo 1k/2k para 3.3V
  GND  → GND (pino 6)

Comportamento:
  - Le a cada `interval_seconds` (default 0.3s — UI precisa reagir rapido).
  - Filtro de mediana (3 amostras) corta picos espurios comuns no HC-SR04.
  - Modo mock le distancia de uma variavel injetada (thread-safe) — assim o
    endpoint admin de debug pode simular alguem se aproximando sem hardware.
  - Distancia em centimetros. Acima de `max_range_cm` (default 400) reporta
    None (fora do alcance / sem reflexao).
"""
from __future__ import annotations

import logging
import statistics
import threading
import time
from datetime import datetime
from typing import Callable, Optional

from .base import is_pi_hardware

logger = logging.getLogger(__name__)

# Reading distance e' separado do SensorReading do base.py para nao misturar
# campos de PIR/DHT — o daemon agrega tudo no estado consolidado.
DistanceCallback = Callable[["DistanceReading"], None]


class DistanceReading:
    """Snapshot leve para distancia. Usar dataclass aqui daria import circular
    com o `Literal["pir","dht22"]` do base — preferimos classe simples."""

    __slots__ = ("timestamp", "distance_cm", "error")

    def __init__(
        self,
        timestamp: datetime,
        distance_cm: float | None,
        error: str | None = None,
    ) -> None:
        self.timestamp = timestamp
        self.distance_cm = distance_cm
        self.error = error


class Hcsr04Sensor:
    """Driver do HC-SR04 com mock automatico fora do Pi.

    Args:
      trig_pin: GPIO BCM do TRIG.
      echo_pin: GPIO BCM do ECHO.
      interval_seconds: periodo entre leituras.
      max_range_cm: leituras acima disso viram None.
      mock_initial_cm: valor de partida no modo mock.
    """

    SPEED_OF_SOUND_CM_S = 34300.0  # 343 m/s a ~20°C

    def __init__(
        self,
        trig_pin: int = 23,
        echo_pin: int = 24,
        interval_seconds: float = 0.3,
        max_range_cm: float = 400.0,
        mock_initial_cm: float = 250.0,
    ) -> None:
        self.trig_pin = trig_pin
        self.echo_pin = echo_pin
        self.interval = interval_seconds
        self.max_range_cm = max_range_cm

        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[DistanceCallback] = None
        self._mock_mode = not is_pi_hardware()

        # Mock state — protegido por lock pois o endpoint /api/sensors/mock
        # escreve aqui de outra thread (worker Gunicorn ou test client).
        self._mock_lock = threading.Lock()
        self._mock_distance_cm: float | None = mock_initial_cm

    @property
    def mock_mode(self) -> bool:
        return self._mock_mode

    def set_mock_distance(self, distance_cm: float | None) -> None:
        """Injeta distancia simulada (so faz efeito em mock_mode)."""
        with self._mock_lock:
            self._mock_distance_cm = distance_cm

    def get_mock_distance(self) -> float | None:
        with self._mock_lock:
            return self._mock_distance_cm

    def start(self, callback: DistanceCallback) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._callback = callback
        self._stop.clear()
        target = self._run_mock if self._mock_mode else self._run_real
        self._thread = threading.Thread(
            target=target, name="hcsr04-sensor", daemon=True,
        )
        self._thread.start()
        logger.info(
            "HC-SR04 iniciado (modo=%s, trig=%s, echo=%s)",
            "mock" if self._mock_mode else "real",
            self.trig_pin,
            self.echo_pin,
        )

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    # ── emissao ───────────────────────────────────────────────────────────

    def _emit(self, distance_cm: float | None, error: str | None = None) -> None:
        if self._callback is None:
            return
        try:
            self._callback(DistanceReading(
                timestamp=datetime.utcnow(),
                distance_cm=distance_cm,
                error=error,
            ))
        except Exception:  # noqa: BLE001 — nao derrubar a thread
            logger.exception("HC-SR04 callback falhou")

    # ── implementacao real (Pi) ───────────────────────────────────────────

    def _measure_once(self, GPIO) -> float | None:  # noqa: N803 — GPIO modulo
        """Dispara um pulso de 10us e mede o tempo de echo. Retorna cm ou None."""
        # Pulso de trigger
        GPIO.output(self.trig_pin, GPIO.HIGH)
        time.sleep(0.00001)  # 10 microssegundos
        GPIO.output(self.trig_pin, GPIO.LOW)

        timeout = time.monotonic() + 0.04  # 40ms = ~6.8m, alem do alcance util

        # Espera echo subir
        while GPIO.input(self.echo_pin) == 0:
            if time.monotonic() > timeout:
                return None
        start = time.monotonic()

        # Espera echo descer
        while GPIO.input(self.echo_pin) == 1:
            if time.monotonic() > timeout:
                return None
        elapsed = time.monotonic() - start

        # distancia ida-e-volta = velocidade * tempo / 2
        dist = (elapsed * self.SPEED_OF_SOUND_CM_S) / 2.0
        if dist <= 0 or dist > self.max_range_cm:
            return None
        return dist

    def _run_real(self) -> None:
        try:
            import RPi.GPIO as GPIO  # type: ignore[import-not-found]
        except ImportError:
            logger.warning("RPi.GPIO nao instalado — HC-SR04 caindo para mock")
            self._mock_mode = True
            self._run_mock()
            return

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.trig_pin, GPIO.OUT, initial=GPIO.LOW)
        GPIO.setup(self.echo_pin, GPIO.IN)
        # Settle do sensor
        time.sleep(0.1)

        try:
            window: list[float] = []
            while not self._stop.is_set():
                try:
                    d = self._measure_once(GPIO)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("HC-SR04 leitura falhou: %s", exc)
                    d = None

                # Filtro de mediana — HC-SR04 da picos esporadicos
                if d is not None:
                    window.append(d)
                    if len(window) > 3:
                        window.pop(0)
                    self._emit(distance_cm=statistics.median(window))
                else:
                    window.clear()
                    self._emit(distance_cm=None)

                self._stop.wait(self.interval)
        finally:
            try:
                GPIO.cleanup([self.trig_pin, self.echo_pin])
            except Exception:  # noqa: BLE001
                pass

    # ── implementacao mock ────────────────────────────────────────────────

    def _run_mock(self) -> None:
        """Le distancia da variavel injetada — controlavel por endpoint admin."""
        while not self._stop.is_set():
            self._emit(distance_cm=self.get_mock_distance())
            if self._stop.wait(self.interval):
                return
