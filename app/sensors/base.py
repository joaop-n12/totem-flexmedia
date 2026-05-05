"""Tipos comuns e deteccao de hardware Pi.

`is_pi_hardware()` evita imports pesados (RPi.GPIO, board, adafruit_dht) em
ambientes sem hardware real — laptops de dev, CI e ate o servidor de
producao caso ele rode separado do kiosk. A heuristica olha pra
`/proc/device-tree/model`, presente em qualquer Raspberry Pi com kernel
mainline, e nao depende de variaveis externas.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass(frozen=True)
class SensorReading:
    """Snapshot imutavel de uma leitura de sensor.

    Campos opcionais (None) significam "sensor nao tem esse dado" — ex.: PIR
    so devolve `motion`, DHT22 so devolve `temp_c`/`humidity_pct`.
    """
    source: Literal["pir", "dht22"]
    timestamp: datetime
    motion: bool | None = None
    temp_c: float | None = None
    humidity_pct: float | None = None
    error: str | None = None


def is_pi_hardware() -> bool:
    """True se rodando num Raspberry Pi (qualquer modelo).

    Evita carregar RPi.GPIO em laptops — o pacote falha ao importar fora do
    Pi e quebraria o daemon todo. Em prod, override via env
    TOTEM_FORCE_MOCK_SENSORS=1 para forcar mock no proprio Pi (debug).
    """
    if os.environ.get("TOTEM_FORCE_MOCK_SENSORS") == "1":
        return False
    try:
        with open("/proc/device-tree/model", "r", encoding="utf-8") as f:
            return "raspberry pi" in f.read().lower()
    except (OSError, UnicodeDecodeError):
        return False
