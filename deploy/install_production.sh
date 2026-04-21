#!/bin/bash
# =============================================================================
# Totem FlexMedia — Instalador de Produção (Raspberry Pi / Debian / Ubuntu)
# =============================================================================
# Provisiona: Nginx + Gunicorn + systemd + SSL (Let's Encrypt)
#
# Uso:
#   sudo bash deploy/install_production.sh
#
# Requisitos:
#   - Domínio apontado para o IP do servidor (registro A)
#   - Portas 80 e 443 liberadas
#   - E-mail válido para o Let's Encrypt
# =============================================================================

set -euo pipefail

# ------- Configuração (pode ser sobrescrita por env) --------------------------
APP_USER="${APP_USER:-totem}"
APP_DIR="${APP_DIR:-/opt/totem-flexmedia}"
REPO_SRC="${REPO_SRC:-$(pwd)}"
DOMAIN="${DOMAIN:-}"
LETSENCRYPT_EMAIL="${LETSENCRYPT_EMAIL:-}"

if [[ $EUID -ne 0 ]]; then
  echo "Execute como root: sudo bash $0" >&2
  exit 1
fi

# ------- Entrada interativa ---------------------------------------------------
if [[ -z "$DOMAIN" ]]; then
  read -rp "Domínio (ex: totem.flexmedia.com.br): " DOMAIN
fi
if [[ -z "$LETSENCRYPT_EMAIL" ]]; then
  read -rp "E-mail para Let's Encrypt: " LETSENCRYPT_EMAIL
fi

echo "===== Instalando Totem FlexMedia em produção ====="
echo "  Usuário:  $APP_USER"
echo "  Diretório: $APP_DIR"
echo "  Domínio:   $DOMAIN"
echo

# ------- Pacotes do sistema ---------------------------------------------------
apt-get update
apt-get install -y python3 python3-venv python3-pip nginx certbot python3-certbot-nginx \
                   redis-server sqlite3 cron

# Redis só precisa ouvir no localhost (rate limit local do Gunicorn)
systemctl enable --now redis-server
systemctl enable --now cron

# ------- Usuário do serviço ---------------------------------------------------
if ! id "$APP_USER" &>/dev/null; then
  useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi
usermod -aG www-data "$APP_USER" || true

# ------- Diretório da aplicação -----------------------------------------------
mkdir -p "$APP_DIR"
# Copia os arquivos do projeto (exceto venv/instance antigos)
rsync -a --delete \
  --exclude 'venv' \
  --exclude '__pycache__' \
  --exclude '.git' \
  --exclude 'instance' \
  "$REPO_SRC"/ "$APP_DIR"/

# Diretórios persistentes (banco, uploads, logs, backups)
mkdir -p "$APP_DIR/instance" "$APP_DIR/static/uploads" "$APP_DIR/logs" "$APP_DIR/backups"
chown -R "$APP_USER:www-data" "$APP_DIR"
chmod -R g+rX "$APP_DIR"
chmod -R g+rwX "$APP_DIR/instance" "$APP_DIR/static/uploads" "$APP_DIR/logs" "$APP_DIR/backups"
chmod +x "$APP_DIR/deploy/backup.sh" || true

# ------- Virtualenv + dependências --------------------------------------------
sudo -u "$APP_USER" python3 -m venv "$APP_DIR/venv"
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install --upgrade pip
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

# ------- .env (preserva se já existir) ----------------------------------------
if [[ ! -f "$APP_DIR/.env" ]]; then
  echo
  echo "===== Configurando .env ====="
  read -rp "OPENAI_API_KEY: " OPENAI_KEY
  read -rp "SUPERADMIN_EMAIL: " SUPER_EMAIL
  read -rsp "SUPERADMIN_PASSWORD (mín. 10 caracteres): " SUPER_PASS
  echo

  # Banco de dados — SQLite local ou PostgreSQL externo
  echo
  echo "Banco de dados:"
  echo "  1) SQLite local  (arquivo em $APP_DIR/instance/flexmedia.db)"
  echo "  2) PostgreSQL externo"
  read -rp "Escolha [1]: " DB_CHOICE
  DB_CHOICE="${DB_CHOICE:-1}"

  DATABASE_URL_LINE=""
  if [[ "$DB_CHOICE" == "2" ]]; then
    echo "Formato: postgresql+psycopg://usuario:senha@host:5432/flexmedia"
    read -rp "DATABASE_URL: " DB_URL
    DATABASE_URL_LINE="DATABASE_URL=$DB_URL"
  fi

  SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
  cat > "$APP_DIR/.env" <<EOF
FLASK_ENV=production
SECRET_KEY=$SECRET
OPENAI_API_KEY=$OPENAI_KEY
SUPERADMIN_EMAIL=$SUPER_EMAIL
SUPERADMIN_PASSWORD=$SUPER_PASS
$DATABASE_URL_LINE
EOF
  chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
fi

# ------- Migrations + seed ----------------------------------------------------
# Cria (ou atualiza) o schema via Flask-Migrate e popula dados iniciais.
# Idempotente: roda em instalação nova e em updates subsequentes.
echo
echo "===== Aplicando migrations e seed ====="
sudo -u "$APP_USER" -E bash -c "
  set -e
  cd '$APP_DIR'
  source venv/bin/activate
  export FLASK_APP=wsgi.py FLASK_ENV=production
  set -a; source .env; set +a
  [ -d migrations ] || flask db init
  flask db migrate -m 'auto' || true
  flask db upgrade
  flask seed
"

# ------- Systemd service ------------------------------------------------------
cp "$APP_DIR/deploy/totem-flexmedia.service" /etc/systemd/system/totem-flexmedia.service
systemctl daemon-reload
systemctl enable totem-flexmedia
systemctl restart totem-flexmedia

# ------- Nginx ----------------------------------------------------------------
NGINX_CONF="/etc/nginx/sites-available/totem-flexmedia"
sed "s/__DOMAIN__/$DOMAIN/g" "$APP_DIR/deploy/nginx.conf.template" > "$NGINX_CONF"
ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/totem-flexmedia
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

# ------- SSL (Let's Encrypt) --------------------------------------------------
certbot --nginx \
  --non-interactive \
  --agree-tos \
  --redirect \
  --email "$LETSENCRYPT_EMAIL" \
  -d "$DOMAIN"

# Renovação automática já vem configurada via systemd timer do certbot.
systemctl enable certbot.timer || true
systemctl start  certbot.timer || true

systemctl reload nginx

# ------- Backup diário (cron) -------------------------------------------------
# Agenda backup do banco todo dia às 03:00 (horário do servidor).
CRON_FILE="/etc/cron.d/totem-flexmedia-backup"
cat > "$CRON_FILE" <<EOF
# Backup diário do Totem FlexMedia — mantém últimos 14 snapshots
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
0 3 * * * $APP_USER $APP_DIR/deploy/backup.sh >> $APP_DIR/logs/backup.log 2>&1
EOF
chmod 644 "$CRON_FILE"

echo
echo "===== INSTALAÇÃO CONCLUÍDA ====="
echo "  Aplicação: https://$DOMAIN"
echo "  Admin:     https://$DOMAIN/admin/login"
echo "  Status:    systemctl status totem-flexmedia"
echo "  Logs:      journalctl -u totem-flexmedia -f"
