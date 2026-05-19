#!/bin/bash
# =============================================================================
# Totem FlexMedia — Instalador de Cloudflare Tunnel
# =============================================================================
# Expoe o totem em HTTPS publico (https://<sub>.<dominio>) usando Cloudflare
# Tunnel — sem precisar de IP publico, port-forwarding, ou certificado SSL
# proprio. Resolve o bloqueio de microfone em HTTP que afeta todos os
# navegadores modernos (incluindo Fully Kiosk Browser gratuito).
#
# O que este script faz:
#   1. Detecta arquitetura do Pi (armhf / arm64) e baixa o binario certo
#   2. Garante que o cloudflared esta instalado
#   3. Autentica o Pi na conta Cloudflare (abre URL pra autorizar dominio)
#   4. Cria um tunel nomeado (idempotente: reaproveita se ja existir)
#   5. Aponta o subdominio escolhido pro tunel via DNS CNAME
#   6. Gera /etc/cloudflared/config.yml apontando pro Gunicorn local
#   7. Instala como servico systemd (sobe no boot, restart automatico)
#   8. Atualiza .env do projeto com TOTEM_PUBLIC_URL pra outras integracoes
#
# Uso:
#   bash deploy/install_cloudflared.sh                  # interativo
#   DOMINIO=flextotem.uk SUBDOMINIO=pi01 \             # nao-interativo
#     TUNNEL_NAME=totem-pi01 \
#     bash deploy/install_cloudflared.sh
#
# Pre-requisitos:
#   - Dominio ja comprado e ativo na Cloudflare (pode comprar em
#     https://dash.cloudflare.com → Domain Registration)
#   - Gunicorn rodando localmente (default: localhost:8000)
#   - Pi com acesso a internet pra falar com a Cloudflare
#
# Idempotencia: pode rodar de novo sem quebrar nada.
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

# --- 0. Pre-checks ---------------------------------------------------------
if [ "$EUID" -eq 0 ]; then
  erro "Nao rode como root/sudo. Use o usuario normal — o script chama sudo quando precisa."
  exit 1
fi

if ! sudo -v; then
  erro "Voce precisa ter privilegios de sudo para continuar."
  exit 1
fi

# Auto-detecta a pasta do projeto (mesmo padrao do install_totem.sh)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
if [ ! -f "$PROJECT_DIR/wsgi.py" ] || [ ! -d "$PROJECT_DIR/app" ]; then
  erro "Nao consegui localizar a raiz do projeto a partir de $SCRIPT_DIR"
  erro "Rode este script de dentro do repositorio do Totem FlexMedia."
  exit 1
fi
ok "Projeto em: $PROJECT_DIR"

# --- 1. Variaveis (env override > interativo) ------------------------------
DOMINIO="${DOMINIO:-}"
SUBDOMINIO="${SUBDOMINIO:-}"
TUNNEL_NAME="${TUNNEL_NAME:-}"
LOCAL_SERVICE="${LOCAL_SERVICE:-http://localhost:8000}"

if [ -z "$DOMINIO" ]; then
  echo ""
  echo "Dominio gerenciado pela Cloudflare (ex.: flextotem.uk):"
  read -rp "  DOMINIO: " DOMINIO
fi
if [ -z "$DOMINIO" ]; then
  erro "DOMINIO obrigatorio."
  exit 1
fi

if [ -z "$SUBDOMINIO" ]; then
  default_sub="pi$(hostname | tr -dc '0-9' | head -c 2)"
  [ -z "$default_sub" ] && default_sub="pi01"
  echo ""
  echo "Subdominio do totem (vai virar https://<sub>.${DOMINIO}):"
  read -rp "  SUBDOMINIO [$default_sub]: " SUBDOMINIO
  SUBDOMINIO="${SUBDOMINIO:-$default_sub}"
fi

HOSTNAME_FULL="${SUBDOMINIO}.${DOMINIO}"

if [ -z "$TUNNEL_NAME" ]; then
  default_name="totem-$(hostname | tr -dc 'a-z0-9-' | head -c 16)"
  [ -z "$default_name" ] && default_name="totem-pi01"
  echo ""
  echo "Nome do tunel na Cloudflare (qualquer identificador unico na sua conta):"
  read -rp "  TUNNEL_NAME [$default_name]: " TUNNEL_NAME
  TUNNEL_NAME="${TUNNEL_NAME:-$default_name}"
fi

echo ""
echo "===== Resumo da configuracao ====="
echo "  Dominio:        $DOMINIO"
echo "  Subdominio:     $SUBDOMINIO"
echo "  URL publica:    https://$HOSTNAME_FULL"
echo "  Nome do tunel:  $TUNNEL_NAME"
echo "  Servico local:  $LOCAL_SERVICE"
echo ""
read -rp "Confirmar e prosseguir? [s/N] " ans
if [[ ! "$ans" =~ ^[sS]$ ]]; then
  echo "Cancelado."
  exit 0
