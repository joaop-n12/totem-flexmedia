import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


# Marker de SECRET_KEY default — qualquer valor IGUAL a este e' tratado
# como ausente em producao (ver ProductionConfig.__init_subclass__/init).
_DEV_SECRET_KEY = "flexmedia-dev-only-change-in-prod"


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", _DEV_SECRET_KEY)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    # ADMIN_PASSWORD: se definido, e' usado como senha inicial do super_admin
    # apenas se SUPERADMIN_PASSWORD nao estiver setado. NAO ha fallback fixo —
    # se nada for definido, o seed gera senha random forte e imprime no log.
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")

    # Session security
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # Flask-Limiter — storage default, sobrescrito em ProductionConfig.
    RATELIMIT_STORAGE_URL = os.environ.get("RATELIMIT_STORAGE_URL", "memory://")

    # LGPD — retencao de logs de interacao.
    # O visitante nao se identifica no totem, mas o texto transcrito pode conter
    # dados pessoais (ex: "meu nome eh Joao"). Mantemos o minimo necessario para
    # analise de uso e descartamos apos N dias via `flask purge-logs`.
    INTERACTION_LOG_RETENTION_DAYS = int(
        os.environ.get("INTERACTION_LOG_RETENTION_DAYS", "90")
    )

    # ── Hardening de autenticacao admin ──────────────────────────────────────
    # Lockout: apos LOCKOUT_THRESHOLD falhas seguidas, a conta fica bloqueada
    # por LOCKOUT_MINUTES. Defesa contra brute-force distribuido.
    LOCKOUT_THRESHOLD = int(os.environ.get("LOCKOUT_THRESHOLD", "5"))
    LOCKOUT_MINUTES   = int(os.environ.get("LOCKOUT_MINUTES",   "15"))

    # Idle timeout do painel admin (minutos). Sessao expira por inatividade.
    ADMIN_IDLE_TIMEOUT_MINUTES = int(os.environ.get("ADMIN_IDLE_TIMEOUT_MINUTES", "30"))

    # ── Heartbeat dos totens ─────────────────────────────────────────────────
    # Janela aceita do timestamp enviado pelo totem (anti-replay). 5 minutos
    # tolera relogio dessincronizado em RPi sem NTP, mas curto o suficiente
    # para nao deixar replays viaveis.
    HEARTBEAT_CLOCK_SKEW_SECONDS = int(
        os.environ.get("HEARTBEAT_CLOCK_SKEW_SECONDS", "300")
    )

    # ── Sprint 4: faixas de distancia para sessao de atendimento ─────────────
    # HC-SR04 mede em cm. Valores documentados no PDF de entrega.
    # ACTIVE  : <= 60 cm  → visitante alcanca a tela com a mao, inicia sessao.
    # INVITE  : <= 150 cm → visitante a 1 passo, mostra convite.
    # IDLE    : > 150 cm  → tela de espera.
    SESSION_INVITE_MAX_CM = float(os.environ.get("SESSION_INVITE_MAX_CM", "150"))
    SESSION_ACTIVE_MAX_CM = float(os.environ.get("SESSION_ACTIVE_MAX_CM", "60"))
    # Tempo sem presenca para encerrar sessao automaticamente.
    SESSION_TIMEOUT_SECONDS = float(os.environ.get("SESSION_TIMEOUT_SECONDS", "30"))
    # Pulso TRIG e ECHO do HC-SR04. Default segue pinagem documentada.
    HCSR04_TRIG_PIN = int(os.environ.get("HCSR04_TRIG_PIN", "23"))
    HCSR04_ECHO_PIN = int(os.environ.get("HCSR04_ECHO_PIN", "24"))

    # Modelo do sensor de temperatura/umidade. DHT11 (mais comum em kits
    # academicos) ou DHT22 (mais preciso). Mesma biblioteca e pinagem; o
    # driver ajusta classe da lib, faixa e precisao automaticamente.
    DHT_MODEL = (os.environ.get("DHT_MODEL", "DHT22") or "DHT22").upper()

    # Bypass dos sensores fisicos para testes em laptop/VM. Quando True:
    #   - overlay "Aproxime-se" nao e' renderizado no totem
    #   - polling/SSE de /api/session/state nao roda no frontend
    #   - saudacao TTS proativa e auto-redirect para /voice ficam inertes
    # NUNCA ligar em producao (Pi 3 em campo).
    TOTEM_DISABLE_SENSORS = (
        os.environ.get("TOTEM_DISABLE_SENSORS", "0").lower() in ("1", "true", "yes")
    )


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'flexmedia.db')}"
    )


