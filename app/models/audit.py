"""AdminAuditLog — trilha imutável de ações administrativas sensíveis.

Diferente do AuthLog (que registra tentativas de login) e do InteractionLog
(que registra uso da IA pelos visitantes), este log existe para responder à
pergunta: "quem mudou o quê, quando e de onde?".

Casos de uso:
  - Investigar incidentes de segurança ("por que essa instituição foi removida?")
  - Auditoria LGPD/ISO ("comprove que apenas usuários autorizados editaram X")
  - Detecção de comportamento anômalo (ações fora do horário, em massa)

Regras:
  - NUNCA editar nem deletar linhas existentes — apenas inserir.
  - Detalhes ficam em JSON livre, mas evite logar segredos (senhas, tokens).
"""
import json
from datetime import datetime

from app.extensions import db


# Lista controlada de ações conhecidas. Usar string livre dificulta consultas;
# manter constantes evita typos. Adicione novas conforme necessário.
ACTION_LOGIN_OK            = "login.success"
ACTION_LOGIN_FAIL          = "login.fail"
ACTION_LOGIN_LOCKED        = "login.locked"
ACTION_LOGOUT              = "logout"
ACTION_PASSWORD_CHANGE     = "user.password_change"
ACTION_USER_CREATE         = "user.create"
ACTION_USER_UPDATE         = "user.update"
ACTION_USER_DELETE         = "user.delete"
ACTION_INSTITUTION_CREATE  = "institution.create"
ACTION_INSTITUTION_UPDATE  = "institution.update"
ACTION_INSTITUTION_DELETE  = "institution.delete"
ACTION_DEVICE_CREATE       = "device.create"
ACTION_DEVICE_REVOKE       = "device.revoke"
ACTION_2FA_ENABLED         = "user.2fa_enabled"
ACTION_2FA_DISABLED        = "user.2fa_disabled"
ACTION_2FA_FAIL            = "user.2fa_fail"
ACTION_2FA_BACKUP_USED     = "user.2fa_backup_used"
ACTION_2FA_BACKUP_REGEN    = "user.2fa_backup_regen"
# Negacao de acesso cross-tenant: client_admin tentou ler/escrever em
# instituicao que nao e' a propria. Sinal forte de credencial comprometida
# ou bug de UI. Sempre auditado.
ACTION_TENANT_DENIED       = "tenant.access_denied"


class AdminAuditLog(db.Model):
    __tablename__ = "admin_audit_logs"
    __table_args__ = (
        db.Index("ix_audit_actor", "actor_user_id"),
        db.Index("ix_audit_action", "action"),
        db.Index("ix_audit_created_at", "created_at"),
        db.Index("ix_audit_resource", "resource_type", "resource_id"),
    )

    id            = db.Column(db.Integer, primary_key=True)
    # NULL quando a ação é de origem anônima (ex.: login fail com email inexistente).
    actor_user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_email   = db.Column(db.String(255), nullable=True)
    action        = db.Column(db.String(60), nullable=False)
    # resource_type: "user", "institution", "device" etc.  resource_id: PK alvo.
    resource_type = db.Column(db.String(40), nullable=True)
    resource_id   = db.Column(db.String(60), nullable=True)
    # Detalhes serializados em JSON (use texto para portar entre SQLite/Postgres).
    details_json  = db.Column(db.Text, nullable=True)
    ip_address    = db.Column(db.String(45), nullable=False, default="unknown")
    user_agent    = db.Column(db.String(255), nullable=True)
    created_at    = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    actor = db.relationship("User", backref=db.backref("audit_entries", lazy="dynamic"))

    @property
    def details(self) -> dict:
        if not self.details_json:
            return {}
        try:
            return json.loads(self.details_json)
        except json.JSONDecodeError:
            return {"_invalid_json": self.details_json[:200]}

    def __repr__(self):
        return f"<AdminAuditLog {self.action} by {self.actor_email or '?'}>"
