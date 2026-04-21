"""Application factory for Totem FlexMedia White Label."""
import logging
import os
from logging.handlers import RotatingFileHandler

from flask import Flask, g, request
from werkzeug.middleware.proxy_fix import ProxyFix
from config import config_map
from app.extensions import db, migrate, login_manager, limiter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def _init_sentry(app: Flask) -> None:
    """Inicializa Sentry se SENTRY_DSN estiver no ambiente e o SDK instalado.

    Instalação opcional:  pip install 'sentry-sdk[flask]'
    Ativação:             defina SENTRY_DSN=https://... no .env
    """
    dsn = os.environ.get("SENTRY_DSN")
    if not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
    except ImportError:
        app.logger.warning("SENTRY_DSN definido mas sentry-sdk não instalado.")
        return
    sentry_sdk.init(
        dsn=dsn,
        integrations=[FlaskIntegration()],
        environment=os.environ.get("SENTRY_ENV", "production"),
        traces_sample_rate=float(os.environ.get("SENTRY_TRACES_RATE", "0.0")),
        send_default_pii=False,
    )
    app.logger.info("Sentry inicializado.")


def _configure_file_logging(app: Flask) -> None:
    """Adiciona log rotativo em disco (complementa o journald).

    Em caso de perda do journal (ex.: cartão SD corrompido no Pi), temos uma
    cópia em arquivo com rotação por tamanho. Só ativa em produção.
    """
    log_dir = os.environ.get("LOG_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs"))
    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError:
        app.logger.warning("Não foi possível criar %s — log em arquivo desabilitado.", log_dir)
        return

    handler = RotatingFileHandler(
        os.path.join(log_dir, "app.log"),
        maxBytes=5 * 1024 * 1024,  # 5 MB por arquivo
        backupCount=5,             # mantém 5 arquivos antigos (25 MB total)
        encoding="utf-8",
    )
    handler.setLevel(logging.INFO)
    handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    app.logger.addHandler(handler)
    app.logger.setLevel(logging.INFO)


