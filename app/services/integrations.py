"""Registry plugavel de integracoes externas.

Atende o backlog Trello (Modulo 2 - Integracao com APIs):
  2.1 Suporte a multiplas APIs externas (traducao, visao, analytics).
  2.2 Arquitetura modular para adicionar novas APIs sem alterar o core.
  2.3 Tratamento de erros com mensagem amigavel.
  2.4 Pelo menos uma integracao funcional validada.

Como adicionar uma integracao nova (ex.: Google Vision):
  1. Cria `app/services/google_vision.py` com uma classe que expoe
     `name`, `is_available()`, `health_check()` e os metodos do dominio.
  2. No factory (app/__init__.py), faz:
        from app.services.google_vision import GoogleVisionIntegration
        registry.register(GoogleVisionIntegration())
  3. Pronto — qualquer rota/UI pode `registry.get("google_vision")`.

Princípios:
  - Registry e' singleton de processo (modulo). Em tests usar `registry.reset()`.
  - Falha no init de UMA integracao NUNCA derruba o app. Erros sao logados
    e a integracao fica como "indisponivel".
  - Cada integracao precisa expor `is_available()` para o admin saber se
    a chave/credencial esta configurada antes de oferecer o recurso ao
    visitante.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class Integration(Protocol):
    """Contrato minimo que toda integracao precisa atender."""

    name: str  # identificador unico (ex.: "translation", "google_vision")

    def is_available(self) -> bool:
        """True se as credenciais estao presentes e a integracao esta utilizavel."""
        ...

    def health_check(self) -> dict:
        """Snapshot de status para o painel admin: {ok: bool, detail: str}."""
        ...


@dataclass
class IntegrationInfo:
    name: str
    available: bool
    detail: str
    instance: Integration


@dataclass
class IntegrationRegistry:
    """Container thread-safe-ish (registro acontece no boot, leitura depois)."""

    _entries: dict[str, Integration] = field(default_factory=dict)

    def register(self, integration: Integration) -> None:
        """Adiciona uma integracao. Substitui se ja existir (util em testes)."""
        if not isinstance(integration, Integration):
            raise TypeError(
                f"{integration!r} nao implementa o protocolo Integration "
                "(precisa de name, is_available, health_check)."
            )
        if integration.name in self._entries:
            logger.info("Integracao %s sendo substituida no registry", integration.name)
        self._entries[integration.name] = integration

    def get(self, name: str) -> Integration | None:
        return self._entries.get(name)

    def require(self, name: str) -> Integration:
        """Como get(), mas levanta se ausente. Use em rotas que dependem dela."""
        inst = self._entries.get(name)
        if inst is None:
            raise KeyError(f"Integracao '{name}' nao registrada")
        return inst

    def list_all(self) -> list[IntegrationInfo]:
        """Lista para o painel admin com status atual de cada uma."""
        items: list[IntegrationInfo] = []
        for inst in self._entries.values():
            try:
                hc = inst.health_check() or {}
                items.append(IntegrationInfo(
                    name=inst.name,
                    available=bool(hc.get("ok")),
                    detail=str(hc.get("detail", "")),
                    instance=inst,
                ))
            except Exception as exc:  # noqa: BLE001 — health_check NUNCA derruba o admin
                logger.exception("health_check da integracao %s falhou", inst.name)
                items.append(IntegrationInfo(
                    name=inst.name,
                    available=False,
                    detail=f"erro: {exc.__class__.__name__}",
                    instance=inst,
                ))
        return sorted(items, key=lambda i: i.name)

    def reset(self) -> None:
        """Limpa o registry — uso esperado: testes."""
        self._entries.clear()


# Instancia global. O factory popula no boot via `registry.register(...)`.
registry = IntegrationRegistry()