fi

# --- 2. Instalar cloudflared (se ainda nao tiver) --------------------------
passo "Verificando binario cloudflared"
if command -v cloudflared >/dev/null 2>&1; then
  ok "cloudflared ja instalado: $(cloudflared --version 2>&1 | head -n1)"
else
  ARCH="$(dpkg --print-architecture)"
  case "$ARCH" in
    armhf) BIN="cloudflared-linux-armhf" ;;
    arm64) BIN="cloudflared-linux-arm64" ;;
    amd64) BIN="cloudflared-linux-amd64" ;;
    *)
      erro "Arquitetura nao suportada: $ARCH"
      erro "Veja binarios disponiveis: https://github.com/cloudflare/cloudflared/releases"
      exit 1
      ;;
  esac
  passo "Baixando $BIN do GitHub releases da Cloudflare"
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  curl -fsSL -o "$TMP/cloudflared" \
    "https://github.com/cloudflare/cloudflared/releases/latest/download/$BIN"
  chmod +x "$TMP/cloudflared"
  sudo mv "$TMP/cloudflared" /usr/local/bin/cloudflared
  ok "Instalado: $(cloudflared --version 2>&1 | head -n1)"
fi

# --- 3. Autenticacao (cert.pem) --------------------------------------------
passo "Verificando autenticacao na conta Cloudflare"
if [ -f "$HOME/.cloudflared/cert.pem" ]; then
  ok "Ja autenticado (cert.pem encontrado)"
else
  echo ""
  echo "  Vou abrir uma URL de autorizacao. Voce vai:"
  echo "    1. Copiar a URL que aparecer"
  echo "    2. Abrir no navegador do celular ou laptop (qualquer um logado na Cloudflare)"
  echo "    3. Selecionar o dominio '$DOMINIO' e clicar em 'Authorize'"
  echo ""
  read -rp "Pressione Enter para iniciar..."
  cloudflared tunnel login
  if [ ! -f "$HOME/.cloudflared/cert.pem" ]; then
    erro "cert.pem nao foi criado. Autorizacao falhou ou foi cancelada."
    exit 1
  fi
  ok "Autenticacao concluida"
fi

# --- 4. Criar tunel (idempotente) ------------------------------------------
passo "Criando tunel '$TUNNEL_NAME'"
EXISTING_UUID="$(cloudflared tunnel list 2>/dev/null \
  | awk -v name="$TUNNEL_NAME" '$2==name {print $1}' \
  | head -n1 || true)"

if [ -n "$EXISTING_UUID" ]; then
  TUNNEL_UUID="$EXISTING_UUID"
  ok "Tunel ja existe: $TUNNEL_NAME (UUID: $TUNNEL_UUID)"
else
  OUT="$(cloudflared tunnel create "$TUNNEL_NAME" 2>&1)"
  echo "$OUT"
  TUNNEL_UUID="$(echo "$OUT" \
    | grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' \
    | head -n1)"
  if [ -z "$TUNNEL_UUID" ]; then
    erro "Nao consegui extrair UUID do tunel criado. Veja o output acima."
    exit 1
  fi
  ok "Tunel criado: UUID $TUNNEL_UUID"
fi

CREDENTIALS_FILE="$HOME/.cloudflared/${TUNNEL_UUID}.json"
if [ ! -f "$CREDENTIALS_FILE" ]; then
  erro "Arquivo de credenciais nao encontrado: $CREDENTIALS_FILE"
  erro "Pode ter sido criado em outra conta. Delete e recrie:"
  erro "  cloudflared tunnel delete $TUNNEL_NAME && rerun this script"
  exit 1
fi

# --- 5. Rota DNS (idempotente) --------------------------------------------
passo "Configurando CNAME ${HOSTNAME_FULL} -> tunel"
if cloudflared tunnel route dns "$TUNNEL_NAME" "$HOSTNAME_FULL" 2>&1 \
     | tee /tmp/cf-route.log \
     | grep -qiE "already exists|added CNAME"; then
  ok "DNS configurado (CNAME -> ${TUNNEL_UUID}.cfargotunnel.com)"
else
  if grep -qi "already" /tmp/cf-route.log; then
    ok "CNAME ja existia"
  else
    aviso "Saida nao reconhecida do 'route dns' — verifique no painel DNS da Cloudflare."
    aviso "Esperado: CNAME ${SUBDOMINIO} -> ${TUNNEL_UUID}.cfargotunnel.com (Proxied)"
  fi
fi
rm -f /tmp/cf-route.log

# --- 6. Config do tunel ----------------------------------------------------
passo "Gerando /etc/cloudflared/config.yml"
sudo mkdir -p /etc/cloudflared
sudo cp "$CREDENTIALS_FILE" "/etc/cloudflared/${TUNNEL_UUID}.json"
sudo chmod 600 "/etc/cloudflared/${TUNNEL_UUID}.json"

