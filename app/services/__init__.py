"""Servicos de aplicacao plugaveis.

Cada modulo aqui implementa uma "capacidade" que pode ser ligada/desligada
sem mexer no core: traducao, OCR, analytics, etc. Todos sao registrados
no `IntegrationRegistry` e ficam disponiveis para qualquer rota/UI.

A arquitetura permite atender o requisito do Trello (epico Produto, US2:
"suporte a APIs de tradução, reconhecimento de imagem e analytics") sem
acoplar essas APIs ao codigo principal.
"""
from .integrations import IntegrationRegistry, registry

__all__ = ["IntegrationRegistry", "registry"]