class ProductionConfig(Config):
    DEBUG = False
    # Cookie da sessao so trafega via HTTPS e nunca acessivel via JS (HttpOnly
    # ja esta na Config base). SameSite=Strict bloqueia CSRF cross-site mais
    # agressivamente que Lax — mas mantemos Lax pois usuarios chegam via
    # links externos para /admin/login.
    #
    # SESSION_COOKIE_SECURE: default True (producao real atras de Nginx + TLS).
    # Override por env var para piloto em LAN sem HTTPS — sem ela, o navegador
    # recusa devolver o cookie em http://, o CSRF nao bate e o POST /admin/login
    # responde 403 antes mesmo de validar credenciais. Aceitavel apenas em
    # ambiente controlado; em producao publica, mantenha True.
    SESSION_COOKIE_SECURE = (
        os.environ.get("SESSION_COOKIE_SECURE", "true").lower() in ("1", "true", "yes")
    )
    SESSION_COOKIE_SAMESITE = "Lax"

    @classmethod
    def validate_runtime(cls) -> None:
        """Fail-fast: producao nao pode subir com SECRET_KEY default nem sem
        FIELD_ENCRYPTION_KEY. Chamado pelo factory quando env='production'.
        """
        if not os.environ.get("SECRET_KEY") or os.environ.get("SECRET_KEY") == _DEV_SECRET_KEY:
            raise RuntimeError(
                "SECRET_KEY ausente ou usando default de dev. "
                "Defina SECRET_KEY=<random 64+ bytes> no .env antes de subir prod."
            )
        if not os.environ.get("FIELD_ENCRYPTION_KEY") and not os.environ.get("FIELD_ENCRYPTION_KEYS"):
            raise RuntimeError(
                "FIELD_ENCRYPTION_KEY ausente. Gere uma com:\n"
                "  python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            )
    # DATABASE_URL no .env. Formatos aceitos:
    #   SQLite:    sqlite:////opt/totem-flexmedia/instance/flexmedia.db
    #   Postgres:  postgresql+psycopg://usuario:senha@host:5432/flexmedia
    # Se não definido, cai no SQLite local (apenas para testes; use Postgres em prod).
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'flexmedia.db')}"
    )
    # Rate limit compartilhado entre workers do Gunicorn — requer Redis.
    # Sem isso, cada worker conta separadamente e o limite efetivo dobra.
    RATELIMIT_STORAGE_URL = os.environ.get(
        "RATELIMIT_STORAGE_URL", "redis://localhost:6379/1"
    )


class TestingConfig(Config):
    TESTING = True
    DEBUG = False
    WTF_CSRF_ENABLED = False
    # Banco em memoria — cada execucao parte do zero.
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    # IMPORTANTE: SQLite `:memory:` cria um banco por CONEXAO. Sem StaticPool,
    # cada request do test_client recebe uma conexao nova → banco vazio →
    # commits feitos em outras conexoes nao sao visiveis. StaticPool mantem
    # uma unica conexao compartilhada para que dados commitados sejam vistos
    # por todas as requests + contextos da mesma execucao de teste.
    # `check_same_thread=False` e' necessario porque a unica conexao e' usada
    # de threads diferentes (test_client e fixture rodam no mesmo thread, mas
    # SQLAlchemy nao tem como saber).
    from sqlalchemy.pool import StaticPool
    SQLALCHEMY_ENGINE_OPTIONS = {
        "connect_args": {"check_same_thread": False},
        "poolclass": StaticPool,
    }
    # Desliga o rate limiter para nao interferir nos testes.
    RATELIMIT_ENABLED = False
    RATELIMIT_STORAGE_URL = "memory://"
    SECRET_KEY = "test-secret"
    OPENAI_API_KEY = "sk-test"


config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}
