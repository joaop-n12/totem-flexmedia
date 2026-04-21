import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "flexmedia-white-label-secret-change-in-prod")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
    # ADMIN_PASSWORD kept only as fallback for seed_super_admin; not used for login
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "flexmedia2024")
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


class DevelopmentConfig(Config):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'flexmedia.db')}"
    )


class ProductionConfig(Config):
    DEBUG = False
    SESSION_COOKIE_SECURE = True
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
