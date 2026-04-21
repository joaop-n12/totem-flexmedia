app/
├── __init__.py          # Application factory (create_app) + CLI: seed, init-db, purge-logs
├── extensions.py        # db, migrate, login_manager, limiter
├── helpers.py           # slugify, CSRF, decoradores auth, build_ai_context, save_upload
├── seed.py              # Seed inicial: módulos, zoo demo, super_admin
├── models/
│   ├── institution.py   # Institution (+ daily_ai_quota, ai_calls_today, ai_quota_exceeded), Module, InstitutionModule
│   ├── content.py       # Animal, Event, Store, Product, FAQ, MapArea
│   ├── log.py           # InteractionLog (retenção via flask purge-logs)
│   └── user.py          # User, AuthLog
└── routes/
    ├── core.py          # Totem público: home, mapa, programação, alimentação, /sw.js, /offline, /privacidade
    ├── zoo.py           # Totem: animais
    ├── shopping.py      # Totem: lojas
    ├── pharmacy.py      # Totem: produtos
    ├── voice.py         # IA: /api/voice, /api/chat (rate-limit + quota por tenant + erros OpenAI tratados)
    ├── admin_auth.py    # /admin/login, /admin/logout
    ├── admin_platform.py    # /admin/platform/* (super_admin)
    └── admin_institution.py # /admin/institutions/<iid>/* (client_admin)

templates/
├── base.html                # Layout público (banner offline, link privacidade, registro do SW)
├── offline.html             # Fallback exibido pelo service worker sem rede
├── privacidade.html         # Aviso LGPD (coleta, OpenAI, retenção, direitos)
├── selector.html
├── 403.html / 404.html / 500.html
├── core/                    # home, mapa, programacao, alimentacao
├── modules/
├── voice/
│   └── index.html           # Assistente (modal de consentimento LGPD + microfone + chat)
└── admin/
    ├── base.html            # Layout do painel (role-aware, noindex, noopener)
    ├── login.html
    ├── forgot_password.html # Placeholder v1
    ├── platform/            # Painel de plataforma (super_admin)
    │   ├── dashboard.html
    │   ├── institution_list.html
    │   ├── institution_form.html  # Inclui campo daily_ai_quota + contador do dia
    │   ├── user_list.html
    │   ├── user_form.html
    │   └── log_list.html
    └── institution/         # Painel de instituição (client_admin)
        ├── dashboard.html
        ├── content_animals.html / animal_form.html
        ├── content_events.html  / event_form.html
        ├── content_stores.html  / store_form.html
        ├── content_products.html / product_form.html
        ├── faq_list.html        / faq_form.html
        └── log_list.html

static/
├── css/style.css
├── js/sw.js                 # Service worker (cache estáticos, fallback offline)
├── images/
└── uploads/                 # Logos e imagens de conteúdo (por instituição)

tests/
├── conftest.py              # Fixture: app "testing", SQLite em memória, instituição seed
├── test_smoke.py            # Rotas públicas (home, selector, privacidade, offline, /sw.js, IA, admin login)
└── test_voice_api.py        # /api/chat e /api/voice com OpenAI mockada (quota, offline, feliz)

deploy/
├── backup.sh                # Backup datado SQLite/Postgres + retenção 14
├── install_production.sh    # Instalador prod: Nginx + Gunicorn + systemd + SSL + cron
├── nginx.conf.template
└── totem-flexmedia.service

docs/
└── OPERACAO.md              # Manual de operação (Pi 3): instalação, troca de chaves,
                             #   restauração de backup, adicionar instituição

data/
├── animais.json             # Seed zoo demo
└── programacao.json         # Seed eventos demo

install_totem.sh             # Instalador kiosk: systemd auto-restart, Chromium fullscreen,
                             #   watchdog, unclutter, autostart LXDE/GNOME
wsgi.py                      # Entrypoint de produção (Gunicorn)
run.py                       # Entrypoint de desenvolvimento (flask run)
.env.example                 # Template de variáveis (SECRET_KEY, OPENAI_API_KEY, SUPERADMIN_*,
                             #   DATABASE_URL opcional, INTERACTION_LOG_RETENTION_DAYS)
config.py                    # Config / ProductionConfig / TestingConfig
                             #   + INTERACTION_LOG_RETENTION_DAYS (LGPD, default 90)
pytest.ini
requirements.txt
requirements-dev.txt         # pytest + pytest-cov

## Regras de engenharia
- Tudo em pt-BR (comentários, variáveis, mensagens).
- Nunca chamar OpenAI em testes — sempre mockar via unittest.mock.
- Toda nova coluna em model precisa de migration (flask db migrate / upgrade).
- Erros da OpenAI diferenciados em voice.py:
  * APIConnectionError/APITimeoutError → 503 "offline"
  * RateLimitError → 429 "muita gente"
  * AuthenticationError → 503 + log ERROR (chave inválida)
  * Quota tenant estourada → 429 "limite diário"
- Retenção de InteractionLog: agendar `flask purge-logs` no cron diariamente.
- Segredos só em `.env` (nunca commitar); produção mantém `chmod 600`.
- Entrypoints: `run.py` em dev, `wsgi.py` em produção (Gunicorn).

## Alvo de hardware
- Piloto roda em **Raspberry Pi 3 B/B+** com Raspberry Pi OS **32 bits**
  (1 GB de RAM — usar SO 64 bits prejudica performance).
- Ajustes do Pi 3 (swap 1 GB, `gpu_mem=64`, desabilitar Bluetooth) estão
  documentados em `docs/OPERACAO.md` §1.1.1.
- Em alto tráfego, separar servidor (host dedicado) do kiosk (Pi 3 só exibe).
