"""Servico de traducao — primeira integracao externa do registry.

Atende o backlog Trello:
  - Modulo 2 - Integracao com APIs (Alta): primeira API funcional validada.
  - Modulo 3 - Acessibilidade e Idiomas (Baixa): suporte a PT/EN como base
    para visitantes estrangeiros (US3 do epico Visitante).

Implementacao:
  - Reusa OPENAI_API_KEY (gpt-4o-mini) — confirmado pelo usuario que e' a
    unica API ativa hoje. Trocar para DeepL/Google e' adicionar uma classe
    irma e re-registrar; a rota nao precisa mudar.
  - Cache em duas camadas: Redis quando RATELIMIT_STORAGE_URL apontar pra
    Redis, ou dict em memoria caso contrario (dev/test). Cache key e' hash
    de (texto + source + target) — TTL de 7 dias. Frase comum traduz uma
    vez e nunca mais paga OpenAI.
  - Erros classificados igual ao voice.py: offline / rate_limit / auth /
    generic. Mensagens amigaveis em pt-BR.
  - Limites de tamanho conservadores para nao virar canal de abuso de quota.
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from dataclasses import dataclass

from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)

logger = logging.getLogger(__name__)


# ── Limites e constantes ──────────────────────────────────────────────────────

MAX_TEXT_LEN = 1500          # caracteres aceitos por chamada
CACHE_TTL_SECONDS = 7 * 24 * 3600
SUPPORTED_LANGUAGES = {
    "pt": "Portuguese (Brazilian)",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
}

# Mensagens amigaveis — espelham o padrao do voice.py.
MSG_OFFLINE = "Tradução indisponível no momento. Tente novamente em instantes."
MSG_RATE    = "Muitas traduções solicitadas. Aguarde alguns segundos."
MSG_AUTH    = "Serviço de tradução temporariamente indisponível."
MSG_GENERIC = "Não consegui traduzir agora. Tente novamente."


# ── Erros ─────────────────────────────────────────────────────────────────────

class TranslationError(Exception):
    """Erro classificado para a rota mapear em status HTTP correto."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind        # "offline" | "rate_limit" | "auth" | "generic" | "invalid"
        self.message = message


# ── Cache backends ────────────────────────────────────────────────────────────

