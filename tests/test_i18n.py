"""Testes do i18n minimo do totem.

Cobre:
  - Catalogo PT/EN: chaves consistentes entre os dois idiomas.
  - `t(key)`: traduz, faz fallback determinístico, devolve a chave se ausente.
  - get_locale/set_locale: validacao + persistencia na sessao.
  - POST /api/locale: 200 com locale conhecido, 400 com desconhecido.
  - Locale persistente entre requests (Trello criterio 3.6).
  - Voice/chat: when locale='en', system prompt instructs reply in English.
"""
from unittest.mock import MagicMock, patch

import pytest
from flask import session

from app.services.i18n import (
    CATALOG, DEFAULT_LOCALE, SUPPORTED_LOCALES, get_locale,
    locale_display_name, set_locale, t,
)


# ════════════════════════════════════════════════════════════════════════════
# Catalogo
# ════════════════════════════════════════════════════════════════════════════

def test_catalogo_tem_idiomas_minimos():
    """PR garante PT e EN. Adicionar idiomas nao quebra esse teste."""
    assert "pt" in CATALOG
    assert "en" in CATALOG


def test_chaves_consistentes_entre_idiomas():
    """Toda chave deve existir em TODOS os idiomas suportados.

    Sem isso, alguns trechos do totem ficariam em outro idioma quando o
    visitante alterna. Falha aqui = traducao incompleta. Generaliza para
    qualquer idioma novo (es, fr, ...) ao inves de fixar PT vs EN.
    """
    base_keys = set(CATALOG[DEFAULT_LOCALE])
    for locale in SUPPORTED_LOCALES:
        loc_keys = set(CATALOG[locale])
        faltando = base_keys - loc_keys
        sobrando = loc_keys - base_keys
        assert not faltando, f"chaves faltando em {locale}: {faltando}"
        assert not sobrando, f"chaves extras em {locale}: {sobrando}"


def test_strings_nao_estao_vazias():
    for locale, table in CATALOG.items():
        for key, value in table.items():
            assert value, f"{locale}.{key} esta vazio"


# ════════════════════════════════════════════════════════════════════════════
# t() / get_locale / set_locale
# ════════════════════════════════════════════════════════════════════════════

def test_t_traduz_em_pt(app):
    with app.test_request_context():
        assert t("nav.home", locale="pt") == "Home"
        assert t("common.yes", locale="pt") == "Sim"


def test_t_traduz_em_en(app):
    with app.test_request_context():
        assert t("common.yes", locale="en") == "Yes"
        assert t("common.no", locale="en") == "No"


def test_t_chave_inexistente_devolve_a_propria_chave(app):
    """Comportamento intencional: chave em falta aparece literal no UI —
    sinal visual obvio em revisao."""
    with app.test_request_context():
        assert t("nada.disso", locale="pt") == "nada.disso"


def test_t_fallback_para_default_quando_chave_so_existe_em_pt(app, monkeypatch):
    """Se uma chave so existe em PT, ao pedir EN cai no PT (nunca em branco)."""
    monkeypatch.setitem(CATALOG, "test", {"so.pt": "valor"})
    monkeypatch.setitem(CATALOG["pt"], "fallback.key", "valor PT")
    with app.test_request_context():
        # Chave existe so em PT — pedindo em "test" cai no DEFAULT (pt).
        assert t("fallback.key", locale="test") == "valor PT"


def test_get_locale_default_quando_sem_sessao(app):
    with app.test_request_context():
        assert get_locale() == DEFAULT_LOCALE


def test_set_locale_persiste_na_sessao(app):
    with app.test_request_context():
        assert set_locale("en") is True
        assert session["_locale"] == "en"
        assert get_locale() == "en"


def test_set_locale_recusa_codigo_desconhecido(app):
    with app.test_request_context():
        assert set_locale("zz") is False
        assert "_locale" not in session


def test_locale_display_name_em_supported():
    for code, label in SUPPORTED_LOCALES.items():
        assert locale_display_name(code) == label


# ════════════════════════════════════════════════════════════════════════════
# POST /api/locale
# ════════════════════════════════════════════════════════════════════════════

def test_endpoint_set_locale_aceita_pt(client):
    r = client.post("/api/locale", json={"locale": "pt"})
    assert r.status_code == 200
    assert r.get_json()["locale"] == "pt"


def test_endpoint_set_locale_aceita_en(client):
    r = client.post("/api/locale", json={"locale": "en"})
    assert r.status_code == 200
    assert r.get_json()["locale"] == "en"


def test_endpoint_set_locale_recusa_desconhecido(client):
    r = client.post("/api/locale", json={"locale": "klingon"})
    assert r.status_code == 400
    body = r.get_json()
    assert "supported" in body
    assert "pt" in body["supported"] and "en" in body["supported"]


def test_endpoint_persiste_locale_entre_requests(client):
    """Trello criterio 3.6: configuracao mantida durante toda a sessao."""
    r1 = client.post("/api/locale", json={"locale": "en"})
    assert r1.status_code == 200
    # Segundo request — verificamos via `t()` injetado num contexto Jinja.
    # A home publica usa o catalogo, mas depende de instituicao. Mais
    # simples: usar a pagina de privacidade que ja existe.
    r2 = client.get("/privacidade")
    # Quando locale=en, o offline banner traduzido aparece.
    assert b"Offline" in r2.data


