"""User and AuthLog models for admin authentication."""
from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db

ROLES = ("super_admin", "client_admin")


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

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

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
