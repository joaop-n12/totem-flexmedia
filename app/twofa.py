"""Funcoes utilitarias para 2FA TOTP (RFC 6238).

Decisoes de design:
  - Padrao TOTP-SHA1, 6 digitos, janela de 30s — compativel com 100% dos
    autenticadores (Google Authenticator, 1Password, Authy, Microsoft).
  - Toleramos +/- 1 step (30s antes/depois) para usuarios com relogio
    levemente fora do horario. Mais que isso vira janela de ataque.
  - 10 codigos de backup, formato xxxx-xxxx (8 hex chars) — humanamente
    digitaveis e suficientes para situacoes excepcionais.
  - Codigos de backup ficam armazenados apenas como hashes (Werkzeug).
    Quando o usuario perde acesso ao app autenticador, ele usa um codigo
    de backup que e invalidado na hora.
"""
import secrets
from io import BytesIO
from base64 import b64encode

import pyotp
import qrcode

# Numero de codigos de backup gerados de uma vez. 10 e o padrao da industria
# (GitHub, Google, AWS) — equilibrio entre conveniencia e exposicao.
BACKUP_CODES_COUNT = 10

# Issuer mostrado no app autenticador. O usuario ve "FlexMedia Admin: email".
TOTP_ISSUER = "FlexMedia Admin"


def generate_totp_secret() -> str:
    """Cria um segredo base32 de 32 chars (160 bits)."""
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str) -> str:
    """URI otpauth:// para o app autenticador escanear via QR code."""
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name=TOTP_ISSUER)


def qr_code_data_uri(uri: str) -> str:
    """Renderiza o URI como PNG e retorna data: URI para embed no <img>.

    Geramos o QR no servidor e enviamos como data URI para evitar dependencia
    de biblioteca JS de QR. PNG fica em memoria — nada toca o disco.
    """
    img = qrcode.make(uri)
    buf = BytesIO()
    img.save(buf, format="PNG")
    encoded = b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def verify_totp(secret: str, code: str) -> bool:
    """Verifica codigo de 6 digitos com janela de +/- 1 step (30s)."""
    if not secret or not code:
        return False
    code_clean = (code or "").replace(" ", "").strip()
    if not code_clean.isdigit() or len(code_clean) != 6:
        return False
    try:
        return pyotp.TOTP(secret).verify(code_clean, valid_window=1)
    except Exception:  # noqa: BLE001 — defensivo: input externo
        return False


def generate_backup_codes() -> list[str]:
    """Gera N codigos hex no formato xxxx-xxxx em minusculas.

    Retorna em texto claro — o chamador armazena apenas hashes via
    User.set_backup_codes(codes) e mostra os originais ao usuario uma unica vez.
    """
    codes: list[str] = []
    for _ in range(BACKUP_CODES_COUNT):
        raw = secrets.token_hex(4)  # 8 hex chars
        codes.append(f"{raw[:4]}-{raw[4:]}")
    return codes


def normalize_backup_input(value: str) -> str:
    """Padroniza entrada do usuario: minusculo, sem hifens nem espacos."""
    return (value or "").replace("-", "").replace(" ", "").lower().strip()
