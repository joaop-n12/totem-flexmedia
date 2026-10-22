"""User and AuthLog models for admin authentication."""
import json
from datetime import datetime, timedelta
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.crypto import encrypt_field, safe_decrypt_field
from app.extensions import db

ROLES = ("super_admin", "client_admin", "operational")


class User(UserMixin, db.Model):
    """Admin user — either FlexMedia staff (super_admin) or institution owner (client_admin)."""
    __tablename__ = "users"
    __table_args__ = (
        db.Index("ix_users_institution_id", "institution_id"),
        db.Index("ix_users_role_active", "role", "active"),
    )

    id             = db.Column(db.Integer, primary_key=True)
    email          = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash  = db.Column(db.String(255), nullable=False)
    name           = db.Column(db.String(100), nullable=False)
    # "super_admin" → acesso global | "client_admin" → acesso restrito à institution_id
    role           = db.Column(db.String(20), nullable=False, default="client_admin")
    # NULL para super_admin; FK obrigatória para client_admin
    institution_id = db.Column(
        db.Integer,
        db.ForeignKey("institutions.id", ondelete="SET NULL"),
        nullable=True,
    )
    active         = db.Column(db.Boolean, nullable=False, default=True)
    created_at     = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_login_at  = db.Column(db.DateTime, nullable=True)

    # ── Anti brute-force: lockout progressivo ─────────────────────────────────
    # failed_login_count zera a cada login bem-sucedido. Quando atinge o limite
    # configurado (LOCKOUT_THRESHOLD), locked_until recebe agora + LOCKOUT_MINUTES
    # e o usuário fica bloqueado mesmo que a senha seja correta.
    failed_login_count = db.Column(db.Integer, nullable=False, default=0)
    locked_until       = db.Column(db.DateTime, nullable=True)

    # ── Política de senha ─────────────────────────────────────────────────────
    # password_changed_at permite expirar senhas antigas (compliance).
    # must_change_password força troca no próximo login (uso: senha temporária
    # criada pelo super_admin ao provisionar uma nova conta).
    password_changed_at  = db.Column(db.DateTime, nullable=True)
    must_change_password = db.Column(db.Boolean, nullable=False, default=False)

    # ── 2FA TOTP ──────────────────────────────────────────────────────────────
    # totp_secret guarda a base32 secret usada pelo app autenticador (Google
    # Authenticator, 1Password, Authy, etc.). Cifrada em repouso via Fernet
    # (FIELD_ENCRYPTION_KEY) — vazamento do banco sem a chave nao quebra 2FA.
    # totp_enabled so vira True apos o usuario confirmar um codigo valido —
    # antes disso o segredo provisorio e descartavel sem comprometer o login.
    # Codigos de backup ficam apenas como hashes (lista JSON) — geramos em
    # texto claro uma unica vez na tela.
    # Coluna interna armazena ciphertext (urlsafe base64). O acesso publico
    # passa pela property `totp_secret` que cifra/decifra automaticamente.
    _totp_secret_enc        = db.Column("totp_secret", db.String(512), nullable=True)
    totp_enabled            = db.Column(db.Boolean,    nullable=False, default=False)
    totp_confirmed_at       = db.Column(db.DateTime,   nullable=True)
    backup_codes_hash_json  = db.Column(db.Text,       nullable=True)

    institution = db.relationship(
        "Institution", backref=db.backref("users", lazy="dynamic")
    )

    # Flask-Login: override is_active com campo do banco (soft-delete)
    @property
    def is_active(self):
        return self.active

    def get_id(self):
        return str(self.id)

    @property
    def is_super_admin(self):
        return self.role == "super_admin"

    @property
    def is_operational(self):
        return self.role == "operational"

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)
        self.password_changed_at = datetime.utcnow()
        self.must_change_password = False

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    # ── Lockout helpers ───────────────────────────────────────────────────────
    def is_locked(self) -> bool:
        """Retorna True se a conta está em janela de bloqueio ativa."""
        return bool(self.locked_until and self.locked_until > datetime.utcnow())

    def register_failed_login(self, threshold: int, lockout_minutes: int) -> None:
        """Incrementa o contador e bloqueia a conta se o limite for atingido."""
        self.failed_login_count = (self.failed_login_count or 0) + 1
        if self.failed_login_count >= threshold:
            self.locked_until = datetime.utcnow() + timedelta(minutes=lockout_minutes)

    def register_successful_login(self) -> None:
        """Limpa o contador de falhas e a janela de bloqueio."""
        self.failed_login_count = 0
        self.locked_until = None
        self.last_login_at = datetime.utcnow()

    # ── 2FA helpers ───────────────────────────────────────────────────────────
    @property
    def totp_secret(self) -> str | None:
        """Decifra e retorna o segredo TOTP em base32. None se nao configurado."""
        return safe_decrypt_field(self._totp_secret_enc) if self._totp_secret_enc else None

    @totp_secret.setter
    def totp_secret(self, value: str | None) -> None:
        """Cifra antes de armazenar. Atribuir None apaga o segredo."""
        self._totp_secret_enc = encrypt_field(value) if value else None

    @property
    def has_totp(self) -> bool:
        """True quando o usuario ja confirmou o segredo TOTP."""
        return bool(self.totp_enabled and self._totp_secret_enc)

    def set_backup_codes(self, codes: list[str]) -> None:
        """Armazena apenas hashes — os codigos em claro sao mostrados uma vez.

        Normaliza antes de hashear para garantir que a verificacao posterior
        (que tambem normaliza) bate independentemente de como o usuario digitou.
        """
        normalized = [c.replace("-", "").replace(" ", "").lower() for c in codes]
        self.backup_codes_hash_json = json.dumps(
            [generate_password_hash(c) for c in normalized]
        )

    def consume_backup_code(self, candidate: str) -> bool:
        """Verifica e remove (one-shot) um codigo de backup.

        Codigos sao comparados de forma constante via check_password_hash.
        Apos uso, o hash e removido da lista — codigos nao podem ser reusados.
        """
        if not self.backup_codes_hash_json or not candidate:
            return False
        try:
            hashes = json.loads(self.backup_codes_hash_json)
        except json.JSONDecodeError:
            return False
        normal = candidate.replace("-", "").replace(" ", "").lower()
        for h in list(hashes):
            if check_password_hash(h, normal):
                hashes.remove(h)
                self.backup_codes_hash_json = json.dumps(hashes)
                return True
        return False

    def remaining_backup_codes(self) -> int:
        if not self.backup_codes_hash_json:
            return 0
        try:
            return len(json.loads(self.backup_codes_hash_json))
        except json.JSONDecodeError:
            return 0

    def disable_totp(self) -> None:
        self._totp_secret_enc = None
        self.totp_enabled = False
        self.totp_confirmed_at = None
        self.backup_codes_hash_json = None

    def __repr__(self):
        return f"<User {self.email} [{self.role}]>"


class AuthLog(db.Model):
    """Registro de toda tentativa de login — sucesso ou falha."""
    __tablename__ = "auth_logs"
    __table_args__ = (
        db.Index("ix_auth_logs_email", "email"),
        db.Index("ix_auth_logs_created_at", "created_at"),
    )

    id         = db.Column(db.Integer, primary_key=True)
    email      = db.Column(db.String(255), nullable=False)
    user_id    = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    success    = db.Column(db.Boolean, nullable=False)
    ip_address = db.Column(db.String(45), nullable=False)  # IPv4 ou IPv6
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship("User", backref=db.backref("auth_logs", lazy="dynamic"))

    def __repr__(self):
        status = "OK" if self.success else "FAIL"
        return f"<AuthLog {self.email} {status} {self.ip_address}>"
