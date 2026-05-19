#!/bin/bash
# =============================================================================
# Totem FlexMedia — Rotacao de segredos
# =============================================================================
# Regenera segredos do .env apos vazamento (chat publico, screenshot, commit
# acidental, etc.). Faz backup do .env atual antes de qualquer escrita.
#
# Cobre:
#   - SECRET_KEY              (Flask: invalida sessoes ativas)
#   - TOTEM_WAKE_SECRET       (loopback /api/local/wake: derruba daemon ate sync)
#   - FIELD_ENCRYPTION_KEY    (criptografia em repouso: ATENCAO — ver abaixo)
#
# NAO cobre (precisa acao manual fora do Pi):
#   - OPENAI_API_KEY    -> revogar em https://platform.openai.com/api-keys
#   - SUPERADMIN_PASSWORD -> trocar em /admin/change_password
#   - Credenciais HMAC de totens -> regerar em /admin/platform/devices
#
# Uso:
#   bash deploy/rotate_secrets.sh                 # interativo (escolhe quais)
#   ROTATE=secret_key,wake bash deploy/rotate_secrets.sh   # nao-interativo
#
# Opcoes pra ROTATE: secret_key, wake, field_key, all
#
# ============================================================================
# IMPORTANTE: FIELD_ENCRYPTION_KEY tem migracao especial
# ============================================================================
# Trocar essa chave SEM migrar dados invalida totp_secret e api_key_secret
# criptografados de todos os totens e usuarios. O script suporta rotacao com
# dual-key (FIELD_ENCRYPTION_KEYS=nova,antiga) — o app le pelas duas e escreve
# com a nova. Apos algumas semanas, voce remove a antiga.
# =============================================================================

set -euo pipefail

VERDE='\033[0;32m'
AMARELO='\033[1;33m'
VERMELHO='\033[0;31m'
AZUL='\033[0;34m'
RESET='\033[0m'

passo() { echo -e "\n${AZUL}==>${RESET} ${1}"; }
ok()    { echo -e "${VERDE}[OK]${RESET} ${1}"; }
aviso() { echo -e "${AMARELO}[AVISO]${RESET} ${1}"; }
erro()  { echo -e "${VERMELHO}[ERRO]${RESET} ${1}" >&2; }

if [ "$EUID" -eq 0 ]; then
  erro "Nao rode como root. Use o usuario dono do .env."
  exit 1
fi

# --- 0. Localizar .env -----------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="${ENV_FILE:-$PROJECT_DIR/.env}"

if [ ! -f "$ENV_FILE" ]; then
  erro ".env nao encontrado em: $ENV_FILE"
  erro "Use ENV_FILE=/caminho/.env bash deploy/rotate_secrets.sh"
  exit 1
fi
ok "Vou rotacionar segredos em: $ENV_FILE"

# --- 1. Escolha do que rotacionar ------------------------------------------
ROTATE="${ROTATE:-}"
if [ -z "$ROTATE" ]; then
  echo ""
  echo "O que rotacionar?"
  echo "  1) SECRET_KEY (invalida sessoes do admin)"
  echo "  2) TOTEM_WAKE_SECRET (precisa sincronizar em /etc/totem/credenciais.env)"
  echo "  3) FIELD_ENCRYPTION_KEY (rotacao com dual-key — ver doc)"
  echo "  4) Todas as 3"
  read -rp "Escolha [1,2,3,4]: " choice
  case "$choice" in
    1) ROTATE="secret_key" ;;
    2) ROTATE="wake" ;;
    3) ROTATE="field_key" ;;
    4) ROTATE="all" ;;
    *) erro "Opcao invalida"; exit 1 ;;
  esac
fi

# --- 2. Backup defensivo ---------------------------------------------------
TS="$(date +%Y%m%d-%H%M%S)"
BACKUP="${ENV_FILE}.bak-${TS}"
cp "$ENV_FILE" "$BACKUP"
chmod 600 "$BACKUP"
ok "Backup salvo em: $BACKUP"

# --- 3. Helpers ------------------------------------------------------------
gen_hex32()  { python3 -c "import secrets;print(secrets.token_hex(32))"; }
gen_fernet() { python3 -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"; }

# Atualiza KEY=VALUE no .env: substitui se existir, adiciona no fim se nao.
set_env_var() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}=" "$ENV_FILE"; then
    # Escapa & e | que sao especiais no sed
    local escaped
    escaped="$(printf '%s' "$value" | sed -e 's/[\/&|]/\\&/g')"
    sed -i "s|^${key}=.*|${key}=${escaped}|" "$ENV_FILE"
  else
    echo "${key}=${value}" >> "$ENV_FILE"
  fi
}

# --- 4. Rotacoes -----------------------------------------------------------
do_secret_key=0
do_wake=0
do_field=0
case "$ROTATE" in
  *all*)        do_secret_key=1; do_wake=1; do_field=1 ;;
  *secret_key*) do_secret_key=1 ;;
esac
[[ "$ROTATE" == *wake* ]] && do_wake=1
[[ "$ROTATE" == *field_key* ]] && do_field=1

if [ "$do_secret_key" -eq 1 ]; then
  passo "Rotacionando SECRET_KEY"
  NEW="$(gen_hex32)"
  set_env_var "SECRET_KEY" "$NEW"
  ok "SECRET_KEY trocada (sessoes ativas serao invalidadas no proximo restart)"