class _MemoryCache:
    """Fallback in-memory com TTL. Suficiente para dev/test e instalacoes
    pequenas (1 totem) onde Redis seria over-engineering."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store: dict[str, tuple[float, str]] = {}

    def get(self, key: str) -> str | None:
        with self._lock:
            entry = self._store.get(key)
            if not entry:
                return None
            expires, value = entry
            if time.time() > expires:
                self._store.pop(key, None)
                return None
            return value

    def set(self, key: str, value: str, ttl: int) -> None:
        with self._lock:
            # Cap simples para nao crescer indefinidamente em prod sem Redis.
            if len(self._store) > 5000:
                # Evicta as 1000 mais antigas — barato.
                sorted_items = sorted(self._store.items(), key=lambda kv: kv[1][0])
                for k, _ in sorted_items[:1000]:
                    self._store.pop(k, None)
            self._store[key] = (time.time() + ttl, value)


class _RedisCache:
    """Wrapper fino sobre redis.Redis. Falhas sao silenciosas — cache miss."""

    def __init__(self, url: str) -> None:
        import redis  # import tardio para nao forcar dependencia em dev
        self._client = redis.Redis.from_url(url, decode_responses=True,
                                            socket_timeout=2, socket_connect_timeout=2)

    def get(self, key: str) -> str | None:
        try:
            return self._client.get(key)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Redis cache miss/erro: %s", exc)
            return None

    def set(self, key: str, value: str, ttl: int) -> None:
        try:
            self._client.set(key, value, ex=ttl)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Redis cache set falhou: %s", exc)


# ── Servico ────────────────────────────────────────────────────────────────────

@dataclass
class TranslationResult:
    text: str
    cached: bool
    source_lang: str
    target_lang: str


class TranslationIntegration:
    """Integracao registrada no `app.services.registry`.

    Inicializada uma vez no boot. NAO armazena state mutavel alem do cache.
    """

    name = "translation"

    def __init__(self, redis_url: str | None = None,
                 model: str = "gpt-4o-mini") -> None:
        self.model = model
        self._cache = self._build_cache(redis_url)
        self._client: OpenAI | None = None  # lazy — evita custo no boot

    # ── Contrato de Integration ──────────────────────────────────────────

    def is_available(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))

    def health_check(self) -> dict:
        if not self.is_available():
            return {"ok": False, "detail": "OPENAI_API_KEY ausente"}
        backend = "redis" if isinstance(self._cache, _RedisCache) else "memoria"
        return {"ok": True, "detail": f"openai/{self.model} (cache: {backend})"}

    # ── API publica ──────────────────────────────────────────────────────

    def translate(
        self,
        text: str,
        target: str,
        source: str = "auto",
    ) -> TranslationResult:
        text = (text or "").strip()
        if not text:
            raise TranslationError("invalid", "Texto vazio.")
        if len(text) > MAX_TEXT_LEN:
            raise TranslationError(
                "invalid",
                f"Texto excede {MAX_TEXT_LEN} caracteres.",
            )
        if target not in SUPPORTED_LANGUAGES:
            raise TranslationError("invalid", f"Idioma destino '{target}' nao suportado.")
        if source != "auto" and source not in SUPPORTED_LANGUAGES:
            raise TranslationError("invalid", f"Idioma origem '{source}' nao suportado.")

        cache_key = self._cache_key(text, source, target)
        hit = self._cache.get(cache_key)
        if hit:
            return TranslationResult(
                text=hit, cached=True, source_lang=source, target_lang=target,
            )

        translated = self._call_openai(text, source, target)
        self._cache.set(cache_key, translated, CACHE_TTL_SECONDS)
        return TranslationResult(
            text=translated, cached=False, source_lang=source, target_lang=target,
        )

    # ── Internos ─────────────────────────────────────────────────────────

    @staticmethod
    def _build_cache(redis_url: str | None):
        if not redis_url or not redis_url.startswith(("redis://", "rediss://")):
            return _MemoryCache()
        try:
            return _RedisCache(redis_url)
        except Exception as exc:  # noqa: BLE001 — Redis indisponivel != broken app
            logger.warning("Cache Redis indisponivel (%s) — caindo para memoria", exc)
            return _MemoryCache()

    @staticmethod
    def _cache_key(text: str, source: str, target: str) -> str:
        h = hashlib.sha256(f"{source}|{target}|{text}".encode("utf-8")).hexdigest()
        return f"flexmedia:translate:{h[:32]}"

    def _get_client(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
        return self._client

    def _call_openai(self, text: str, source: str, target: str) -> str:
        target_name = SUPPORTED_LANGUAGES[target]
        if source == "auto":
            instr = (
                f"Detect the source language and translate the user message into "
                f"{target_name}. Reply with the translation only, no quotes, no "
                f"language labels, no explanations."
            )
        else:
            source_name = SUPPORTED_LANGUAGES[source]
            instr = (
                f"Translate the user message from {source_name} into {target_name}. "
                f"Reply with the translation only, no quotes, no labels, no notes."
            )

        try:
            resp = self._get_client().chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": instr},
                    {"role": "user",   "content": text},
                ],
                # Traducao raramente precisa de criatividade — temperatura baixa
                # da consistencia ao cache (mesma frase = mesma traducao).
                temperature=0.1,
                max_tokens=600,
            )
            return (resp.choices[0].message.content or "").strip()
        except (APIConnectionError, APITimeoutError) as exc:
            logger.warning("translation offline/timeout: %s", exc)
            raise TranslationError("offline", MSG_OFFLINE) from exc
        except RateLimitError as exc:
            logger.warning("translation rate-limited")
            raise TranslationError("rate_limit", MSG_RATE) from exc
        except AuthenticationError as exc:
            logger.error("translation auth error (chave OpenAI invalida?)")
            raise TranslationError("auth", MSG_AUTH) from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception("translation falha generica")
            raise TranslationError("generic", MSG_GENERIC) from exc
