#!/usr/bin/env python3
"""Entry point standalone do daemon de sensores.

Roda como systemd service (`totem-sensors.service`). NAO importa Flask —
le sensores, posta wake-up local e envia heartbeat HMAC ao servidor.

Uso:
    python -m scripts.totem_sensor_daemon --env-file /etc/totem/credenciais.env
"""
import os
import sys

# Garante que o pacote `app` esteja no path quando executado direto.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from app.sensors.daemon import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