fi

if [ "$do_wake" -eq 1 ]; then
  passo "Rotacionando TOTEM_WAKE_SECRET"
  NEW="$(gen_hex32)"
  set_env_var "TOTEM_WAKE_SECRET" "$NEW"
  ok "TOTEM_WAKE_SECRET trocada no $ENV_FILE"
  echo ""
  aviso "ATENCAO: o daemon de sensores le /etc/totem/credenciais.env."
  aviso "Precisa atualizar a mesma chave la, ou o daemon nao consegue acordar o kiosk."
  echo ""
  echo "  Comando pronto (rode como root):"
  echo "    sudo sed -i 's|^TOTEM_WAKE_SECRET=.*|TOTEM_WAKE_SECRET=${NEW}|' /etc/totem/credenciais.env"
  echo "    sudo systemctl restart totem-sensors"
  echo ""
  if [ -f /etc/totem/credenciais.env ]; then
    read -rp "Quer que eu sincronize agora em /etc/totem/credenciais.env? [s/N] " ans
    if [[ "$ans" =~ ^[sS]$ ]]; then
      if grep -q "^TOTEM_WAKE_SECRET=" /etc/totem/credenciais.env; then
        sudo sed -i "s|^TOTEM_WAKE_SECRET=.*|TOTEM_WAKE_SECRET=${NEW}|" /etc/totem/credenciais.env
      else
        echo "TOTEM_WAKE_SECRET=${NEW}" | sudo tee -a /etc/totem/credenciais.env >/dev/null
      fi
      sudo systemctl restart totem-sensors 2>/dev/null || \
        aviso "totem-sensors nao esta instalado/ativo — pule o restart"
      ok "Sincronizado em /etc/totem/credenciais.env + daemon reiniciado"
    fi
  fi
fi

if [ "$do_field" -eq 1 ]; then
  passo "Rotacionando FIELD_ENCRYPTION_KEY (modo dual-key)"
  OLD_KEY="$(grep -E '^FIELD_ENCRYPTION_KEY(S)?=' "$ENV_FILE" | head -n1 | cut -d= -f2- || true)"
  if [ -z "$OLD_KEY" ]; then
    aviso "Nao havia FIELD_ENCRYPTION_KEY antes — gerando do zero."
    NEW="$(gen_fernet)"
    set_env_var "FIELD_ENCRYPTION_KEY" "$NEW"
    ok "FIELD_ENCRYPTION_KEY criada"
  else
    NEW="$(gen_fernet)"
    # Remove a linha antiga (FIELD_ENCRYPTION_KEY ou FIELD_ENCRYPTION_KEYS)
    sed -i '/^FIELD_ENCRYPTION_KEY=/d;/^FIELD_ENCRYPTION_KEYS=/d' "$ENV_FILE"
    # Escreve a forma dual-key: app le pelas duas, escreve com a primeira.
    echo "FIELD_ENCRYPTION_KEYS=${NEW},${OLD_KEY}" >> "$ENV_FILE"
    ok "FIELD_ENCRYPTION_KEYS=nova,antiga (dual-key ativo)"
    echo ""
    aviso "Apos algumas semanas (todos os dados re-escritos com a nova chave),"
    aviso "remova a antiga editando manualmente:"
    aviso "  FIELD_ENCRYPTION_KEY=${NEW}"
  fi
fi

# --- 5. Restart do servico -------------------------------------------------
passo "Reiniciando totem-flexmedia"
if systemctl list-unit-files | grep -q '^totem-flexmedia.service'; then
  sudo systemctl restart totem-flexmedia
  sleep 2
  if sudo systemctl is-active --quiet totem-flexmedia; then
    ok "totem-flexmedia ativo"
  else
    erro "totem-flexmedia NAO subiu apos restart. Veja logs:"
    erro "  sudo journalctl -u totem-flexmedia -n 50 --no-pager"
    erro ""
    erro "Pra reverter, copie de volta o backup:"
    erro "  cp $BACKUP $ENV_FILE && sudo systemctl restart totem-flexmedia"
    exit 1
  fi
else
  aviso "totem-flexmedia.service nao instalado neste host — pule o restart"
fi

# --- 6. Resumo + lembretes -------------------------------------------------
echo ""
echo -e "${VERDE}===========================================================${RESET}"
echo -e "${VERDE}  ROTACAO CONCLUIDA${RESET}"
echo -e "${VERDE}===========================================================${RESET}"
echo ""
echo "  Backup do .env anterior:  $BACKUP"
echo ""
echo "Acoes complementares (manuais, fora do Pi):"
echo "  [ ] Revogar OPENAI_API_KEY antiga:"
echo "         https://platform.openai.com/api-keys"
echo "  [ ] Trocar senha do super admin:"
echo "         https://<seu-totem>/admin/change_password"
echo "  [ ] Regenerar credenciais HMAC dos totens (se a chave do .env vazou):"
echo "         https://<seu-totem>/admin/platform/devices"
echo ""
echo "Pra rollback, basta:"
echo "  cp $BACKUP $ENV_FILE && sudo systemctl restart totem-flexmedia"
echo ""
