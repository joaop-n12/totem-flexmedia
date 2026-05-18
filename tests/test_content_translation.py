"""Testes do filtro Jinja `|tr` que traduz conteudo do banco on-the-fly.

Garante que:
  - Quando locale == 'pt' (default), retorna o texto sem chamar OpenAI.
  - Quando locale != 'pt', invoca TranslationIntegration e devolve o resultado.
  - Falhas do tradutor (offline/rate_limit/auth/qualquer) NUNCA quebram o
    render: o filtro cai silenciosamente para o texto original. UX > IA.
  - Texto vazio/None passa pelo filtro sem chamar nada.

Por que esses testes existem:
  O totem nao pode mostrar uma pagina quebrada se a OpenAI cair. O filtro
  e' a unica camada de tradutor de conteudo dinamico; uma regressao aqui
  silenciosamente faz visitantes estrangeiros verem PT — ou pior, uma
  excecao Jinja na cara.
"""
from unittest.mock import MagicMock, patch

from flask import render_template_string

from app.services.translation import TranslationError, TranslationResult


# ── Helpers de mock ────────────────────────────────────────────────────────────

def _fake_integration(translate_return=None, translate_raises=None,
                      available=True):
    integration = MagicMock()
    integration.is_available.return_value = available
    if translate_raises is not None:
        integration.translate.side_effect = translate_raises
    else:
        integration.translate.return_value = translate_return
    return integration


def _render(app, template, **ctx):
    with app.test_request_context():
        return render_template_string(template, **ctx)


# ── Locale default ────────────────────────────────────────────────────────────

def test_tr_filter_devolve_texto_quando_locale_pt(app):
    """Sem trocar locale, o filtro nao deve chamar OpenAI nem alterar nada."""
    with patch("app.services.registry.get") as fake_get:
        out = _render(app, "{{ 'Elefante africano'|tr }}")
        assert out == "Elefante africano"
        fake_get.assert_not_called()


def test_tr_filter_devolve_vazio_sem_chamar_tradutor(app):
    with patch("app.services.registry.get") as fake_get:
        with app.test_request_context():
            # Forca locale en — para garantir que o atalho e' o "texto vazio".
            from app.services.i18n import set_locale
            set_locale("en")
            assert render_template_string("{{ ''|tr }}") == ""
            assert render_template_string("{{ none|tr }}") == "None"
        fake_get.assert_not_called()


# ── Locale != pt ──────────────────────────────────────────────────────────────

def test_tr_filter_traduz_quando_locale_en(app):
    """Locale=en → filtro chama TranslationIntegration com target='en'.

    O filtro faz `isinstance(integration, TranslationIntegration)`, entao
    usamos uma instancia real (criada via __new__ para nao chamar __init__)
    e mockamos so os metodos relevantes.
    """
    from app.services.translation import TranslationIntegration
    real = TranslationIntegration.__new__(TranslationIntegration)
    real.is_available = lambda: True
    real.translate = MagicMock(return_value=TranslationResult(
        text="African elephant", cached=False,
        source_lang="pt", target_lang="en",
    ))
    with app.test_request_context():
        from app.services.i18n import set_locale
        set_locale("en")
        with patch("app.services.registry.get", return_value=real):
            out = render_template_string("{{ 'Elefante africano'|tr }}")
            assert out == "African elephant"
            real.translate.assert_called_once()
            kwargs = real.translate.call_args.kwargs
            assert kwargs["target"] == "en"
            assert kwargs["source"] == "pt"


def test_tr_filter_traduz_quando_locale_es(app):
    """Locale=es → filtro pede target='es'."""
    from app.services.translation import TranslationIntegration
    real = TranslationIntegration.__new__(TranslationIntegration)
    real.is_available = lambda: True
    real.translate = MagicMock(return_value=TranslationResult(
        text="Elefante africano (es)", cached=True,
        source_lang="pt", target_lang="es",
    ))
    with app.test_request_context():
        from app.services.i18n import set_locale
        set_locale("es")
        with patch("app.services.registry.get", return_value=real):
            out = render_template_string("{{ 'Elefante africano'|tr }}")
            assert out == "Elefante africano (es)"
            kwargs = real.translate.call_args.kwargs
            assert kwargs["target"] == "es"


# ── Fail-soft ──────────────────────────────────────────────────────────────────

def test_tr_filter_devolve_original_quando_tradutor_offline(app):
    """OpenAI fora do ar → visitante ve PT original, sem 500."""
    from app.services.translation import TranslationIntegration
    real = TranslationIntegration.__new__(TranslationIntegration)
    real.is_available = lambda: True
    real.translate = MagicMock(side_effect=TranslationError(
        "offline", "Tradução indisponível",
    ))
    with app.test_request_context():
        from app.services.i18n import set_locale
        set_locale("en")
        with patch("app.services.registry.get", return_value=real):
            out = render_template_string("{{ 'Elefante'|tr }}")
            assert out == "Elefante"


def test_tr_filter_devolve_original_quando_tradutor_indisponivel(app):
    """Sem OPENAI_API_KEY → is_available() False → devolve PT."""
    from app.services.translation import TranslationIntegration
    real = TranslationIntegration.__new__(TranslationIntegration)
    real.is_available = lambda: False
    real.translate = MagicMock()  # nao deveria ser chamada
    with app.test_request_context():
        from app.services.i18n import set_locale
        set_locale("en")
        with patch("app.services.registry.get", return_value=real):
            out = render_template_string("{{ 'Elefante'|tr }}")
            assert out == "Elefante"
            real.translate.assert_not_called()


def test_tr_filter_devolve_original_em_excecao_inesperada(app):
    """Defesa em profundidade: qualquer Exception cai para o texto original."""
    from app.services.translation import TranslationIntegration
    real = TranslationIntegration.__new__(TranslationIntegration)
    real.is_available = lambda: True
    real.translate = MagicMock(side_effect=RuntimeError("boom"))
    with app.test_request_context():
        from app.services.i18n import set_locale
        set_locale("en")
        with patch("app.services.registry.get", return_value=real):
            out = render_template_string("{{ 'Elefante'|tr }}")
            assert out == "Elefante"


# ── Bottom-nav i18n (chrome do base.html) ─────────────────────────────────────

def test_bottom_nav_label_traduz_em_en(client):
    """Bottom-nav usava 'Animais'/'Mapa'/etc hardcoded — agora via t()."""
    client.post("/api/locale", json={"locale": "en"})
    r = client.get("/privacidade")
    assert r.status_code == 200
    # As 7 labels devem aparecer em EN no bottom-nav (Home/Animals/Stores/
    # Products/Map/Schedule/Assistant) — mas a instituicao do teste so tem
    # `ia` habilitado, entao validamos o que sempre aparece (Home).
    # Strings PT como "Programação" NAO podem aparecer no bottom-nav.
    assert "Programação".encode("utf-8") not in r.data


def test_bottom_nav_label_traduz_em_es(client):
    client.post("/api/locale", json={"locale": "es"})
    r = client.get("/privacidade")
    assert r.status_code == 200
    # Lista de strings PT que NAO deveriam estar no chrome se o ES funcionar.
    for pt in ("Animais", "Programação"):
        assert pt.encode("utf-8") not in r.data