# ════════════════════════════════════════════════════════════════════════════
# UI: toggle no topbar e i18n na pagina
# ════════════════════════════════════════════════════════════════════════════

def test_topbar_nao_renderiza_seletor_de_idioma(client):
    """Regressao: o seletor de idioma do topbar foi removido em definitivo.
    Toda troca de idioma vive no rodape da Home (.nc-lang-btn / data-lang).
    Se este teste falhar, alguem reintroduziu o componente em base.html —
    revisar a decisao com o time antes de re-adicionar."""
    r = client.get("/privacidade")
    assert r.status_code == 200
    # HTML: nem o container nem os botoes podem voltar ao topbar.
    assert b'class="lang-switch"' not in r.data
    assert b'data-locale=' not in r.data
    assert b'class="lang-btn' not in r.data


def test_home_renderiza_seletor_de_idioma_no_rodape(client):
    """Fonte unica do toggle: rodape da Home (componente .nc-lang com
    bandeiras PT/EN/ES). Garante que a remocao do topbar nao deixou o
    visitante sem caminho para trocar de idioma."""
    r = client.get("/teste/")  # slug seedado pelo conftest
    assert r.status_code == 200
    assert b'class="nc-lang"' in r.data
    assert b'data-lang="pt"' in r.data
    assert b'data-lang="en"' in r.data
    assert b'data-lang="es"' in r.data


# ════════════════════════════════════════════════════════════════════════════
# Voice/chat respeitam o locale
# ════════════════════════════════════════════════════════════════════════════

def test_voice_chat_anexa_instrucao_de_idioma_quando_en(client):
    """Quando locale=en, system prompt deve incluir 'Respond in English'."""
    client.post("/api/locale", json={"locale": "en"})

    # Patch do OpenAI para capturar o system prompt enviado.
    with patch("app.routes.voice._get_client") as fake_get:
        fake_client = MagicMock()
        msg = MagicMock(); msg.content = "Hello!"
        choice = MagicMock(); choice.message = msg
        chat_resp = MagicMock(); chat_resp.choices = [choice]
        fake_client.chat.completions.create.return_value = chat_resp
        fake_get.return_value = fake_client

        r = client.post("/teste/api/chat", json={"message": "hi"})
        assert r.status_code == 200

        # Inspeciona o system prompt enviado para o LLM.
        kwargs = fake_client.chat.completions.create.call_args.kwargs
        messages = kwargs["messages"]
        system = next(m for m in messages if m["role"] == "system")
        assert "English" in system["content"]


def test_voice_chat_anexa_instrucao_de_idioma_quando_es(client):
    """Homologacao Spanish: locale=es injeta 'Respond in Español' no prompt."""
    client.post("/api/locale", json={"locale": "es"})

    with patch("app.routes.voice._get_client") as fake_get:
        fake_client = MagicMock()
        msg = MagicMock(); msg.content = "¡Hola!"
        choice = MagicMock(); choice.message = msg
        chat_resp = MagicMock(); chat_resp.choices = [choice]
        fake_client.chat.completions.create.return_value = chat_resp
        fake_get.return_value = fake_client

        r = client.post("/teste/api/chat", json={"message": "hola"})
        assert r.status_code == 200

        kwargs = fake_client.chat.completions.create.call_args.kwargs
        system = next(m for m in kwargs["messages"] if m["role"] == "system")
        # locale_display_name('es') == 'Español' → tem que aparecer no prompt.
        assert "Español" in system["content"]
        # A trava de idioma agora e' marcada por um bloco delimitado para
        # facilitar grep em logs/depuracao — qualquer locale produz o mesmo
        # delimitador, so o nome do idioma muda.
        assert "LANGUAGE LOCK" in system["content"]
        assert "respond exclusively in" in system["content"]


def test_endpoint_set_locale_aceita_es(client):
    """Homologacao Spanish: /api/locale aceita 'es' e persiste na sessao."""
    r = client.post("/api/locale", json={"locale": "es"})
    assert r.status_code == 200
    assert r.get_json()["locale"] == "es"

    # Persistencia entre requests + render do banner traduzido (Trello 3.6).
    r2 = client.get("/privacidade")
    assert "Sin conexión".encode("utf-8") in r2.data


def test_home_renderiza_botao_espanhol_no_rodape(client):
    """O rodape da Home expoe ES junto de PT/EN (fonte unica de troca)."""
    r = client.get("/teste/")
    assert r.status_code == 200
    assert b'data-lang="es"' in r.data


def test_voice_chat_nao_anexa_instrucao_quando_pt(client):
    """Locale default (pt) NAO deve sujar o prompt — economiza tokens."""
    # Nao seta locale — fica no default 'pt'.
    with patch("app.routes.voice._get_client") as fake_get:
        fake_client = MagicMock()
        msg = MagicMock(); msg.content = "Olá!"
        choice = MagicMock(); choice.message = msg
        chat_resp = MagicMock(); chat_resp.choices = [choice]
        fake_client.chat.completions.create.return_value = chat_resp
        fake_get.return_value = fake_client

        r = client.post("/teste/api/chat", json={"message": "oi"})
        assert r.status_code == 200

        kwargs = fake_client.chat.completions.create.call_args.kwargs
        system = next(m for m in kwargs["messages"] if m["role"] == "system")
        assert "Respond in" not in system["content"]
        assert "English" not in system["content"]
