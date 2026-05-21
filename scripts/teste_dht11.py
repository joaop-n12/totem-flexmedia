"""Leitura simples de DHT11 no Raspberry Pi.

Uso (no Pi):
    sudo pip3 install adafruit-circuitpython-dht
    sudo python3 scripts/teste_dht11.py

Pinagem padrao (BCM):
    VCC  -> 3.3V (pino 1)
    DATA -> GPIO4 (pino 7)   <- ajustavel via env DHT_PIN
    GND  -> GND  (pino 6)

Obs: DHT11 e' lento — uma leitura a cada ~2 segundos.
"""

import os
import time

import board
import adafruit_dht


# Mapeia "4" -> board.D4, "17" -> board.D17, etc.
NUMERO_PINO = int(os.getenv("DHT_PIN", "4"))
pino = getattr(board, f"D{NUMERO_PINO}")

# use_pulseio=False evita conflito com audio/PWM no Pi 3
sensor = adafruit_dht.DHT11(pino, use_pulseio=False)

print(f"Lendo DHT11 no GPIO{NUMERO_PINO}. Ctrl+C para sair.\n")

while True:
    try:
        temperatura = sensor.temperature  # graus Celsius
        umidade = sensor.humidity         # percentual
        if temperatura is not None and umidade is not None:
            print(f"Temp: {temperatura:.1f}C  |  Umidade: {umidade:.1f}%")
        else:
            print("Leitura vazia, tentando de novo...")
    except RuntimeError as erro:
        # DHT11 falha bastante — e' normal, basta repetir
        print(f"Falha transitoria: {erro}")
    except KeyboardInterrupt:
        sensor.exit()
        print("\nEncerrado.")
        break

    time.sleep(2)