sudo tee /etc/cloudflared/config.yml >/dev/null <<EOF
# Gerado por deploy/install_cloudflared.sh em $(date -Iseconds)
# Tunel que expoe o totem em HTTPS publico via Cloudflare.
# NAO commitar este arquivo — contem caminho de credenciais.

tunnel: ${TUNNEL_UUID}
credentials-file: /etc/cloudflared/${TUNNEL_UUID}.json

# Logs detalhados ajudam a debugar problemas de conectividade.
loglevel: info

ingress:
  # Trafego pro subdominio publico vai pro Gunicorn local.
  - hostname: ${HOSTNAME_FULL}
    service: ${LOCAL_SERVICE}
    originRequest:
      # Permite que o totem use websockets (futuro: SSE de presenca, etc).
      noTLSVerify: false
      connectTimeout: 30s
  # Catch-all: qualquer outro hostname recebe 404.
  - service: http_status:404
EOF
sudo chmod 644 /etc/cloudflared/config.yml
ok "Config gravada em /etc/cloudflared/config.yml"

# --- 7. Servico systemd ----------------------------------------------------
passo "Instalando servico systemd (cloudflared.service)"
if systemctl list-unit-files | grep -q '^cloudflared.service'; then
  ok "Servico ja instalado — vou recarregar config"
  sudo systemctl daemon-reload
else
  # 'cloudflared service install' cria o unit file e ja sobe o servico.
  sudo cloudflared --config /etc/cloudflared/config.yml service install
  ok "Servico instalado"
fi

sudo systemctl enable cloudflared >/dev/null 2>&1 || true
sudo systemctl restart cloudflared
sleep 3

if sudo systemctl is-active --quiet cloudflared; then
  ok "Servico cloudflared ativo"
else
  erro "Servico cloudflared NAO esta ativo. Veja logs:"
  erro "  sudo journalctl -u cloudflared -n 50 --no-pager"
  exit 1
fi

# --- 8. Atualizar .env do projeto (opcional, melhora DX) -------------------
ENV_FILE="$PROJECT_DIR/.env"
if [ -f "$ENV_FILE" ]; then
  passo "Registrando TOTEM_PUBLIC_URL no .env do projeto"
  PUBLIC_URL="https://${HOSTNAME_FULL}"
  if grep -q "^TOTEM_PUBLIC_URL=" "$ENV_FILE"; then
    sed -i "s|^TOTEM_PUBLIC_URL=.*|TOTEM_PUBLIC_URL=${PUBLIC_URL}|" "$ENV_FILE"
    ok "TOTEM_PUBLIC_URL atualizado em $ENV_FILE"
  else
    echo "TOTEM_PUBLIC_URL=${PUBLIC_URL}" >> "$ENV_FILE"
    ok "TOTEM_PUBLIC_URL adicionado a $ENV_FILE"
  fi
fi

# --- 9. Teste de fumaca ----------------------------------------------------
passo "Testando resolucao DNS"
if command -v getent >/dev/null 2>&1; then
  if getent hosts "$HOSTNAME_FULL" >/dev/null 2>&1; then
    ok "DNS resolve $HOSTNAME_FULL"
  else
    aviso "DNS ainda nao propagou (geralmente leva <1 min na Cloudflare)"
  fi
fi

# --- 10. Resumo final ------------------------------------------------------
echo ""
echo -e "${VERDE}===========================================================${RESET}"
echo -e "${VERDE}  CLOUDFLARE TUNNEL INSTALADO COM SUCESSO${RESET}"
echo -e "${VERDE}===========================================================${RESET}"
echo ""
echo "  URL publica:    https://${HOSTNAME_FULL}"
echo "  Tunel:          ${TUNNEL_NAME} (${TUNNEL_UUID})"
echo "  Config:         /etc/cloudflared/config.yml"
echo "  Logs:           sudo journalctl -u cloudflared -f"
echo "  Status:         sudo systemctl status cloudflared"
echo ""
echo "Proximos passos:"
echo "  1. Abra https://${HOSTNAME_FULL} no celular — deve carregar com cadeado verde"
echo "  2. Teste o botao de voz — microfone agora libera (HTTPS valido)"
echo "  3. No Fully Kiosk Browser do totem, troque a Start URL pra:"
echo "        https://${HOSTNAME_FULL}"
echo "  4. Exit Fully + reabrir (mudanca de Start URL so vale apos restart)"
echo ""
echo "Para desfazer (caso precise):"
echo "  sudo systemctl disable --now cloudflared"
echo "  cloudflared tunnel delete ${TUNNEL_NAME}"
echo "  sudo rm -rf /etc/cloudflared /etc/systemd/system/cloudflared.service"
echo ""
