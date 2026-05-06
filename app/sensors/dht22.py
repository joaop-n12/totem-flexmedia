"""Sensor DHT11 / DHT22 — temperatura e umidade ambiente.

Trello: Modulo 1 - Sensores/Hardware [Alta] 1.3.

Suporta os dois modelos via parametro `model` ou env `DHT_MODEL`.
Mesma biblioteca (`adafruit-circuitpython-dht`), mesma pinagem (DATA + pull-up
10k), mesmo callback. Diferencas que o codigo respeita:
  - DHT11: 0-50°C / 20-90% RH, precisao 1°C/1%, intervalo minimo 1 s.
  - DHT22: -40-80°C / 0-100% RH, precisao 0,1°C/0,1%, intervalo minimo 2 s.

Pinagem padrao:
  VCC → 3.3V (pino 1)      DATA → GPIO 4 (pino 7) com pull-up 10k     GND → GND

Comportamento:
  - Le sensor a cada `interval_seconds`. Se < intervalo minimo do modelo,
    o construtor sobe para o minimo automaticamente (proteje contra leituras
    rapidas demais que falham consistentemente).
  - Telemetria e' empurrada via callback. O daemon agrega no proximo
    heartbeat — nao manda HTTP por leitura.
  - Modo mock devolve valores razoaveis pra Sao Paulo, respeitando a faixa
    e a precisao do modelo selecionado.
"""
from __future__ import annotations

import logging
import os
import random
import threading
from datetime import datetime
from typing import Callable, Literal, Optional

from .base import SensorReading, is_pi_hardware

logger = logging.getLogger(__name__)

EnvCallback = Callable[[SensorReading], None]

DhtModel = Literal["DHT11", "DHT22"]

# Caracteristicas por modelo — usado pelo mock e pelo throttle minimo.
_MODEL_SPECS = {
    "DHT11": {
        "min_interval": 1.0,
        "temp_range": (0.0, 50.0),
        "hum_range":  (20.0, 90.0),
        "decimals":   0,   # DHT11 reporta inteiros
    },
    "DHT22": {
        "min_interval": 2.0,
        "temp_range": (-40.0, 80.0),
        "hum_range":  (0.0, 100.0),
        "decimals":   1,
    },
}


def _resolve_model(explicit: DhtModel | None) -> DhtModel:
    """Prioridade: argumento explicito > env DHT_MODEL > DHT22 (default)."""
    if explicit:
        return explicit
    env = (os.environ.get("DHT_MODEL") or "").strip().upper()
    if env in ("DHT11", "DHT22"):
        return env  # type: ignore[return-value]
    return "DHT22"


class Dht22Sensor:
    """Driver para DHT11 ou DHT22. Nome da classe mantido por compatibilidade
    historica — internamente respeita o parametro `model`."""

    def __init__(
        self,
        gpio_pin: int = 4,
        interval_seconds: float = 60.0,
        model: DhtModel | None = None,
    ) -> None:
        self.gpio_pin = gpio_pin
        self.model: DhtModel = _resolve_model(model)
        spec = _MODEL_SPECS[self.model]
        # Garante intervalo minimo seguro para o modelo (DHT11=1s, DHT22=2s).
        self.interval = max(interval_seconds, spec["min_interval"])
        self._spec = spec
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
        self._thread = threading.Thread(
            target=target, name=f"{self.model.lower()}-sensor", daemon=True,
        )
        self._thread.start()
        logger.info(
            "%s iniciado (modo=%s, gpio=%s, intervalo=%ss)",
            self.model,
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
            # source mantido como 'dht22' para nao quebrar o schema do
            # SensorReading (Literal). O modelo real fica em self.model.
            self._callback(SensorReading(
                source="dht22",
                timestamp=datetime.utcnow(),
                temp_c=temp_c,
                humidity_pct=humidity,
                error=error,
            ))
        except Exception:  # noqa: BLE001
            logger.exception("%s callback falhou", self.model)

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
            logger.error("board.%s indisponivel — abortando %s", pin_attr, self.model)
            return

        # use_pulseio=False evita dependencia de libgpiod no Pi 3.
        # Escolhe a classe correta da lib conforme o modelo configurado.
        sensor_cls = adafruit_dht.DHT11 if self.model == "DHT11" else adafruit_dht.DHT22
        sensor = sensor_cls(pin, use_pulseio=False)
        try:
            while not self._stop.is_set():
                try:
                    temp = sensor.temperature
                    hum = sensor.humidity
                    if temp is not None and hum is not None:
                        self._emit(temp_c=float(temp), humidity=float(hum))
                except RuntimeError as exc:
                    # DHT11/22 falham em ~10% das leituras por timing — normal.
                    self._emit(temp_c=None, humidity=None, error=str(exc))
                except Exception:  # noqa: BLE001
                    logger.exception("%s erro nao recuperavel", self.model)
                self._stop.wait(self.interval)
        finally:
            try:
                sensor.exit()
            except Exception:  # noqa: BLE001
                pass

    def _run_mock(self) -> None:
        """Devolve valores plausiveis dentro da faixa do modelo configurado.
        DHT11 reporta inteiros (decimals=0); DHT22 reporta com 1 casa.
        NAO esta calibrado — apenas exercita a UI."""
        decimals = self._spec["decimals"]
        t_min, t_max = self._spec["temp_range"]
        h_min, h_max = self._spec["hum_range"]
        while not self._stop.is_set():
            # Centro em ~26°C / 60% — clipa nos limites do modelo.
            temp = max(t_min, min(t_max, 26 + random.uniform(-2.0, 4.0)))
            hum  = max(h_min, min(h_max, 60 + random.uniform(-8.0, 15.0)))
            self._emit(
                temp_c=round(temp, decimals),
                humidity=round(hum, decimals),
            )
            if self._stop.wait(self.interval):
                return
