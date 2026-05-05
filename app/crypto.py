"""Cifragem simetrica de campos sensiveis em repouso (Fernet/AES-128-CBC + HMAC).

Usado para proteger:
  - api_key_secret dos totens (precisamos recuperar o segredo em claro para
    validar HMAC do heartbeat — hash one-way nao serve aqui).
  - totp_secret dos administradores (vazamento do banco nao deve quebrar 2FA
    de todos os admins de uma vez).

Chave:
  - Em producao: env FIELD_ENCRYPTION_KEY (Fernet.generate_key().decode()).
    Falha duro se ausente. Documentado em .env.example.
  - Em dev/teste: derivada de SECRET_KEY via HKDF — boot sem configuracao
    extra continua funcionando, mas SECRET_KEY de dev nao deve ser reusada
    em prod (a propria checagem de SECRET_KEY default ja avisa).

Rotacao:
  - Para girar a chave, definir FIELD_ENCRYPTION_KEYS (separadas por virgula).
    A primeira e usada para cifrar; todas sao tentadas para decifrar.
    Usar `MultiFernet` permite reciclar campos antigos sem downtime.
"""
import base64
import hashlib
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken, MultiFernet


_DEV_DERIVATION_INFO = b"flexmedia.field-encryption.v1"


def _derive_key_from_secret(secret_key: str) -> bytes:
    """Deriva uma Fernet key (32 bytes b64) a partir do SECRET_KEY.

    Usado APENAS em dev/teste. Em producao FIELD_ENCRYPTION_KEY e exigido.
    """
    raw = hashlib.sha256(secret_key.encode("utf-8") + _DEV_DERIVATION_INFO).digest()
    return base64.urlsafe_b64encode(raw)


def _build_cipher() -> MultiFernet:
    """Constroi o cipher a partir das envs.

    Tres caminhos:
      1. FIELD_ENCRYPTION_KEYS=k1,k2,...    → MultiFernet (rotacao)
      2. FIELD_ENCRYPTION_KEY=k             → MultiFernet com 1 chave
      3. nenhum                              → deriva de SECRET_KEY (dev only)
    """
    rotation = os.environ.get("FIELD_ENCRYPTION_KEYS")
    if rotation:
        keys = [k.strip().encode() for k in rotation.split(",") if k.strip()]
        return MultiFernet([Fernet(k) for k in keys])

    primary = os.environ.get("FIELD_ENCRYPTION_KEY")
    if primary:
        return MultiFernet([Fernet(primary.strip().encode())])

    secret_key = os.environ.get("SECRET_KEY")
    if secret_key:
        return MultiFernet([Fernet(_derive_key_from_secret(secret_key))])

    # Ultimo recurso: chave fixa de teste. Nao deve ocorrer em prod porque
    # ProductionConfig falha sem SECRET_KEY/FIELD_ENCRYPTION_KEY.
    return MultiFernet([Fernet(_derive_key_from_secret("flexmedia-default-dev"))])


_cipher: Optional[MultiFernet] = None


def _get_cipher() -> MultiFernet:
    global _cipher
    if _cipher is None:
        _cipher = _build_cipher()
    return _cipher


def reset_cipher_cache() -> None:
    """Forca releitura das envs na proxima chamada (uso: testes que mudam env)."""
    global _cipher
    _cipher = None


def encrypt_field(plaintext: str) -> str:
    """Cifra uma string. Retorna texto urlsafe (cabe em coluna VARCHAR)."""
    if plaintext is None:
        return None
    return _get_cipher().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_field(ciphertext: str) -> str:
    """Decifra. Levanta InvalidToken se a chave nao bater."""
    if ciphertext is None:
        return None
    return _get_cipher().decrypt(ciphertext.encode("ascii")).decode("utf-8")


def safe_decrypt_field(ciphertext: str) -> Optional[str]:
    """Versao tolerante: retorna None em vez de excecao.

    Util para campos que podem conter valor legado em texto puro durante
    migracao — chamador trata None como 'nao foi possivel decifrar'.
    """
    if not ciphertext:
        return None
    try:
        return decrypt_field(ciphertext)
    except InvalidToken:
        return None
