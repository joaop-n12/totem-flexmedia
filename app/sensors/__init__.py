"""Pacote de sensores fisicos do totem (DHT11/DHT22 + HC-SR04).

Roda no Raspberry Pi do totem como daemon separado (`scripts/totem_sensor_daemon.py`),
NUNCA dentro do worker Gunicorn — Flask nao deve segurar GPIO.

Cada modulo (`dht22`, `hcsr04`) expoe duas implementacoes:
  - Real (adafruit_dht / RPi.GPIO) quando disponivel.
  - Mock (gera eventos sinteticos) quando o hardware nao esta presente.

A escolha e' automatica via `is_pi_hardware()` — assim o mesmo codigo roda
em desenvolvimento (laptop Windows/macOS) e em producao (Pi).
"""
from .base import SensorReading, is_pi_hardware
from .dht22 import Dht22Sensor
from .hcsr04 import DistanceReading, Hcsr04Sensor

__all__ = [
    "SensorReading",
    "is_pi_hardware",
    "Dht22Sensor",
    "DistanceReading",
    "Hcsr04Sensor",
]
