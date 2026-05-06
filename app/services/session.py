"""Maquina de estados da sessao de atendimento do totem (Sprint 4).

Consolidada num servico singleton porque o estado e' processo-local: o
mesmo Gunicorn worker que recebe `/api/local/wake` (do daemon de sensores)
tambem responde `/api/session/state` para o kiosk.

Estados:
    IDLE     — sem presenca detectada, totem em modo de descanso
    INVITE   — PIR detectou movimento; convite visual ativo
    ENGAGED  — HC-SR04 confirmou usuario proximo (< INVITE_DISTANCE_CM)
    FAREWELL — usuario afastou-se; transicao curta antes de voltar a IDLE

Transicoes (simplificadas, fail-open):
    IDLE     --motion-->        INVITE
    INVITE   --dist < ENGAGE--> ENGAGED
    INVITE   --timeout-->       IDLE
    ENGAGED  --dist > LEAVE-->  FAREWELL
    ENGAGED  --timeout-->       FAREWELL
    FAREWELL --timeout-->       IDLE

Thread-safety: lock unico no singleton. Volume de chamadas e' baixo
(daemon manda heartbeat 1x/s + kiosk polla 1x/s) — lock simples basta.
"""
from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional


# ── Parametros ajustaveis ──────────────────────────────────────────────────
ENGAGE_DISTANCE_CM = 80.0   # entra em ENGAGED quando usuario se aproxima
LEAVE_DISTANCE_CM = 150.0   # sai de ENGAGED quando se afasta
INVITE_TIMEOUT_S = 8.0      # INVITE sem aproximacao -> IDLE
ENGAGED_TIMEOUT_S = 60.0    # ENGAGED sem refresh de distancia -> FAREWELL
FAREWELL_TIMEOUT_S = 4.0    # FAREWELL -> IDLE


# ── Tipos publicos ─────────────────────────────────────────────────────────
@dataclass
class SessionSnapshot:
    """Snapshot serializavel do estado atual. Consumido por kiosk e admin."""
    state: str = "idle"
    distance_cm: Optional[float] = None
    temp_c: Optional[float] = None
    humidity_pct: Optional[float] = None
    last_motion_at: Optional[float] = None
    last_distance_at: Optional[float] = None
    state_since: float = field(default_factory=lambda: datetime.utcnow().timestamp())

    def to_dict(self) -> dict:
        return asdict(self)


# ── Maquina de estados ─────────────────────────────────────────────────────
class SessionStateMachine:
    """Estado processo-local. Use get_state_machine() para obter singleton."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._snap = SessionSnapshot()

    # — helpers internos —
    def _now(self) -> float:
        return datetime.utcnow().timestamp()

    def _transition(self, new_state: str) -> None:
        if self._snap.state != new_state:
            self._snap.state = new_state
            self._snap.state_since = self._now()

    def _evaluate_timeout(self) -> None:
        """Reavalia o estado em funcao do tempo decorrido. Sem efeitos colaterais
        alem da propria transicao."""
        elapsed = self._now() - self._snap.state_since
        s = self._snap.state
        if s == "invite" and elapsed > INVITE_TIMEOUT_S:
            self._transition("idle")
        elif s == "engaged" and elapsed > ENGAGED_TIMEOUT_S:
            self._transition("farewell")
        elif s == "farewell" and elapsed > FAREWELL_TIMEOUT_S:
            self._transition("idle")

    # — API publica usada por devices.py —
    def update_motion(self) -> SessionSnapshot:
        """PIR detectou presenca. Promove IDLE -> INVITE (fail-open)."""
        with self._lock:
            self._snap.last_motion_at = self._now()
            if self._snap.state == "idle":
                self._transition("invite")
            return self._snap

    def update_distance(self, distance_cm: Optional[float]) -> SessionSnapshot:
        """HC-SR04 reportou nova leitura. None = fora de alcance."""
        with self._lock:
            self._snap.distance_cm = distance_cm
            self._snap.last_distance_at = self._now()

            if distance_cm is None:
                # fora de alcance — se estava ENGAGED, comeca a despedida.
                if self._snap.state == "engaged":
                    self._transition("farewell")
            elif distance_cm <= ENGAGE_DISTANCE_CM:
                # usuario proximo — entra em ENGAGED a partir de qualquer estado
                # exceto FAREWELL (ja em transicao para IDLE).
                if self._snap.state in ("idle", "invite"):
                    self._transition("engaged")
            elif distance_cm >= LEAVE_DISTANCE_CM:
                if self._snap.state == "engaged":
                    self._transition("farewell")

            self._evaluate_timeout()
            return self._snap

    def update_environment(
        self,
        temp_c: Optional[float] = None,
        humidity_pct: Optional[float] = None,
    ) -> None:
        """DHT22 reportou ambiente. Nao muda estado — apenas telemetria."""
        with self._lock:
            if temp_c is not None:
                try:
                    self._snap.temp_c = float(temp_c)
                except (TypeError, ValueError):
                    pass
            if humidity_pct is not None:
                try:
                    self._snap.humidity_pct = float(humidity_pct)
                except (TypeError, ValueError):
                    pass

    def snapshot(self) -> SessionSnapshot:
        """Le o estado sem reavaliar timeout."""
        with self._lock:
            return self._snap

    def tick(self) -> SessionSnapshot:
        """Reavalia timeout e devolve snapshot. Usado pelo polling do kiosk."""
        with self._lock:
            self._evaluate_timeout()
            return self._snap


# ── Singleton ──────────────────────────────────────────────────────────────
_instance: Optional[SessionStateMachine] = None
_instance_lock = threading.Lock()


def get_state_machine() -> SessionStateMachine:
    """Retorna o singleton da maquina de estados (lazy + thread-safe)."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = SessionStateMachine()
    return _instance
