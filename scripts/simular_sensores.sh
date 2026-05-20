#!/usr/bin/env bash
# Simulador de sensores do Totem FlexMedia — espelho do simular_sensores.ps1
# para rodar no Pi (ou em qualquer Linux/macOS).
#
# Como usar:
#   1. cd ~/totem_flexmedia
#   2. source ./scripts/simular_sensores.sh
#   3. Chame: aproximar | afastar | fora_alcance | presenca_constante
#            ambiente <temp> <hum> | estado | reset | demo | dist <cm>
#
# Variaveis opcionais antes do source:
#   TOTEM_BASE_URL=http://127.0.0.1:8000   (default — porta do Gunicorn no Pi)
#   TOTEM_WAKE_SECRET=...                  (carregado do .env se nao definido)
#
# Tudo via POST /api/sensors/mock (HC-SR04) e /api/local/wake (DHT).
# Loopback-only + X-Wake-Secret — mesma autenticacao do daemon de sensores.

TOTEM_BASE_URL="${TOTEM_BASE_URL:-http://127.0.0.1:8000}"

_simular_carregar_secret() {
  if [ -n "${TOTEM_WAKE_SECRET:-}" ]; then return 0; fi
  local env_file
  for candidate in \
      "$(dirname "${BASH_SOURCE[0]}")/../.env" \
      "$PWD/.env" \
      "$HOME/totem_flexmedia/.env" \
      "/etc/totem/credenciais.env"; do
    if [ -f "$candidate" ]; then
      env_file="$candidate"
      break
    fi
  done
  if [ -n "${env_file:-}" ]; then
    TOTEM_WAKE_SECRET="$(grep -E '^TOTEM_WAKE_SECRET=' "$env_file" \
      | tail -n1 | cut -d= -f2- | tr -d '"'"'"' ')"
  fi
  export TOTEM_WAKE_SECRET
  if [ -z "${TOTEM_WAKE_SECRET:-}" ]; then
    echo "TOTEM_WAKE_SECRET nao encontrado. Defina manualmente:" >&2
    echo "  export TOTEM_WAKE_SECRET=algumacoisa" >&2
  fi
}
_simular_carregar_secret

_simular_curl() {
  # $1=path, $2=body. Retorna body da resposta (silencia headers).
  local path="$1"; local body="$2"
  curl -s -X POST "${TOTEM_BASE_URL}${path}" \
    -H "X-Wake-Secret: ${TOTEM_WAKE_SECRET}" \
    -H "Content-Type: application/json" \
    -d "$body"
}

# Parse mini-JSON do snapshot para exibicao didatica. Usa python3 — sempre
# disponivel no Pi e mais robusto que sed/awk pra null/numeros.
_simular_print_snap() {
  python3 - "$1" <<'PY' 2>/dev/null || echo "$1"
import json, sys
try:
    data = json.loads(sys.argv[1])
except Exception:
    print(sys.argv[1]); sys.exit(0)
s = data.get("session", data)
fmt = lambda v, suf="": "—" if v is None else f"{v}{suf}"
print(f"[{s.get('state','?').upper()}] distancia={fmt(s.get('distance_cm'),' cm')}  "
      f"temp={fmt(s.get('temp_c'),'°C')}  umid={fmt(s.get('humidity_pct'),'%')}")
PY
}

# ── HC-SR04 (distancia / proximidade) ────────────────────────────────────

dist() {
  # uso: dist 50    |   dist null
  local val="$1"
  local body
  if [ "$val" = "null" ] || [ -z "$val" ]; then
    body='{"distance_cm": null}'
  else
    body="{\"distance_cm\": ${val}}"
  fi
  _simular_print_snap "$(_simular_curl /api/sensors/mock "$body")"
}

aproximar() {
  echo "→ Visitante a 50 cm (dentro de ENGAGE_DISTANCE_CM=80)"
  dist 50
  echo "  Esperado: state=active, overlay some, audio toca."
}

afastar() {
  echo "→ Visitante a 250 cm (alem de LEAVE_DISTANCE_CM=150)"
  dist 250
  echo "  Esperado: state continua active por LEAVE_DELAY_S (30s); depois vai a idle."
}

fora_alcance() {
  echo "→ HC-SR04 sem reflexao (null)"
  dist null
  echo "  Mesmo efeito de afastamento: grace 30s e vai a idle."
}

presenca_constante() {
  # uso: presenca_constante [segundos=100] [cm=50]
  local segundos="${1:-100}"; local cm="${2:-50}"
  echo "→ Visitante PARADO a ${cm} cm por ${segundos} segundos"
  echo "  Antes do fix: caia em IDLE apos ACTIVE_TIMEOUT_S (60s)."
  echo "  Depois do fix: permanece ACTIVE o tempo todo."
  local iter=$(( (segundos + 4) / 5 ))
  for i in $(seq 1 "$iter"); do
    dist "$cm"
    sleep 5
  done
  echo "Fim. Estado final:"
  estado
}

# ── DHT11/DHT22 (temperatura + umidade) ──────────────────────────────────
# /api/local/wake com type=environment. NAO muda o state — so telemetria.

ambiente() {
  # uso: ambiente 25.5 60
  local t="${1:-}"; local h="${2:-}"
  if [ -z "$t" ] || [ -z "$h" ]; then
    echo "uso: ambiente <temp_c> <humidity_pct>"; return 1
  fi
  local body
  body="{\"type\": \"environment\", \"temp_c\": ${t}, \"humidity_pct\": ${h}, \"source\": \"dht22\"}"
  _simular_print_snap "$(_simular_curl /api/local/wake "$body")"
}

# ── Utilitarios ──────────────────────────────────────────────────────────

estado() {
  local resp
  resp="$(curl -s "${TOTEM_BASE_URL}/api/session/state" || true)"
  if [ -z "$resp" ]; then
    echo "Servidor nao respondeu — Flask/Gunicorn rodando em ${TOTEM_BASE_URL}?"
    return 1
  fi
  _simular_print_snap "$resp"
}

reset() {
  echo "→ Forcando IDLE (afastamento + grace de 31s)"
  dist 250
  echo "  Aguardando LEAVE_DELAY_S..."
  sleep 31
  estado
}

demo() {
  echo "═══ DEMO COMPLETA ═══"
  estado
  echo ""
  aproximar
  sleep 2
  estado
  echo ""
  presenca_constante 70 50
  echo ""
  afastar
  echo "  Aguardando grace period..."
  sleep 31
  estado
}

echo ""
echo "Simulador carregado (base=${TOTEM_BASE_URL}). Funcoes disponiveis:"
echo "  aproximar              — visitante chega (state: active, audio toca)"
echo "  afastar                — visitante sai (state: idle apos 30s)"
echo "  fora_alcance           — sensor sem reflexao (idle apos 30s)"
echo "  presenca_constante     — fica parado 100s; valida o fix do IDLE espurio"
echo "  ambiente <temp> <hum>  — DHT11/DHT22 mock (so telemetria)"
echo "  dist <cm|null>         — leitura crua"
echo "  estado                 — snapshot atual da maquina de estados"
echo "  reset                  — forca volta para idle sem restart"
echo "  demo                   — cenario completo de ponta a ponta"
echo ""
