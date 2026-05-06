#!/bin/bash
# ==========================================================================
# Instalador do Totem FlexMedia para Raspberry Pi / Linux kiosk
# Configura Flask + Chromium em modo kiosk robusto (fullscreen forcado,
# auto-restart, gestos desabilitados, watchdog offline)
#
# USO:
#   1. Clone o projeto em ~/totem_flexmedia (ou rode dentro da pasta)
#   2. chmod +x install_totem.sh
#   3. ./install_totem.sh
#
# O script e' idempotente: pode rodar de novo sem quebrar o que ja existe.
# ==========================================================================

set -euo pipefail

# Cores para feedback visual
VERDE='\033[0;32m'
AMARELO='\033[1;33m'
VERMELHO='\033[0;31m'
AZUL='\033[0;34m'
RESET='\033[0m'

passo()    { echo -e "\n${AZUL}==>${RESET} ${1}"; }
ok()       { echo -e "${VERDE}[OK]${RESET} ${1}"; }
aviso()    { echo -e "${AMARELO}[AVISO]${RESET} ${1}"; }
erro()     { echo -e "${VERMELHO}[ERRO]${RESET} ${1}" >&2; }

# --- 0. Pre-checks ---------------------------------------------------------
passo "Verificando ambiente"

if [ "$EUID" -eq 0 ]; then
  erro "Nao rode este script como root/sudo. Use o usuario normal (ex.: pi)."
  erro "O script chama sudo internamente apenas quando necessario."
  exit 1
fi

if ! sudo -v; then
  erro "Voce precisa ter privilegios de sudo para continuar."
  exit 1
fi

# Auto-detecta a pasta do projeto: se rodando de dentro dela, usa o cwd.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/wsgi.py" ] && [ -d "$SCRIPT_DIR/app" ]; then
  PROJECT_DIR="$SCRIPT_DIR"
elif [ -d "$HOME/totem_flexmedia" ]; then
  PROJECT_DIR="$HOME/totem_flexmedia"
else
  erro "Pasta do projeto nao encontrada."
  erro "Clone com:  git clone -b totem_tela_admin <url> ~/totem_flexmedia"
  exit 1
fi
ok "Projeto em: $PROJECT_DIR"

# Detecta se e' Raspberry Pi de verdade
IS_PI=0
if [ -f /proc/device-tree/model ] && grep -qi "raspberry pi" /proc/device-tree/model 2>/dev/null; then
  IS_PI=1
  ok "Raspberry Pi detectado ($(tr -d '\0' < /proc/device-tree/model))"
else
  aviso "Nao e' Raspberry Pi — sensores ficarao em modo mock."
fi

# --- 1. Dependencias de sistema --------------------------------------------
passo "Instalando dependencias do sistema (apt)"
sudo apt update
sudo apt install -y \
  python3 python3-pip python3-venv \
  chromium chromium-l10n \
  unclutter xdotool \
  fonts-noto-color-emoji \
  curl git
ok "Dependencias de sistema instaladas"

# --- 2. Projeto e virtualenv -----------------------------------------------
cd "$PROJECT_DIR"

passo "Criando ambiente virtual Python"
if [ ! -d venv ]; then
  python3 -m venv venv
  ok "venv criado"
else
  ok "venv ja existe (reaproveitando)"
fi
# shellcheck disable=SC1091
source venv/bin/activate
pip install --quiet --upgrade pip

passo "Instalando dependencias Python (requirements.txt)"
pip install -r requirements.txt

if [ "$IS_PI" -eq 1 ]; then
  passo "Instalando drivers de sensores (requirements-pi.txt)"
  if pip install -r requirements-pi.txt; then
    ok "Drivers de sensores instalados"
  else
    aviso "Falha ao instalar drivers — sensores ficarao em modo mock."
  fi
fi

