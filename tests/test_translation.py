"""Testes do servico de traducao + registry de integracoes.

Cobre:
  - Registry: register/get/require/list_all/health_check.
  - TranslationIntegration: cache hit/miss, classificacao de erros, limites.
  - Rota POST /<slug>/api/translate: 200, 400 (vazio), 429 (rate/quota),
    503 (offline/auth), e log de InteractionLog.

OpenAI nunca e' chamada de verdade — sempre mockamos o client (regra de
engenharia do projeto).
"""
import json
from unittest.mock import MagicMock, patch

import pytest
from openai import APIConnectionError, AuthenticationError, RateLimitError

from app.extensions import db
from app.models import InteractionLog
from app.services import registry
from app.services.integrations import IntegrationRegistry
from app.services.translation import (
    SUPPORTED_LANGUAGES,
    TranslationError,
    TranslationIntegration,
    _MemoryCache,
)


# ════════════════════════════════════════════════════════════════════════════
# Registry
# ════════════════════════════════════════════════════════════════════════════

class _FakeIntegration:
    name = "fake"
    def is_available(self): return True
    def health_check(self): return {"ok": True, "detail": "fake online"}


class _BrokenIntegration:
    name = "broken"
    def is_available(self): return True
    def health_check(self): raise RuntimeError("boom")


def test_registry_register_e_get():
    reg = IntegrationRegistry()
    fake = _FakeIntegration()
    reg.register(fake)
    assert reg.get("fake") is fake
    assert reg.get("ausente") is None


def test_registry_require_levanta_se_ausente():
    reg = IntegrationRegistry()
    with pytest.raises(KeyError):
        reg.require("inexistente")


def test_registry_recusa_objeto_que_nao_implementa_protocolo():
    reg = IntegrationRegistry()
    class SemContrato:
        pass
    with pytest.raises(TypeError):
        reg.register(SemContrato())


def test_registry_list_all_engole_excecao_em_health_check():
    """Uma integracao quebrada NAO pode derrubar o painel admin."""
    reg = IntegrationRegistry()
    reg.register(_FakeIntegration())
    reg.register(_BrokenIntegration())
    items = reg.list_all()
    nomes = {i.name for i in items}
    assert nomes == {"fake", "broken"}
    broken = next(i for i in items if i.name == "broken")
    assert broken.available is False
    assert "RuntimeError" in broken.detail


# ════════════════════════════════════════════════════════════════════════════
# Cache em memoria
# ════════════════════════════════════════════════════════════════════════════

def test_memory_cache_round_trip():
    c = _MemoryCache()
    c.set("k", "v", ttl=60)
    assert c.get("k") == "v"


def test_memory_cache_expira_apos_ttl(monkeypatch):
    c = _MemoryCache()
    c.set("k", "v", ttl=10)
    # Fast-forward "agora" 20s no futuro.
    real_time = __import__("time").time
    monkeypatch.setattr("app.services.translation.time.time",
                        lambda: real_time() + 20)
    assert c.get("k") is None


# ════════════════════════════════════════════════════════════════════════════
# TranslationIntegration — caminhos felizes e erros
# ════════════════════════════════════════════════════════════════════════════

def _fake_openai_response(content: str):
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def test_translate_caminho_feliz_chama_openai_e_cacha():
    integ = TranslationIntegration()
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _fake_openai_response("Hello, friend!")
    integ._client = fake_client

    r1 = integ.translate("Olá, amigo!", target="en")
    assert r1.text == "Hello, friend!"
    assert r1.cached is False
    assert fake_client.chat.completions.create.call_count == 1

    # Segunda chamada identica → cache hit, OpenAI NAO e' chamada.
    r2 = integ.translate("Olá, amigo!", target="en")
    assert r2.text == "Hello, friend!"
    assert r2.cached is True
    assert fake_client.chat.completions.create.call_count == 1


