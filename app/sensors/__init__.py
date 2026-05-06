"""Pacote de sensores fisicos do totem (PIR + DHT22).

Roda no Raspberry Pi do totem como daemon separado (`scripts/totem_sensor_daemon.py`),
NUNCA dentro do worker Gunicorn — Flask nao deve segurar GPIO.

Cada modulo (`pir`, `dht22`) expoe duas implementacoes:
  - Real (RPi.GPIO / adafruit_dht) quando disponivel.
  - Mock (gera eventos sinteticos) quando o hardware nao esta presente.

A escolha e' automatica via `is_pi_hardware()` — assim o mesmo codigo roda
em desenvolvimento (laptop Windows/macOS) e em producao (Pi).
"""
from .base import SensorReading, is_pi_hardware
from .pir import PirSensor
from .dht22 import Dht22Sensor
from .hcsr04 import DistanceReading, Hcsr04Sensor

__all__ = [
    "SensorReading",
    "is_pi_hardware",
    "PirSensor",
    "Dht22Sensor",
    "DistanceReading",
    "Hcsr04Sensor",
]
