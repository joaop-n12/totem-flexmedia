"""Endpoints de saúde para monitoramento externo.

Dois níveis, seguindo o padrão do Kubernetes e de uptime checkers:

- /readyz  → liveness barato. Responde 200 OK sempre que o processo está vivo.
            Use este para reiniciar o container/serviço se travar.
- /healthz → readiness/health. Testa dependências críticas (DB, Redis se usado).
            Retorna 503 e JSON detalhado se alguma falhar. Use para alerta.

Ambos ficam isentos de rate limit e não são logados pelo Nginx.
"""
import os
from flask import Blueprint, current_app, jsonify
from sqlalchemy import text

from app.extensions import db, limiter

health_bp = Blueprint("health", __name__)


@health_bp.route("/readyz")
@limiter.exempt
def readyz():
    """Liveness: o processo Python está respondendo."""
    return jsonify(status="ok"), 200


@health_bp.route("/healthz")
@limiter.exempt
def healthz():
    """Health: banco e Redis (se configurado) estão acessíveis."""
    checks: dict[str, dict] = {}
    ok = True

    # --- Banco de dados ------------------------------------------------------
    try:
        db.session.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok"}
    except Exception as e:  # noqa: BLE001 — queremos capturar tudo aqui
        ok = False
        checks["database"] = {"status": "fail", "error": str(e)[:200]}

    # --- Redis (rate limit storage) ------------------------------------------
    storage_url = current_app.config.get("RATELIMIT_STORAGE_URL", "")
    if storage_url.startswith("redis://") or storage_url.startswith("rediss://"):
        try:
            import redis  # type: ignore
            r = redis.Redis.from_url(storage_url, socket_connect_timeout=2)
            r.ping()
            checks["redis"] = {"status": "ok"}
        except Exception as e:  # noqa: BLE001
            ok = False
            checks["redis"] = {"status": "fail", "error": str(e)[:200]}
    else:
        checks["redis"] = {"status": "skipped", "reason": "memory storage"}

    # --- OpenAI key configurada ---------------------------------------------
    # Só confere presença — não chama a API para evitar custo por checagem.
    if os.environ.get("OPENAI_API_KEY"):
        checks["openai_key"] = {"status": "ok"}
    else:
        ok = False
        checks["openai_key"] = {"status": "fail", "error": "OPENAI_API_KEY não definido"}

    payload = {"status": "ok" if ok else "fail", "checks": checks}
    return jsonify(payload), 200 if ok else 503