# --- 3. Arquivo .env -------------------------------------------------------
passo "Configurando .env"
if [ ! -f .env ]; then
  echo ""
  echo "Vamos preencher os 3 segredos minimos. Pressione Ctrl+C para abortar."
  echo ""

  while true; do
    read -rp "Cole sua OPENAI_API_KEY (comeca com 'sk-'): " api_key
    if [[ "$api_key" =~ ^sk- ]]; then break; fi
    aviso "Chave invalida. A chave da OpenAI sempre comeca com 'sk-'."
  done

  while true; do
    read -rp "Email do super admin (ex.: admin@totem.com): " admin_email
    if [[ "$admin_email" =~ ^[^@]+@[^@]+\.[^@]+$ ]]; then break; fi
    aviso "Email invalido."
  done

  while true; do
    read -rsp "Senha do super admin (min. 10 caracteres): " admin_pass; echo
    read -rsp "Confirme a senha: " admin_pass2; echo
    if [ ${#admin_pass} -lt 10 ]; then
      aviso "Senha curta demais (precisa >= 10 caracteres)."
    elif [ "$admin_pass" != "$admin_pass2" ]; then
      aviso "Senhas nao conferem."
    else
      break
    fi
  done

  {
    echo "# Gerado por install_totem.sh em $(date -Iseconds)"
    echo "OPENAI_API_KEY=$api_key"
    echo "FLASK_DEBUG=false"
    echo "SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))')"
    echo "SUPERADMIN_EMAIL=$admin_email"
    echo "SUPERADMIN_PASSWORD=$admin_pass"
    echo "TOTEM_WAKE_SECRET=$(python3 -c 'import secrets;print(secrets.token_hex(32))')"
    echo "# Porta TCP do Gunicorn (kiosk e admin batem em http://localhost:8000)"
    echo "GUNICORN_BIND=127.0.0.1:8000"
  } > .env
  chmod 600 .env
  ok ".env criado (chmod 600)"
else
  # Garante que .env existente tenha GUNICORN_BIND (instalacoes antigas nao tinham).
  if ! grep -q "^GUNICORN_BIND=" .env; then
    echo "GUNICORN_BIND=127.0.0.1:8000" >> .env
    ok "GUNICORN_BIND=127.0.0.1:8000 adicionado ao .env existente"
  else
    ok ".env ja existe — preservando valores atuais"
  fi
fi

# --- 3.1 Banco de dados (cria tabelas + seed inicial) ----------------------
passo "Inicializando banco de dados"
export FLASK_APP=wsgi.py
set -a
# shellcheck disable=SC1091
source .env
set +a
flask init-db
flask seed
ok "Banco inicializado e seed aplicado"

# --- 4. Servico systemd do Flask (auto-restart) ----------------------------
passo "Criando servico systemd do Flask"
sudo bash -c "cat > /etc/systemd/system/totem-flexmedia.service <<EOF
[Unit]
Description=Totem FlexMedia Flask App
After=network-online.target
Wants=network-online.target

[Service]
User=$USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$PROJECT_DIR/venv/bin/gunicorn -c gunicorn.conf.py wsgi:app
EnvironmentFile=$PROJECT_DIR/.env
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF"

sudo systemctl daemon-reload
sudo systemctl enable totem-flexmedia
sudo systemctl restart totem-flexmedia
ok "Servico totem-flexmedia ativo (porta 8000)"

# --- 4.1 Daemon de sensores (PIR + DHT22) ----------------------------------
# Roda independente do Flask. Le o /etc/totem/credenciais.env (gerado pela
# tela de provisionamento de totens no painel admin).
if [ "$IS_PI" -eq 1 ] && [ -f "$PROJECT_DIR/deploy/totem-sensors.service" ]; then
  passo "Instalando daemon de sensores (PIR + DHT22)"
  sudo cp "$PROJECT_DIR/deploy/totem-sensors.service" /etc/systemd/system/
  sudo sed -i "s|/home/pi/totem_flexmedia|$PROJECT_DIR|g" /etc/systemd/system/totem-sensors.service
  sudo sed -i "s|^User=pi|User=$USER|" /etc/systemd/system/totem-sensors.service
  sudo systemctl daemon-reload
  sudo systemctl enable totem-sensors

  if [ -f /etc/totem/credenciais.env ]; then
    sudo systemctl restart totem-sensors
    ok "Daemon de sensores ativo"
  else
    aviso "Sensores instalados, MAS sem credenciais ainda."
    echo "  -> Acesse o painel admin: http://<IP>:8000/admin/login"
    echo "  -> Frota -> Provisionar -> copie API_KEY_ID e API_KEY_SECRET"
    echo "  -> Crie /etc/totem/credenciais.env (chmod 600) com:"
    echo "         TOTEM_API_KEY_ID=tk_..."
    echo "         TOTEM_API_KEY_SECRET=..."
    echo "         TOTEM_WAKE_SECRET=$(grep ^TOTEM_WAKE_SECRET= "$PROJECT_DIR/.env" | cut -d= -f2)"
    echo "  -> Depois: sudo systemctl start totem-sensors"
  fi
fi

# --- 5. Script do kiosk (fullscreen, sem gestos, watchdog) -----------------
passo "Criando script do kiosk"
mkdir -p "$HOME/.config"

cat > "$HOME/.config/totem-kiosk.sh" <<'EOF'
#!/bin/bash
# Kiosk launcher do Totem FlexMedia
# - Bloqueia screensaver e gerenciamento de energia
# - Esconde cursor apos 100ms
# - Aguarda o backend Flask responder antes de abrir o Chromium
# - Se a rede/backend cair, recarrega a pagina periodicamente

export DISPLAY=:0
URL="http://localhost:8000/"

# Desativa screensaver, DPMS e blank
xset s off
xset -dpms
xset s noblank

# Esconde cursor do mouse
unclutter -idle 0.1 -root &

# Limpa estado do Chromium que pode travar o kiosk (crash recovery prompt)
PROFILE_DIR="$HOME/.config/chromium-kiosk"
rm -rf "$PROFILE_DIR/Singleton"*
mkdir -p "$PROFILE_DIR"
# Remove flag "Chrome nao foi encerrado corretamente"
sed -i 's/"exited_cleanly":false/"exited_cleanly":true/; s/"exit_type":"Crashed"/"exit_type":"Normal"/' \
  "$PROFILE_DIR/Default/Preferences" 2>/dev/null || true

# Aguarda backend subir (ate 60s)
for i in $(seq 1 60); do
  if curl -fs "$URL" >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

# Watchdog: se o Chromium fechar por qualquer motivo, reabre
while true; do
  chromium \
    --kiosk \
    --noerrdialogs \
    --disable-infobars \
    --disable-session-crashed-bubble \
    --disable-features=TranslateUI,Translate \
    --disable-pinch \
    --overscroll-history-navigation=0 \
    --disable-features=TouchpadOverscrollHistoryNavigation \
    --check-for-update-interval=31536000 \
    --user-data-dir="$PROFILE_DIR" \
    --start-fullscreen \
    --incognito \
    --app="$URL"
  sleep 3
done
EOF

chmod +x "$HOME/.config/totem-kiosk.sh"

# --- 6. Autostart via .desktop (LXDE/XFCE/GNOME) ---------------------------
echo "Criando autostart do kiosk..."
mkdir -p "$HOME/.config/autostart"
cat > "$HOME/.config/autostart/totem-kiosk.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Totem FlexMedia Kiosk
Exec=$HOME/.config/totem-kiosk.sh
X-GNOME-Autostart-enabled=true
X-LXQt-Need-Tray=false
Terminal=false
EOF

# --- 7. Autostart tambem via LXDE (Raspberry Pi OS) ------------------------
LXDE_AUTOSTART="$HOME/.config/lxsession/LXDE-pi/autostart"
if [ -d "$(dirname "$LXDE_AUTOSTART")" ]; then
  mkdir -p "$(dirname "$LXDE_AUTOSTART")"
  touch "$LXDE_AUTOSTART"
  grep -q "totem-kiosk.sh" "$LXDE_AUTOSTART" || \
    echo "@$HOME/.config/totem-kiosk.sh" >> "$LXDE_AUTOSTART"
fi

# --- 8. Desabilita gestos de swipe/suspend do sistema ----------------------
# Em Raspberry Pi OS: remove atalhos que possam sair do kiosk
if command -v gsettings >/dev/null 2>&1; then
  gsettings set org.gnome.desktop.screensaver lock-enabled false 2>/dev/null || true
  gsettings set org.gnome.desktop.session idle-delay 0 2>/dev/null || true
fi

IP_LOCAL="$(hostname -I 2>/dev/null | awk '{print $1}')"

echo ""
echo -e "${VERDE}=========================================${RESET}"
echo -e "${VERDE}  INSTALACAO CONCLUIDA COM SUCESSO${RESET}"
echo -e "${VERDE}=========================================${RESET}"
echo ""
echo "Proximos passos:"
echo "  1. Acesse o painel admin:  http://${IP_LOCAL:-localhost}:8000/admin/login"
echo "  2. Faca login com o email/senha definidos acima."
if [ "$IS_PI" -eq 1 ]; then
  echo "  3. Frota -> Provisionar -> gere as credenciais do totem."
  echo "  4. Crie /etc/totem/credenciais.env (ver instrucoes acima)."
  echo "  5. sudo reboot   # kiosk sobe sozinho no boot"
else
  echo "  3. sudo reboot   # kiosk sobe sozinho no boot"
fi
echo ""
echo "Comandos uteis:"
echo "  journalctl -u totem-flexmedia -f      # logs do backend ao vivo"
echo "  journalctl -u totem-sensors -f        # logs do daemon de sensores"
echo "  sudo systemctl restart totem-flexmedia"
echo "  curl http://localhost:8000/           # teste rapido"
echo ""
