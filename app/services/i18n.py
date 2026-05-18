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
    "es": "Español",
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

        "home.status":          "Sistema Online · Inteligência Ativa",
        "home.welcome":         "Bem-vindo à",
        "home.subtitle":        "Escolha uma opção para iniciar o atendimento",
        "home.animals_desc":    "Explore as espécies",
        "home.map_desc":        "Encontre as atrações",
        "home.schedule_full":   "Programação e Alimentação",
        "home.schedule_desc":   "Horários e atividades do dia",
        "home.assistant_full":  "Assistente IA",
        "home.assistant_desc":  "Pergunte por voz ou texto",
        "home.a11y":            "Acessibilidade",

        "common.search_btn":       "Buscar",
        "common.view_all":         "Ver todos",
        "common.clear_filters":    "Limpar filtros",
        "common.touch_explore":    "Toque para explorar",
        "common.no_animal_found":  "Nenhum animal encontrado.",
        "common.animal_singular":  "animal",
        "common.animal_plural":    "animais",
        "common.today":            "Hoje",

        "zoo.species.eyebrow":     "Catálogo de espécies",
        "zoo.species.title":       "Conheça os animais",
        "zoo.species.desc":        "Escolha uma espécie para descobrir os animais que vivem no parque.",
        "zoo.species.view_catalog":"📋 Ver Catálogo Completo",

        "zoo.list.eyebrow":        "Espécie",
        "zoo.list.desc":           "Toque em um animal para ver detalhes, habitat e curiosidades.",
        "zoo.list.search_ph":      "Pesquisar animal...",

        "zoo.detail.fallback":     "Animal",
        "zoo.detail.habitat":      "Habitat",
        "zoo.detail.area":         "Área",
        "zoo.detail.food":         "Alimentação",
        "zoo.detail.curiosities":  "Curiosidades",
        "zoo.detail.conservation": "Conservação",

        "zoo.catalog.eyebrow":     "Catálogo completo",
        "zoo.catalog.title":       "Todos os animais",
        "zoo.catalog.desc":        "Use a busca e os filtros para encontrar.",
        "zoo.catalog.species":     "Espécie",
        "zoo.catalog.habitat":     "Habitat",
        "zoo.catalog.all":         "Todos",
        "zoo.catalog.search_ph":   "Buscar animal…",
        "zoo.catalog.search_aria": "Buscar animal",
        "zoo.catalog.count_of":    "de",
        "zoo.catalog.empty_title": "Nenhum animal encontrado",
        "zoo.catalog.empty_desc":  "Tente outros termos ou remova algum filtro.",

        "map.eyebrow":             "Mapa interativo",
        "map.title":                "Onde estamos no parque",
        "map.desc":                 "Toque nos pontos para explorar cada área. Use os botões para dar zoom ou arraste com o dedo.",
        "map.zoom_in":              "＋ Zoom",
        "map.zoom_out":             "－ Zoom",
        "map.reset":                "↺ Resetar",

        "schedule.eyebrow":        "Hoje no parque",
        "schedule.title":          "Programação e Alimentação",
        "schedule.desc":           "Horários das atividades especiais, apresentações e momentos de alimentação dos animais.",
        "schedule.feed_title":     "Alimentação dos animais",
        "schedule.activities":     "Atividades e apresentações",
        "schedule.empty_title":    "Nenhuma atividade programada",
        "schedule.empty_desc":     "Volte mais tarde para conferir o cronograma do dia.",
        "schedule.food_cta_title": "Procurando onde comer?",
        "schedule.food_cta_desc":  "Veja todos os restaurantes, lanchonetes e quiosques disponíveis no parque.",
        "schedule.food_cta_btn":   "🍽️ Ver pontos de alimentação",

        "food.eyebrow":            "Alimentação",
        "food.title_prefix":       "Onde comer no",
        "food.desc":               "Restaurantes, lanchonetes e quiosques distribuídos pelo parque para você não perder nenhum momento do passeio.",
        "food.tips_title":         "Dicas para sua refeição",
        "food.feed_title":         "Alimentação dos animais",
        "food.feed_desc":          "Você sabia? O zoológico também tem horários especiais de alimentação dos animais, abertos ao público. É uma oportunidade única de ver os tratadores em ação e aprender sobre a dieta de cada espécie.",
        "food.feed_cta":           "Ver horários de alimentação dos animais",
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

        "home.status":          "System Online · Intelligence Active",
        "home.welcome":         "Welcome to",
        "home.subtitle":        "Choose an option to start your visit",
        "home.animals_desc":    "Browse the species",
        "home.map_desc":        "Find the attractions",
        "home.schedule_full":   "Schedule & Feeding",
        "home.schedule_desc":   "Today's times and activities",
        "home.assistant_full":  "AI Assistant",
        "home.assistant_desc":  "Ask by voice or text",
        "home.a11y":            "Accessibility",

        "common.search_btn":       "Search",
        "common.view_all":         "View all",
        "common.clear_filters":    "Clear filters",
        "common.touch_explore":    "Tap to explore",
        "common.no_animal_found":  "No animal found.",
        "common.animal_singular":  "animal",
        "common.animal_plural":    "animals",
        "common.today":            "Today",

        "zoo.species.eyebrow":     "Species catalog",
        "zoo.species.title":       "Meet the animals",
        "zoo.species.desc":        "Choose a species to discover the animals living in the park.",
        "zoo.species.view_catalog":"📋 View Full Catalog",

        "zoo.list.eyebrow":        "Species",
        "zoo.list.desc":           "Tap an animal to see details, habitat, and fun facts.",
        "zoo.list.search_ph":      "Search animal...",

        "zoo.detail.fallback":     "Animal",
        "zoo.detail.habitat":      "Habitat",
        "zoo.detail.area":         "Area",
        "zoo.detail.food":         "Diet",
        "zoo.detail.curiosities":  "Fun facts",
        "zoo.detail.conservation": "Conservation",

        "zoo.catalog.eyebrow":     "Full catalog",
        "zoo.catalog.title":       "All animals",
        "zoo.catalog.desc":        "Use search and filters to find them.",
        "zoo.catalog.species":     "Species",
        "zoo.catalog.habitat":     "Habitat",
        "zoo.catalog.all":         "All",
        "zoo.catalog.search_ph":   "Search animal…",
        "zoo.catalog.search_aria": "Search animal",
        "zoo.catalog.count_of":    "of",
        "zoo.catalog.empty_title": "No animal found",
        "zoo.catalog.empty_desc":  "Try other terms or remove a filter.",

        "map.eyebrow":             "Interactive map",
        "map.title":                "Where we are in the park",
        "map.desc":                 "Tap the dots to explore each area. Use the buttons to zoom or drag with your finger.",
        "map.zoom_in":              "＋ Zoom",
        "map.zoom_out":             "－ Zoom",
        "map.reset":                "↺ Reset",

        "schedule.eyebrow":        "Today at the park",
        "schedule.title":          "Schedule & Feeding",
        "schedule.desc":           "Times for special activities, shows, and animal feeding moments.",
        "schedule.feed_title":     "Animal feeding",
        "schedule.activities":     "Activities and shows",
        "schedule.empty_title":    "No activities scheduled",
        "schedule.empty_desc":     "Check back later for today's schedule.",
        "schedule.food_cta_title": "Looking for somewhere to eat?",
        "schedule.food_cta_desc":  "See all restaurants, snack bars, and kiosks available in the park.",
        "schedule.food_cta_btn":   "🍽️ See food spots",

        "food.eyebrow":            "Dining",
        "food.title_prefix":       "Where to eat at",
        "food.desc":               "Restaurants, snack bars, and kiosks throughout the park so you don't miss a moment of your visit.",
        "food.tips_title":         "Tips for your meal",
        "food.feed_title":         "Animal feeding",
        "food.feed_desc":          "Did you know? The zoo also has special public animal feeding times. It's a unique opportunity to watch keepers in action and learn about each species' diet.",
        "food.feed_cta":           "See animal feeding times",
    },
    "es": {
        "nav.home":          "Inicio",
        "nav.animals":       "Animales",
        "nav.stores":        "Tiendas",
        "nav.products":      "Productos",
        "nav.map":           "Mapa",
        "nav.schedule":      "Programación",
        "nav.assistant":     "Asistente",
        "nav.quiz":          "Quiz",

        "common.back":       "Volver",
        "common.yes":        "Sí",
        "common.no":         "No",
        "common.privacy":    "Privacidad",
        "common.fullscreen": "Pantalla completa",
        "common.language":   "Idioma",

        "voice.consent_title":  "Antes de empezar",
        "voice.consent_text":   "Sus preguntas pueden ser grabadas para mejorar el servicio. No se requieren datos personales.",
        "voice.consent_accept": "Acepto y quiero empezar",
        "voice.placeholder":    "Toque el micrófono para hablar conmigo",

        "quiz.intro_title":     "¿Quiere poner a prueba sus conocimientos?",
        "quiz.intro_subtitle":  "Preguntas rápidas y curiosidades.",
        "quiz.start":           "SÍ",
        "quiz.correct":         "¡Correcto!",
        "quiz.incorrect":       "Esta vez no",
        "quiz.thanks":          "¡Gracias por participar!",

        "offline.banner":       "Sin conexión — algunas funciones no estarán disponibles.",
        "preview.banner":       "VISTA PREVIA — cambios no guardados. Cierre esta pestaña para descartar.",

        "home.status":          "Sistema En Línea · Inteligencia Activa",
        "home.welcome":         "Bienvenido a",
        "home.subtitle":        "Elija una opción para iniciar la atención",
        "home.animals_desc":    "Explore las especies",
        "home.map_desc":        "Encuentre las atracciones",
        "home.schedule_full":   "Programación y Alimentación",
        "home.schedule_desc":   "Horarios y actividades del día",
        "home.assistant_full":  "Asistente IA",
        "home.assistant_desc":  "Pregunte por voz o texto",
        "home.a11y":            "Accesibilidad",

        "common.search_btn":       "Buscar",
        "common.view_all":         "Ver todos",
        "common.clear_filters":    "Limpiar filtros",
        "common.touch_explore":    "Toque para explorar",
        "common.no_animal_found":  "No se encontró ningún animal.",
        "common.animal_singular":  "animal",
        "common.animal_plural":    "animales",
        "common.today":            "Hoy",

        "zoo.species.eyebrow":     "Catálogo de especies",
        "zoo.species.title":       "Conozca los animales",
        "zoo.species.desc":        "Elija una especie para descubrir los animales que viven en el parque.",
        "zoo.species.view_catalog":"📋 Ver Catálogo Completo",

        "zoo.list.eyebrow":        "Especie",
        "zoo.list.desc":           "Toque un animal para ver detalles, hábitat y curiosidades.",
        "zoo.list.search_ph":      "Buscar animal...",

        "zoo.detail.fallback":     "Animal",
        "zoo.detail.habitat":      "Hábitat",
        "zoo.detail.area":         "Área",
        "zoo.detail.food":         "Alimentación",
        "zoo.detail.curiosities":  "Curiosidades",
        "zoo.detail.conservation": "Conservación",

        "zoo.catalog.eyebrow":     "Catálogo completo",
        "zoo.catalog.title":       "Todos los animales",
        "zoo.catalog.desc":        "Use la búsqueda y los filtros para encontrarlos.",
        "zoo.catalog.species":     "Especie",
        "zoo.catalog.habitat":     "Hábitat",
        "zoo.catalog.all":         "Todos",
        "zoo.catalog.search_ph":   "Buscar animal…",
        "zoo.catalog.search_aria": "Buscar animal",
        "zoo.catalog.count_of":    "de",
        "zoo.catalog.empty_title": "No se encontró ningún animal",
        "zoo.catalog.empty_desc":  "Pruebe otros términos o quite algún filtro.",

        "map.eyebrow":             "Mapa interactivo",
        "map.title":                "Dónde estamos en el parque",
        "map.desc":                 "Toque los puntos para explorar cada área. Use los botones para hacer zoom o arrastre con el dedo.",
        "map.zoom_in":              "＋ Zoom",
        "map.zoom_out":             "－ Zoom",
        "map.reset":                "↺ Restablecer",

        "schedule.eyebrow":        "Hoy en el parque",
        "schedule.title":          "Programación y Alimentación",
        "schedule.desc":           "Horarios de actividades especiales, presentaciones y momentos de alimentación de los animales.",
        "schedule.feed_title":     "Alimentación de los animales",
        "schedule.activities":     "Actividades y presentaciones",
        "schedule.empty_title":    "No hay actividades programadas",
        "schedule.empty_desc":     "Vuelva más tarde para ver el cronograma del día.",
        "schedule.food_cta_title": "¿Buscando dónde comer?",
        "schedule.food_cta_desc":  "Vea todos los restaurantes, cafeterías y quioscos disponibles en el parque.",
        "schedule.food_cta_btn":   "🍽️ Ver puntos de alimentación",

        "food.eyebrow":            "Alimentación",
        "food.title_prefix":       "Dónde comer en",
        "food.desc":               "Restaurantes, cafeterías y quioscos distribuidos por el parque para que no se pierda ningún momento del paseo.",
        "food.tips_title":         "Consejos para su comida",
        "food.feed_title":         "Alimentación de los animales",
        "food.feed_desc":          "¿Sabía? El zoológico también tiene horarios especiales de alimentación de los animales, abiertos al público. Es una oportunidad única de ver a los cuidadores en acción y aprender sobre la dieta de cada especie.",
        "food.feed_cta":           "Ver horarios de alimentación de los animales",
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
