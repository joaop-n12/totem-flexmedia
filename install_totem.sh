#!/bin/bash
# ==========================================================================
# Instalador do Totem FlexMedia para Raspberry Pi / Linux kiosk
# Configura Flask + Chromium em modo kiosk robusto (fullscreen forcado,
# auto-restart, gestos desabilitados, watchdog offline)
# ==========================================================================

set -e

echo "===== Instalando Totem FlexMedia ====="

# --- 1. Dependencias de sistema --------------------------------------------
sudo apt update
sudo apt install -y \
  python3 python3-pip python3-venv \
  chromium chromium-l10n \
  unclutter xdotool \
  fonts-noto-color-emoji \
  curl

# --- 2. Projeto e virtualenv -----------------------------------------------
PROJECT_DIR="$HOME/totem_flexmedia"
if [ ! -d "$PROJECT_DIR" ]; then
  echo "Pasta $PROJECT_DIR nao encontrada. Clone o projeto antes de rodar."
  exit 1
fi
cd "$PROJECT_DIR"

echo "Criando ambiente virtual..."
python3 -m venv venv
source venv/bin/activate

echo "Instalando dependencias Python..."
pip install -r requirements.txt

# --- 3. Arquivo .env -------------------------------------------------------
if [ ! -f .env ]; then
  echo ""
  echo "===== Configuracao da API ====="
  read -p "Cole sua OPENAI_API_KEY: " api_key
  read -p "Email do super admin (ex.: admin@totem.com): " admin_email
  read -s -p "Senha do super admin (minimo 10 caracteres): " admin_pass
  echo ""
  {
    echo "OPENAI_API_KEY=$api_key"
    echo "FLASK_DEBUG=false"
    echo "SECRET_KEY=$(python3 -c 'import secrets;print(secrets.token_hex(32))')"
    echo "SUPERADMIN_EMAIL=$admin_email"
    echo "SUPERADMIN_PASSWORD=$admin_pass"
  } > .env
  chmod 600 .env
  echo ".env criado (chmod 600)."
else
  echo ".env ja existe, pulando..."
fi

# --- 3.1 Banco de dados (cria tabelas + seed inicial) ----------------------
echo "Inicializando banco de dados..."
export FLASK_APP=app.py
set -a; source .env; set +a
flask init-db
flask seed

# --- 4. Servico systemd do Flask (auto-restart) ----------------------------
echo "Criando servico systemd do Flask..."
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

# --- 5. Script do kiosk (fullscreen, sem gestos, watchdog) -----------------
echo "Criando script do kiosk..."
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

echo ""
echo "===== INSTALACAO CONCLUIDA ====="
echo "Reinicie o equipamento: sudo reboot"
echo "Logs do Flask: journalctl -u totem-flexmedia -f"