def create_app(env: str = "default") -> Flask:
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates"),
        static_folder=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static"),
    )

    # ── Config ──────────────────────────────────────────────────────────────────
    app.config.from_object(config_map.get(env, config_map["default"]))

    os.makedirs(app.config.get("UPLOAD_FOLDER", "static/uploads"), exist_ok=True)
    os.makedirs(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "instance"), exist_ok=True)

    # ── Proxy (Nginx) ───────────────────────────────────────────────────────────
    # Em produção o app fica atrás do Nginx. Sem ProxyFix, o Flask vê todas as
    # requisições como HTTP (quebra SESSION_COOKIE_SECURE) e o IP do cliente
    # aparece como 127.0.0.1 (quebra o rate limiter). O Nginx envia
    # X-Forwarded-Proto e X-Forwarded-For — o ProxyFix lê esses cabeçalhos.
    if not app.config.get("DEBUG"):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
        _configure_file_logging(app)

    # ── Extensions ──────────────────────────────────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)
    limiter.init_app(app)

    # ── Flask-Login ──────────────────────────────────────────────────────────────
    login_manager.login_view = "auth.login"
    login_manager.login_message = None
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id: str):
        from app.models import User
        return User.query.get(int(user_id))

    # ── Import models so Migrate/SQLAlchemy sees them ───────────────────────────
    with app.app_context():
        from app.models import (  # noqa: F401
            Institution, Module, InstitutionModule,
            Animal, Event, Store, Product, FAQ, MapArea,
            InteractionLog, User, AuthLog,
        )

    # ── Blueprints ──────────────────────────────────────────────────────────────
    from app.routes.core              import core_bp
    from app.routes.zoo               import zoo_bp
    from app.routes.shopping          import shopping_bp
    from app.routes.pharmacy          import pharmacy_bp
    from app.routes.voice             import voice_bp
    from app.routes.admin_auth        import auth_bp
    from app.routes.admin_platform    import admin_platform_bp
    from app.routes.admin_institution import admin_institution_bp
    from app.routes.health            import health_bp

    app.register_blueprint(core_bp)
    app.register_blueprint(zoo_bp)
    app.register_blueprint(shopping_bp)
    app.register_blueprint(pharmacy_bp)
    app.register_blueprint(voice_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp,               url_prefix="/admin")
    app.register_blueprint(admin_platform_bp,     url_prefix="/admin/platform")
    app.register_blueprint(admin_institution_bp,  url_prefix="/admin")

    # ── Sentry (opcional) ───────────────────────────────────────────────────────
    # Se SENTRY_DSN estiver definido no .env, envia erros para o Sentry.
    # Requer: pip install "sentry-sdk[flask]" (não está no requirements por padrão).
    _init_sentry(app)

    # ── Security headers ─────────────────────────────────────────────────────────
    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-XSS-Protection", "1; mode=block")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        # Admin pages: never cache, never index
        if request.path.startswith("/admin"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
        return response

    # ── Context processors ──────────────────────────────────────────────────────
    from app.helpers import generate_csrf_token

    @app.context_processor
    def inject_globals():
        from flask_login import current_user
        return dict(
            institution=getattr(g, "institution", None),
            csrf_token=generate_csrf_token,
            current_user=current_user,
        )

    # ── Error handlers ───────────────────────────────────────────────────────────
    @app.errorhandler(403)
    def forbidden(e):
        from flask import render_template as _rt
        return _rt("403.html"), 403

    @app.errorhandler(404)
    def not_found(e):
        from flask import render_template as _rt
        return _rt("404.html"), 404

    @app.errorhandler(429)
    def ratelimit_error(e):
        from flask import render_template as _rt, jsonify
        if request.path.startswith("/api") or request.is_json:
            return jsonify({"error": "Muitas requisições. Aguarde e tente novamente."}), 429
        return _rt("admin/login.html",
                   error="Muitas tentativas. Aguarde alguns minutos."), 429

    @app.errorhandler(500)
    def server_error(e):
        from flask import render_template as _rt
        app.logger.error("Internal server error", exc_info=e)
        return _rt("500.html"), 500

    # ── Comandos CLI ─────────────────────────────────────────────────────────────
    # O schema é gerenciado por Flask-Migrate (Alembic):
    #   flask db init      → cria a pasta migrations/ (primeira vez apenas)
    #   flask db migrate   → gera migration comparando models x banco
    #   flask db upgrade   → aplica as migrations pendentes
    # Use `flask seed` para popular o catálogo de módulos e o super admin.
    # Os dois comandos abaixo são idempotentes — podem ser re-executados.

    @app.cli.command("seed")
    def _seed_cmd():
        """Popula o banco com dados iniciais (módulos, zoo demo, super admin)."""
        from app.seed import run_seed
        run_seed()
        print("Seed concluído.")

    @app.cli.command("purge-logs")
    def _purge_logs_cmd():
        """LGPD — remove InteractionLogs mais antigos que INTERACTION_LOG_RETENTION_DAYS.

        Recomenda-se agendar no cron diariamente:
            0 3 * * *  cd /opt/totem-flexmedia && venv/bin/flask purge-logs
        """
        from datetime import datetime, timedelta
        from app.models import InteractionLog
        days = app.config.get("INTERACTION_LOG_RETENTION_DAYS", 90)
        cutoff = datetime.utcnow() - timedelta(days=days)
        deleted = InteractionLog.query.filter(InteractionLog.created_at < cutoff).delete()
        db.session.commit()
        print(f"Removidos {deleted} logs anteriores a {cutoff.isoformat()} (retencao={days}d).")

    @app.cli.command("init-db")
    def _init_db_cmd():
        """Atalho para desenvolvimento — cria todas as tabelas sem migration.

        ATENÇÃO: em produção use `flask db upgrade` em vez deste comando.
        """
        db.create_all()
        print("Tabelas criadas via db.create_all().")

    return app
