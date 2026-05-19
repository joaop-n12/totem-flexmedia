"""Maquina de estados da sessao de atendimento do totem.

Consolidada num servico singleton porque o estado e' processo-local: o
mesmo Gunicorn worker que recebe `/api/local/wake` (do daemon de sensores)
tambem responde `/api/session/state` para o kiosk.

Estados (contrato consumido pelo overlay em templates/base.html):
    idle    — visitante longe (ou sem leitura), overlay "Aproxime-se" visivel
    active  — HC-SR04 detectou usuario proximo: overlay some, totem dispara
              saudacao TTS e (se na home) navega para /voice

Transicoes (simplificadas, fail-open):
    idle    --dist <= ENGAGE-->  active
    active  --dist >= LEAVE-->   idle
    active  --dist = None  -->   idle
    active  --timeout-->         idle

Thread-safety: lock unico no singleton. Volume de chamadas e' baixo
(daemon manda heartbeat 1x/s + kiosk polla 1x/s) — lock simples basta.
"""
from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Optional


# ── Parametros ajustaveis ──────────────────────────────────────────────────
ENGAGE_DISTANCE_CM = 80.0   # entra em ACTIVE quando usuario se aproxima
LEAVE_DISTANCE_CM = 150.0   # sai de ACTIVE quando se afasta
ACTIVE_TIMEOUT_S = 60.0     # ACTIVE sem refresh de distancia -> IDLE (rede de seguranca)
LEAVE_DELAY_S = 30.0        # apos perder presenca, aguarda esse delay antes de voltar a IDLE


# ── Tipos publicos ─────────────────────────────────────────────────────────
@dataclass
class SessionSnapshot:
    """Snapshot serializavel do estado atual. Consumido por kiosk e admin."""
    state: str = "idle"
    distance_cm: Optional[float] = None
    temp_c: Optional[float] = None
    humidity_pct: Optional[float] = None
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
        # Marca o instante em que a presenca foi perdida. None = usuario
        # presente (ou ja em IDLE). Quando vira um timestamp, comeca a
        # contar LEAVE_DELAY_S antes de derrubar pra IDLE.
        self._leaving_since: Optional[float] = None

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
        if self._snap.state != "active":
            return

        now = self._now()

        # Caminho 1: cronometro de saida (LEAVE_DELAY_S) estourou
        # depois que a presenca foi perdida.
        if self._leaving_since is not None:
            if now - self._leaving_since >= LEAVE_DELAY_S:
                self._transition("idle")
                self._leaving_since = None
                return

        # Caminho 2: rede de seguranca — tempo total em ACTIVE sem
        # nenhuma renovacao de state_since. Protege contra sensor mudo.
        if now - self._snap.state_since > ACTIVE_TIMEOUT_S:
            self._transition("idle")
            self._leaving_since = None

    # — API publica usada por devices.py —
    def update_distance(self, distance_cm: Optional[float]) -> SessionSnapshot:
        """HC-SR04 reportou nova leitura. None = fora de alcance."""
        with self._lock:
            self._snap.distance_cm = distance_cm
            self._snap.last_distance_at = self._now()
            now = self._now()

            if distance_cm is not None and distance_cm <= ENGAGE_DISTANCE_CM:
                # Usuario presente: cancela qualquer cronometro de saida
                # em andamento e garante que estamos em ACTIVE.
                self._leaving_since = None
                if self._snap.state == "idle":
                    self._transition("active")
                else:
                    # Renova o relogio do ACTIVE_TIMEOUT_S enquanto
                    # houver presenca confirmada.
                    self._snap.state_since = now
            else:
                # Sem presenca confirmada (None ou >= LEAVE_DISTANCE_CM).
                # Se estavamos em ACTIVE e o cronometro ainda nao comecou,
                # inicia agora. Nao derruba pra IDLE imediatamente — deixa
                # o _evaluate_timeout decidir quando estourar LEAVE_DELAY_S.
                if self._snap.state == "active" and self._leaving_since is None:
                    self._leaving_since = now

            self._evaluate_timeout()
            return self._snap

    def update_environment(
        self,
        temp_c: Optional[float] = None,
        humidity_pct: Optional[float] = None,
    ) -> None:
        """DHT11/DHT22 reportou ambiente. Nao muda estado — apenas telemetria."""
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
