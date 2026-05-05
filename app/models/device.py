"""TotemDevice — representa um totem fisico em campo (frota de Raspberry Pi 3).

Cada totem provisionado recebe um par (api_key_id, api_key_secret):
  - api_key_id e' publico — vai no header X-Totem-Key para indicar QUEM esta
    falando.
  - api_key_secret e' privado — entregue UMA UNICA VEZ ao instalador, e nunca
    mais aparece em texto puro fora do banco. NUNCA trafega na rede apos o
    provisionamento (HMAC do request usa o segredo apenas no cliente).

Por que cifrar simetricamente em vez de hash one-way?
  Hash (scrypt/bcrypt) protege contra exposicao do banco mas torna impossivel
  recomputar HMAC do lado servidor. Antes deste modulo, o servidor exigia o
  segredo no header X-Totem-Secret para "validar" — o que neutralizava o HMAC
  porque um atacante que capturasse a requisicao tinha o segredo na mao.
  Agora cifra-se com Fernet (AES-128-CBC + HMAC-SHA256) usando uma chave
  separada (FIELD_ENCRYPTION_KEY). Dump do banco sem a chave de cifragem
  permanece inutil; e o servidor consegue recuperar o segredo para validar
  apenas a assinatura HMAC do heartbeat — o segredo nao trafega na rede.
"""
import hashlib
import hmac
import secrets
from datetime import datetime

from app.crypto import decrypt_field, encrypt_field, safe_decrypt_field
from app.extensions import db


# Tamanho do segredo em bytes — 32 bytes = 256 bits, suficiente para HMAC-SHA256.
API_KEY_BYTES = 32


def generate_api_key_id() -> str:
    """Identificador publico do dispositivo. Aparece nos logs sem risco."""
    # 16 bytes hex = 32 chars. Pequeno o bastante para caber em URL/header.
    return "tk_" + secrets.token_hex(16)


def generate_api_key_secret() -> str:
    """Segredo entregue UMA VEZ ao instalador. Nunca mais e' exibido."""
    return secrets.token_urlsafe(API_KEY_BYTES)


class TotemDevice(db.Model):
    __tablename__ = "totem_devices"
    __table_args__ = (
        db.Index("ix_devices_institution", "institution_id"),
        db.Index("ix_devices_status", "status"),
    )

    id              = db.Column(db.Integer, primary_key=True)
    institution_id  = db.Column(
        db.Integer,
        db.ForeignKey("institutions.id", ondelete="CASCADE"),
        nullable=False,
    )
    name            = db.Column(db.String(120), nullable=False)
    location        = db.Column(db.String(200), nullable=True)
    api_key_id      = db.Column(db.String(40), unique=True, nullable=False)
    # api_key_secret cifrado (Fernet). Coluna mapeada com nome legado
    # `api_key_hash` para compatibilidade com bancos existentes — semantica
    # mudou (ciphertext, nao mais hash).
    api_key_secret_encrypted = db.Column("api_key_hash", db.String(512), nullable=False)
    # status: "active" (em uso), "revoked" (chave invalidada), "decommissioned"
    status          = db.Column(db.String(20), nullable=False, default="active")
    # Telemetria mais recente reportada pelo totem.
    last_seen_at    = db.Column(db.DateTime, nullable=True)
    last_ip         = db.Column(db.String(45), nullable=True)
    app_version     = db.Column(db.String(40), nullable=True)
    cpu_temp_c      = db.Column(db.Float, nullable=True)
    free_disk_mb    = db.Column(db.Integer, nullable=True)
    uptime_seconds  = db.Column(db.Integer, nullable=True)
    # Telemetria do daemon de sensores (DHT22 + PIR). Opcional — totens sem
    # sensor fisico simplesmente nao reportam esses campos.
    ambient_temp_c       = db.Column(db.Float, nullable=True)
    ambient_humidity_pct = db.Column(db.Float, nullable=True)
    last_motion_at       = db.Column(db.DateTime, nullable=True)
    created_at      = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    institution = db.relationship(
        "Institution", backref=db.backref("devices", lazy="dynamic", cascade="all, delete-orphan")
    )

    def set_secret(self, secret: str) -> None:
        """Cifra e armazena o segredo. Chamado uma vez no provisionamento."""
        self.api_key_secret_encrypted = encrypt_field(secret)

    def get_secret(self) -> str:
        """Decifra e retorna o segredo em texto puro.

        Usado apenas para recomputar o HMAC do heartbeat. Nao expor em
        respostas HTTP nem em logs.
        """
        return decrypt_field(self.api_key_secret_encrypted)

    def verify_hmac(self, timestamp: str, body: bytes, signature_hex: str) -> bool:
        """Verifica HMAC-SHA256 do heartbeat em tempo constante.

        Mensagem assinada: f"{api_key_id}.{timestamp}.".encode() + body.
        Incluir api_key_id na mensagem impede que um atacante reuse a
        assinatura de um dispositivo num pedido com outro api_key_id.
        """
        secret = safe_decrypt_field(self.api_key_secret_encrypted)
        if not secret:
            return False
        expected = hmac.new(
            key=secret.encode("utf-8"),
            msg=f"{self.api_key_id}.{timestamp}.".encode("utf-8") + (body or b""),
            digestmod=hashlib.sha256,
        ).hexdigest()
        try:
            return hmac.compare_digest(expected, signature_hex or "")
        except (TypeError, ValueError):
            return False

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    def __repr__(self):
        return f"<TotemDevice {self.api_key_id} [{self.status}]>"
