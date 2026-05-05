"""i18n minimo do totem — catalogo PT/EN com fallback determinístico.

Atende o backlog Trello (Modulo 3 - Acessibilidade e Idiomas [Baixa]):
  3.1 Selecao de idioma antes ou durante o atendimento.
  3.2 Suporte a pelo menos 2 idiomas (PT/EN), expansivel.
  3.6 Configuracao mantida durante toda a sessao.

Por que NAO Flask-Babel?
  Babel adiciona ~3 MB de dependencias e um pipeline de extracao/compilacao
  (.po/.mo) overkill para o volume de strings do totem (algumas dezenas).
  Catalogo Python puro:
    - cabe num arquivo legivel/diff-avel,
    - vai pro git sem build step,
    - permite hot-reload em dev sem `pybabel compile`,
    - facilita o admin re-traducao via UI no futuro.

Como adicionar uma nova string:
  1. Adicione a chave em CATALOG['pt'] e CATALOG['en'].
  2. Use `{{ t('chave') }}` no template ou `t('chave')` no codigo.
  3. Strings ausentes voltam a chave (`missing_key` → 'missing_key') —
     visualmente obvio em revisao.

Como adicionar um novo idioma:
  1. Acrescente um dicionario em CATALOG (ex.: 'es': {...}).
  2. Adicione o codigo em SUPPORTED_LOCALES.
  3. Pronto — `set_locale('es')` ja funciona.
"""
from __future__ import annotations

from flask import session

# Codigo do idioma → nome legivel para a IA (system prompt) e UI.
SUPPORTED_LOCALES: dict[str, str] = {
    "pt": "Português (Brasil)",
    "en": "English",
}
DEFAULT_LOCALE = "pt"
SESSION_KEY = "_locale"


# ── Catalogo de strings ────────────────────────────────────────────────────────
# Chaves usam ponto como separador de namespace (nav.home, voice.consent, ...).
# Novas chaves: prefira textos curtos e atomicos para reuso entre paginas.

CATALOG: dict[str, dict[str, str]] = {
    "pt": {
        "nav.home":          "Home",
        "nav.animals":       "Animais",
        "nav.stores":        "Lojas",
        "nav.products":      "Produtos",
        "nav.map":           "Mapa",
        "nav.schedule":      "Programação",
        "nav.assistant":     "Assistente",
        "nav.quiz":          "Quiz",

        "common.back":       "Voltar",
        "common.yes":        "Sim",
        "common.no":         "Não",
        "common.privacy":    "Privacidade",
        "common.fullscreen": "Tela cheia",
        "common.language":   "Idioma",

        "voice.consent_title":  "Antes de começar",
        "voice.consent_text":   "Suas perguntas podem ser gravadas para melhorar o atendimento. Nenhum dado pessoal é exigido.",
        "voice.consent_accept": "Aceito e quero começar",
        "voice.placeholder":    "Toque no microfone para falar comigo",

        "quiz.intro_title":     "Quer testar seu conhecimento?",
        "quiz.intro_subtitle":  "Perguntas rápidas e curiosidades.",
        "quiz.start":           "SIM",
        "quiz.correct":         "Correto!",
        "quiz.incorrect":       "Não foi dessa vez",
        "quiz.thanks":          "Obrigado por participar!",

        "offline.banner":       "Sem conexão — algumas funções estarão indisponíveis.",
        "preview.banner":       "PREVIEW — alterações ainda não salvas. Feche esta aba para descartar.",
    },
    "en": {
        "nav.home":          "Home",
        "nav.animals":       "Animals",
        "nav.stores":        "Stores",
        "nav.products":      "Products",
        "nav.map":           "Map",
        "nav.schedule":      "Schedule",
        "nav.assistant":     "Assistant",
        "nav.quiz":          "Quiz",

        "common.back":       "Back",
        "common.yes":        "Yes",
        "common.no":         "No",
        "common.privacy":    "Privacy",
        "common.fullscreen": "Fullscreen",
        "common.language":   "Language",

        "voice.consent_title":  "Before we start",
        "voice.consent_text":   "Your questions may be recorded to improve service. No personal data is required.",
        "voice.consent_accept": "I agree, let's start",
        "voice.placeholder":    "Tap the microphone to talk to me",

        "quiz.intro_title":     "Want to test your knowledge?",
        "quiz.intro_subtitle":  "Quick questions and fun facts.",
        "quiz.start":           "YES",
        "quiz.correct":         "Correct!",
        "quiz.incorrect":       "Not this time",
        "quiz.thanks":          "Thanks for playing!",

        "offline.banner":       "Offline — some features will be unavailable.",
        "preview.banner":       "PREVIEW — changes not saved. Close this tab to discard.",
    },
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def get_locale() -> str:
    """Locale atual da sessao, com fallback ao default e validacao defensiva."""
    locale = session.get(SESSION_KEY) if session else None
    if locale not in SUPPORTED_LOCALES:
        return DEFAULT_LOCALE
    return locale


def set_locale(code: str) -> bool:
    """Persiste o locale na sessao se conhecido. Retorna True/False."""
    if code not in SUPPORTED_LOCALES:
        return False
    session[SESSION_KEY] = code
    session.permanent = True  # mantem na sessao (Trello 3.6)
    return True


def t(key: str, locale: str | None = None) -> str:
    """Traduz `key` para o locale (default: o da sessao).

    Estrategia de fallback:
      1. CATALOG[locale][key] se existir.
      2. CATALOG[DEFAULT_LOCALE][key] se existir.
      3. A propria `key` — sinaliza visualmente que falta tradução.
    """
    if locale is None:
        locale = get_locale()
    table = CATALOG.get(locale, {})
    if key in table:
        return table[key]
    fallback_table = CATALOG.get(DEFAULT_LOCALE, {})
    return fallback_table.get(key, key)


def locale_display_name(code: str | None = None) -> str:
    """Nome legivel do idioma (para system prompts e UI)."""
    if code is None:
        code = get_locale()
    return SUPPORTED_LOCALES.get(code, SUPPORTED_LOCALES[DEFAULT_LOCALE])