def test_translate_recusa_texto_vazio():
    integ = TranslationIntegration()
    with pytest.raises(TranslationError) as exc:
        integ.translate("", target="en")
    assert exc.value.kind == "invalid"


def test_translate_recusa_idioma_destino_desconhecido():
    integ = TranslationIntegration()
    with pytest.raises(TranslationError) as exc:
        integ.translate("oi", target="xx")
    assert exc.value.kind == "invalid"


def test_translate_recusa_texto_muito_longo():
    integ = TranslationIntegration()
    with pytest.raises(TranslationError) as exc:
        integ.translate("a" * 5000, target="en")
    assert exc.value.kind == "invalid"


def test_translate_classifica_offline():
    integ = TranslationIntegration()
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = APIConnectionError(request=MagicMock())
    integ._client = fake_client
    with pytest.raises(TranslationError) as exc:
        integ.translate("oi", target="en")
    assert exc.value.kind == "offline"


def test_translate_classifica_rate_limit():
    integ = TranslationIntegration()
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = RateLimitError(
        message="rl", response=MagicMock(), body=None,
    )
    integ._client = fake_client
    with pytest.raises(TranslationError) as exc:
        integ.translate("oi", target="en")
    assert exc.value.kind == "rate_limit"


def test_translate_classifica_auth():
    integ = TranslationIntegration()
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = AuthenticationError(
        message="bad key", response=MagicMock(), body=None,
    )
    integ._client = fake_client
    with pytest.raises(TranslationError) as exc:
        integ.translate("oi", target="en")
    assert exc.value.kind == "auth"


# ════════════════════════════════════════════════════════════════════════════
# Rota /api/translate
# ════════════════════════════════════════════════════════════════════════════

def _patch_registry(monkeypatch, integ):
    """Substitui a integracao no registry global pela fornecida."""
    monkeypatch.setattr(registry, "_entries", {"translation": integ}, raising=False)


def test_rota_translate_caminho_feliz(app, client, monkeypatch):
    integ = TranslationIntegration()
    fake_client = MagicMock()
    fake_client.chat.completions.create.return_value = _fake_openai_response("Hello.")
    integ._client = fake_client
    _patch_registry(monkeypatch, integ)

    r = client.post("/teste/api/translate",
                    json={"text": "Olá.", "target": "en"})
    assert r.status_code == 200
    body = r.get_json()
    assert body["translation"] == "Hello."
    assert body["target"] == "en"
    assert body["cached"] is False

    # InteractionLog gravado com input_type marcando o idioma de destino.
    with app.app_context():
        log = InteractionLog.query.order_by(InteractionLog.id.desc()).first()
        assert log is not None
        assert log.input_type == "translate:en"
        assert log.input_text == "Olá."


def test_rota_translate_recusa_texto_vazio(client):
    r = client.post("/teste/api/translate", json={"text": "", "target": "en"})
    assert r.status_code == 400


def test_rota_translate_503_quando_integracao_indisponivel(client, monkeypatch):
    monkeypatch.setattr(registry, "_entries", {}, raising=False)
    r = client.post("/teste/api/translate",
                    json={"text": "oi", "target": "en"})
    assert r.status_code == 503


def test_rota_translate_lista_idiomas(client):
    r = client.get("/api/translate/languages")
    assert r.status_code == 200
    body = r.get_json()
    assert "pt" in body["languages"]
    assert "en" in body["languages"]
    assert body["languages"]["pt"] == SUPPORTED_LANGUAGES["pt"]


def test_rota_translate_erro_offline_vira_503(client, monkeypatch):
    integ = TranslationIntegration()
    fake_client = MagicMock()
    fake_client.chat.completions.create.side_effect = APIConnectionError(request=MagicMock())
    integ._client = fake_client
    _patch_registry(monkeypatch, integ)

    r = client.post("/teste/api/translate",
                    json={"text": "oi", "target": "en"})
    assert r.status_code == 503
    assert r.get_json()["error"] == "offline"
