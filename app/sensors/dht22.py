"""Sensor DHT22 — temperatura e umidade ambiente.

Trello: Modulo 1 - Sensores/Hardware [Alta] 1.3.

Pinagem padrao:
  VCC → 3.3V (pino 1)      DATA → GPIO 4 (pino 7) com pull-up 10k     GND → GND

Comportamento:
  - Le sensor a cada `interval_seconds` (default 60s — DHT22 e' lento e
    leituras < 2s queimam o sensor).
  - Telemetria e' empurrada via callback. O daemon agrega no proximo
    heartbeat — nao manda HTTP por leitura.
  - Modo mock devolve valores razoaveis pra Sao Paulo: 24-28°C / 55-70%.
"""
from __future__ import annotations

import logging
import random
import threading
from datetime import datetime
from typing import Callable, Optional

from .base import SensorReading, is_pi_hardware

logger = logging.getLogger(__name__)

EnvCallback = Callable[[SensorReading], None]


class Dht22Sensor:
    def __init__(
        self,
        gpio_pin: int = 4,
        interval_seconds: float = 60.0,
    ) -> None:
        self.gpio_pin = gpio_pin
        self.interval = interval_seconds
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._callback: Optional[EnvCallback] = None
        self._mock_mode = not is_pi_hardware()

    @property
    def mock_mode(self) -> bool:
        return self._mock_mode

    def start(self, callback: EnvCallback) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._callback = callback
        self._stop.clear()
        target = self._run_mock if self._mock_mode else self._run_real
        self._thread = threading.Thread(target=target, name="dht22-sensor", daemon=True)
        self._thread.start()
        logger.info(
            "DHT22 iniciado (modo=%s, gpio=%s, intervalo=%ss)",
            "mock" if self._mock_mode else "real",
            self.gpio_pin,
            self.interval,
        )

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

    # ── implementacoes ─────────────────────────────────────────────────────

    def _emit(self, temp_c: float | None, humidity: float | None, error: str | None = None) -> None:
        if self._callback is None:
            return
        try:
            self._callback(SensorReading(
                source="dht22",
                timestamp=datetime.utcnow(),
                temp_c=temp_c,
                humidity_pct=humidity,
                error=error,
            ))
        except Exception:  # noqa: BLE001
            logger.exception("DHT22 callback falhou")

    def _run_real(self) -> None:
        # adafruit_dht sobre lgpio e' a stack atual recomendada (RPi.GPIO
        # legacy nao funciona em Pi 5). Em Pi 3, o driver tambem funciona.
        try:
            import board  # type: ignore[import-not-found]
            import adafruit_dht  # type: ignore[import-not-found]
        except ImportError:
            logger.warning("adafruit-circuitpython-dht nao instalado — caindo para mock")
            self._mock_mode = True
            self._run_mock()
            return

        pin_attr = f"D{self.gpio_pin}"
        try:
            pin = getattr(board, pin_attr)
        except AttributeError:
            logger.error("board.%s indisponivel — abortando DHT22", pin_attr)
            return

        # use_pulseio=False evita dependencia de libgpiod no Pi 3.
        sensor = adafruit_dht.DHT22(pin, use_pulseio=False)
        try:
            while not self._stop.is_set():
                try:
                    temp = sensor.temperature
                    hum = sensor.humidity
                    if temp is not None and hum is not None:
                        self._emit(temp_c=float(temp), humidity=float(hum))
                except RuntimeError as exc:
                    # DHT22 falha em ~10% das leituras por timing — normal.
                    self._emit(temp_c=None, humidity=None, error=str(exc))
                except Exception:  # noqa: BLE001
                    logger.exception("DHT22 erro nao recuperavel")
                self._stop.wait(self.interval)
        finally:
            try:
                sensor.exit()
            except Exception:  # noqa: BLE001
                pass

    def _run_mock(self) -> None:
        """Devolve valores plausiveis. NAO esta calibrado — apenas exercita a UI."""
        while not self._stop.is_set():
            temp = round(24 + random.uniform(-1.5, 4.0), 1)
            hum = round(55 + random.uniform(-5, 15), 1)
            self._emit(temp_c=temp, humidity=hum)
            if self._stop.wait(self.interval):
                return
