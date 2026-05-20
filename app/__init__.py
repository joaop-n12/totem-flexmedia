"""Application factory for Totem FlexMedia White Label."""
import logging
import os
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler

from flask import Flask, g, redirect, request, session, url_for
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
    cfg = config_map.get(env, config_map["default"])
    # Em producao, valida envs criticas antes de inicializar nada.
    if hasattr(cfg, "validate_runtime"):
        cfg.validate_runtime()
    app.config.from_object(cfg)

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
            AdminAuditLog, TotemDevice, QuizQuestion, ExperienceRating,
        )


    # ── Integracoes externas (registry plugavel) ───────────────────────────────
    # Registradas ANTES dos blueprints — rotas dependem do registry populado.
    # Adicionar uma nova integracao aqui nao requer mudancas no core: cria-se
    # a classe em app/services/, instancia e chama registry.register(...).
    from app.services import registry as _integrations_registry
    from app.services.translation import TranslationIntegration
    _integrations_registry.reset()  # idempotente — relevante em testes/factory reuse
    _integrations_registry.register(TranslationIntegration(
        redis_url=app.config.get("RATELIMIT_STORAGE_URL"),
    ))

    # ── Blueprints ──────────────────────────────────────────────────────────────
    from app.routes.core              import core_bp
    from app.routes.zoo               import zoo_bp
    from app.routes.shopping          import shopping_bp
    from app.routes.pharmacy          import pharmacy_bp
    from app.routes.voice             import voice_bp
    from app.routes.translate         import translate_bp
    from app.routes.sync              import sync_bp
    from app.routes.quiz              import quiz_bp
    from app.routes.rating            import rating_bp
    from app.routes.admin_auth        import auth_bp
    from app.routes.admin_platform    import admin_platform_bp
    from app.routes.admin_institution import admin_institution_bp
    from app.routes.health            import health_bp
    from app.routes.devices           import devices_bp

    app.register_blueprint(core_bp)
    app.register_blueprint(zoo_bp)
    app.register_blueprint(shopping_bp)
    app.register_blueprint(pharmacy_bp)
    app.register_blueprint(voice_bp)
    app.register_blueprint(translate_bp)
    app.register_blueprint(sync_bp)
    app.register_blueprint(quiz_bp)
    app.register_blueprint(rating_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp,               url_prefix="/admin")
    app.register_blueprint(admin_platform_bp,     url_prefix="/admin/platform")
    app.register_blueprint(admin_institution_bp,  url_prefix="/admin")
    # devices_bp expoe /api/heartbeat (publico HMAC) + /admin/platform/devices/*
    # As rotas declaram seu proprio prefixo dentro do blueprint para diferenciar.
    app.register_blueprint(devices_bp)

    # ── Sentry (opcional) ───────────────────────────────────────────────────────
    # Se SENTRY_DSN estiver definido no .env, envia erros para o Sentry.
    # Requer: pip install "sentry-sdk[flask]" (não está no requirements por padrão).
    _init_sentry(app)

    # ── Security headers ─────────────────────────────────────────────────────────
    # Justificativa de cada header:
    #  - X-Content-Type-Options: bloqueia MIME sniffing (defesa contra XSS via upload).
    #  - X-Frame-Options: bloqueia clickjacking — admin nunca em iframe.
    #  - Referrer-Policy: limita o que vaza para terceiros (links externos da IA).
    #  - Strict-Transport-Security (HSTS): so em prod (HTTPS).
    #  - Permissions-Policy: desliga APIs perigosas que nao usamos (geo, USB, etc.).
    #    Microfone E permitido pois a rota /assistente usa SpeechRecognition.
    #  - Content-Security-Policy: bloqueia injection de scripts externos. Como
    #    usamos CDNs (jsDelivr, fonts.googleapis), liberamos por host. 'unsafe-inline'
    #    para scripts e CSS so no totem (templates antigos com inline) — futuro:
    #    migrar para nonces.
    @app.after_request
    def add_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-XSS-Protection", "0")  # legado — modernos ignoram
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy",
            "geolocation=(), camera=(), payment=(), usb=(), microphone=(self)",
        )

        # HSTS apenas em producao (com TLS); em dev poderia trancar localhost.
        if not app.config.get("DEBUG") and not app.config.get("TESTING"):
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )

        # CSP — versao pragmatica. Apertar com nonces depois de auditar templates.
        # Para o painel admin somos mais rigorosos (sem 'unsafe-inline' em script).
        if request.path.startswith("/admin"):
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; "
                "img-src 'self' data: blob:; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com; "
                "script-src 'self'; "
                "connect-src 'self'; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self'",
            )
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
        else:
            # Totem publico — mais permissivo (CDNs JS, audio, etc.).
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; "
                "img-src 'self' data: blob: https:; "
                "media-src 'self' blob: data:; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com data:; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net "
                "https://cdnjs.cloudflare.com; "
                "connect-src 'self' https://api.openai.com; "
                "frame-ancestors 'none'; "
                "base-uri 'self'",
            )
        return response

    # ── Sessao admin: idle timeout + binding por IP ──────────────────────────────
    # Ataques comuns evitados:
    #   - Sessao roubada e reusada dias depois → idle timeout invalida.
    #   - Cookie de sessao copiado para outro IP → comparamos session["_login_ip"].
    # A regra so vale para /admin (totem publico nao tem login).
    app.config.setdefault("PERMANENT_SESSION_LIFETIME", timedelta(hours=8))
    idle_minutes = int(os.environ.get("ADMIN_IDLE_TIMEOUT_MINUTES", "30"))

    @app.before_request
    def _enforce_admin_session_timeout():
        if not request.path.startswith("/admin"):
            return None
        # Login/logout/forgot nao precisam dessa checagem.
        if request.endpoint in {"auth.login", "auth.logout", "auth.forgot_password",
                                "static", None}:
            return None
        from flask_login import current_user as _cu
        if not _cu.is_authenticated:
            return None

        agora = datetime.utcnow()
        ultimo = session.get("_last_activity")
        if ultimo:
            try:
                ultimo_dt = datetime.fromisoformat(ultimo)
                if (agora - ultimo_dt) > timedelta(minutes=idle_minutes):
                    from flask_login import logout_user
                    logout_user()
                    session.clear()
                    return redirect(url_for("auth.login", next=request.path))
            except ValueError:
                session.pop("_last_activity", None)

        # Binding por IP — troca de IP encerra a sessao.
        login_ip = session.get("_login_ip")
        atual_ip = request.remote_addr or "unknown"
        if login_ip is None:
            session["_login_ip"] = atual_ip
        elif login_ip != atual_ip:
            from flask_login import logout_user
            logout_user()
            session.clear()
            return redirect(url_for("auth.login"))

        session["_last_activity"] = agora.isoformat()
        return None

    # ── Context processors ──────────────────────────────────────────────────────
    from app.helpers import generate_csrf_token

    @app.context_processor
    def inject_globals():
        from flask import request
        from flask_login import current_user
        from app.services.i18n import (
            SUPPORTED_LOCALES, get_locale, locale_display_name, t,
        )

        # Resolve a instituicao do path /admin/institutions/<iid>/... para que
        # o sidebar do admin (base.html) consiga calcular o link "Ver Totem"
        # apontando para a URL publica HTTPS especifica daquela instituicao.
        # Hit no identity map quando a rota ja carregou a inst — sem custo
        # extra. `request` pode nao existir em contextos como CLI.
        current_inst = None
        try:
            iid = (request.view_args or {}).get("iid") if request else None
        except RuntimeError:
            iid = None
        if iid:
            from app.models.institution import Institution
            try:
                current_inst = db.session.get(Institution, iid)
            except Exception:
                current_inst = None

        env_public_url = app.config.get("TOTEM_PUBLIC_URL") or None
        # URL final do "Ver Totem": ordem inst.public_url → env → None
        # (None deixa o template cair na rota interna como hoje).
        ver_totem_href = (
            current_inst.effective_public_url(env_public_url) if current_inst else env_public_url
        )

        return dict(
            institution=getattr(g, "institution", None),
            current_institution=current_inst,
            ver_totem_href=ver_totem_href,
            csrf_token=generate_csrf_token,
            current_user=current_user,
            # i18n: `t('chave')` traduz; `current_locale` e' o codigo atual.
            t=t,
            current_locale=get_locale,
            locale_display=locale_display_name,
            supported_locales=SUPPORTED_LOCALES,
            # Dev/teste sem hardware: oculta overlay e desliga polling de sensor.
            totem_disable_sensors=bool(app.config.get("TOTEM_DISABLE_SENSORS")),
        )

    # ── Filtro de traducao de conteudo do banco ────────────────────────────────
    # Conteudo gerenciado pelo client_admin (nomes, descricoes, habitat...) e'
    # cadastrado em PT. Quando o visitante escolhe EN/ES, este filtro traduz
    # on-the-fly via TranslationIntegration (mesma camada que /<slug>/api/translate
    # ja usa). Cache de 7 dias por (texto+idioma) — primeira visita estrangeira
    # paga 1 chamada OpenAI por string, as proximas sao gratis. Falha silenciosa:
    # se a integracao estiver offline/sem quota, devolve o PT original (UX
    # nunca quebra por falha de tradutor).
    #
    # Uso no template: {{ animal.descricao|tr }}
    @app.template_filter("tr")
    def _translate_content_filter(text):
        if not text:
            return text
        from app.services.i18n import DEFAULT_LOCALE, get_locale
        locale = get_locale()
        if locale == DEFAULT_LOCALE:
            return text
        try:
            from app.services import registry as _reg
            from app.services.translation import (
                TranslationError, TranslationIntegration,
            )
            integration = _reg.get("translation")
            if not isinstance(integration, TranslationIntegration):
                return text
            if not integration.is_available():
                return text
            result = integration.translate(
                text=str(text), target=locale, source="pt",
            )
            return result.text
        except TranslationError:
            return text  # offline/rate_limit/auth → devolve PT
        except Exception:  # noqa: BLE001 — defesa em profundidade
            app.logger.exception("filtro tr() falhou; devolvendo texto original")
            return text

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

    @app.cli.command("security-upgrade")
    def _security_upgrade_cmd():
        """Aplica colunas/tabelas novas do hardening em banco existente.

        Idempotente — pode ser re-executado. Usa introspecao para nao falhar
        se a coluna ja existir. Funciona com SQLite e Postgres.

        Uso: flask security-upgrade
        """
        import re as _re
        from sqlalchemy import inspect, text

        from app.crypto import encrypt_field, safe_decrypt_field
        from app.models import TotemDevice, User

        insp = inspect(db.engine)

        # 1. Cria as tabelas novas, se ainda nao existirem.
        db.create_all()

        # 2. Adiciona colunas novas em `users` se faltarem.
        # totp_secret agora cabe ate 512 chars (Fernet ciphertext).
        existing_cols = {c["name"] for c in insp.get_columns("users")}
        alters = [
            ("failed_login_count",      "INTEGER NOT NULL DEFAULT 0"),
            ("locked_until",            "TIMESTAMP NULL"),
            ("password_changed_at",     "TIMESTAMP NULL"),
            ("must_change_password",    "BOOLEAN NOT NULL DEFAULT 0"),
            ("totp_secret",             "VARCHAR(512) NULL"),
            ("totp_enabled",            "BOOLEAN NOT NULL DEFAULT 0"),
            ("totp_confirmed_at",       "TIMESTAMP NULL"),
            ("backup_codes_hash_json",  "TEXT NULL"),
        ]
        for col, ddl in alters:
            if col not in existing_cols:
                try:
                    db.session.execute(text(f"ALTER TABLE users ADD COLUMN {col} {ddl}"))
                    db.session.commit()
                    print(f"[security-upgrade] +coluna users.{col}")
                except Exception as exc:  # noqa: BLE001
                    db.session.rollback()
                    print(f"[security-upgrade] FALHA ao adicionar {col}: {exc}")

        # 2b. Colunas novas em `totem_devices` (telemetria de sensores fisicos).
        if insp.has_table("totem_devices"):
            existing_dev_cols = {c["name"] for c in insp.get_columns("totem_devices")}
            dev_alters = [
                ("ambient_temp_c",       "FLOAT NULL"),
                ("ambient_humidity_pct", "FLOAT NULL"),
                ("last_motion_at",       "TIMESTAMP NULL"),
            ]
            for col, ddl in dev_alters:
                if col not in existing_dev_cols:
                    try:
                        db.session.execute(text(f"ALTER TABLE totem_devices ADD COLUMN {col} {ddl}"))
                        db.session.commit()
                        print(f"[security-upgrade] +coluna totem_devices.{col}")
                    except Exception as exc:  # noqa: BLE001
                        db.session.rollback()
                        print(f"[security-upgrade] FALHA ao adicionar {col}: {exc}")

        # 2c. Coluna content_version em `institutions` (sync de conteudo remoto).
        if insp.has_table("institutions"):
            existing_inst_cols = {c["name"] for c in insp.get_columns("institutions")}
            if "content_version" not in existing_inst_cols:
                try:
                    db.session.execute(text(
                        "ALTER TABLE institutions ADD COLUMN content_version "
                        "INTEGER NOT NULL DEFAULT 0"
                    ))
                    db.session.commit()
                    print("[security-upgrade] +coluna institutions.content_version")
                except Exception as exc:  # noqa: BLE001
                    db.session.rollback()
                    print(f"[security-upgrade] FALHA ao adicionar content_version: {exc}")

        # 3. Cifra totp_secrets legados (texto puro base32) in-place.
        # Heuristica: base32 puro tem so [A-Z2-7], 32 chars exatos. Ciphertext
        # Fernet comeca com "gAAAAA" e e' bem mais longo.
        base32_re = _re.compile(r"^[A-Z2-7]{32}$")
        try:
            users = User.query.filter(User._totp_secret_enc.isnot(None)).all()
            migrated = 0
            for u in users:
                raw = u._totp_secret_enc or ""
                if base32_re.match(raw):
                    u._totp_secret_enc = encrypt_field(raw)
                    migrated += 1
            if migrated:
                db.session.commit()
                print(f"[security-upgrade] {migrated} totp_secret(s) cifrados em repouso")
        except Exception as exc:  # noqa: BLE001
            db.session.rollback()
            print(f"[security-upgrade] FALHA ao migrar totp_secrets: {exc}")

        # 4. Detecta devices com api_key_hash legado (hash werkzeug, nao
        # ciphertext Fernet). Esses NAO podem mais validar HMAC e sao
        # marcados como needs_reprovision para evitar telemetria suspeita.
        try:
            devices = TotemDevice.query.all()
            sinalizados = 0
            for d in devices:
                if not d.api_key_secret_encrypted:
                    continue
                # Tenta decifrar; se falhar e o valor parece hash werkzeug
                # (comeca com "scrypt:" ou "pbkdf2:"), e' legado.
                if safe_decrypt_field(d.api_key_secret_encrypted) is None:
                    if d.status == "active":
                        d.status = "needs_reprovision"
                        sinalizados += 1
            if sinalizados:
                db.session.commit()
                print(
                    f"[security-upgrade] {sinalizados} totem(ns) marcados como "
                    "needs_reprovision (hash legado nao permite validar HMAC). "
                    "Reprovisione cada um pela tela admin."
                )
        except Exception as exc:  # noqa: BLE001
            db.session.rollback()
            print(f"[security-upgrade] FALHA ao auditar devices: {exc}")

        print("[security-upgrade] OK.")

    return app
