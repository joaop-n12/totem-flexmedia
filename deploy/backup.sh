#!/bin/bash
# =============================================================================
# Totem FlexMedia — Backup do banco de dados
# =============================================================================
# Detecta SQLite ou Postgres a partir do DATABASE_URL no .env e salva um
# snapshot datado em $BACKUP_DIR. Mantém os últimos 14 backups.
#
# Uso manual:
#   sudo -u totem /opt/totem-flexmedia/deploy/backup.sh
#
# Agendamento (via cron do root):
#   0 3 * * *  /opt/totem-flexmedia/deploy/backup.sh
# =============================================================================

set -euo pipefail

APP_DIR="${APP_DIR:-/opt/totem-flexmedia}"
BACKUP_DIR="${BACKUP_DIR:-$APP_DIR/backups}"
RETENTION="${BACKUP_RETENTION:-14}"

mkdir -p "$BACKUP_DIR"

# Carrega DATABASE_URL do .env
if [[ -f "$APP_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$APP_DIR/.env"
  set +a
fi

STAMP=$(date +%Y%m%d-%H%M%S)
DB_URL="${DATABASE_URL:-sqlite:///$APP_DIR/instance/flexmedia.db}"

if [[ "$DB_URL" == postgresql* || "$DB_URL" == postgres* ]]; then
  OUT="$BACKUP_DIR/flexmedia-$STAMP.sql.gz"
  echo "Backup Postgres → $OUT"
  pg_dump "$DB_URL" | gzip -9 > "$OUT"
else
  # SQLite — usa .backup (consistente com escritas em andamento)
  DB_PATH="${DB_URL#sqlite:///}"
  # Remove o 4º / caso esteja com 4 barras (sqlite:////path)
  DB_PATH="${DB_PATH#/}"
  [[ "$DB_PATH" != /* ]] && DB_PATH="/$DB_PATH"
  OUT="$BACKUP_DIR/flexmedia-$STAMP.db"
  echo "Backup SQLite → $OUT"
  sqlite3 "$DB_PATH" ".backup '$OUT'"
  gzip -9 "$OUT"
  OUT="$OUT.gz"
fi

# Rotação: mantém os $RETENTION mais recentes
cd "$BACKUP_DIR"
ls -1t flexmedia-* 2>/dev/null | tail -n +$((RETENTION + 1)) | xargs -r rm -v

echo "Backup concluído: $OUT"
ls -lh "$BACKUP_DIR" | tail -n +2
