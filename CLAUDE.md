# CLAUDE.md — Mapa do projeto e regras de engenharia

> Guia de orientação para qualquer agente que vá trabalhar nesta base.
> Mantém a árvore de arquivos sincronizada com o estado real e as regras de negócio que precisam ser respeitadas.

---

## Árvore do projeto

```
app/
├── __init__.py             # Application factory + CLI: seed, init-db, purge-logs
├── extensions.py           # db, migrate, login_manager, limiter
├── helpers.py              # slugify, CSRF, decoradores auth, audit_log,
│                           #   build_ai_context, save_upload, validate_password_strength,
│                           #   tenant_get_or_404 / tenant_query (anti-IDOR),
│                           #   bump_content_version (sync com totem)
├── twofa.py                # TOTP (pyotp) + códigos de backup hashados
├── seed.py                 # Seed inicial: módulos, zoo demo, super_admin
├── models/
│   ├── institution.py      # Institution (+ daily_ai_quota, ai_calls_today),
│   │                       #   Module, InstitutionModule
│   ├── content.py          # Animal, Event, Store, Product, FAQ, MapArea
│   ├── log.py              # InteractionLog (retenção via flask purge-logs)
│   ├── user.py             # User (+ has_totp, totp_secret, backup_codes,
│   │                       #   must_change_password, failed_logins, locked_until),
│   │                       #   AuthLog
│   ├── audit.py            # AdminAuditLog + ACTION_* constants
│   ├── device.py           # TotemDevice (api_key_id, api_key_secret, last_seen,
│   │                       #   generate_api_key_id/secret)
│   ├── quiz.py             # QuizQuestion (perguntas + curiosidades por
│   │                       #   instituicao); to_public_dict() omite gabarito
│   └── rating.py           # ExperienceRating (anonimo: stars + comment).
│                           #   Sem PII no schema (sem IP/session/UA)
└── routes/
    ├── core.py             # Totem público: home, mapa, programação, alimentação,
    │                       #   /sw.js, /offline, /privacidade, /selector,
    │                       #   POST /api/locale (toggle de idioma na sessao)
    ├── zoo.py              # Totem: animais (espécies, lista, detalhe, catálogo)
    ├── shopping.py         # Totem: lojas
    ├── pharmacy.py         # Totem: produtos
    ├── voice.py            # IA: /api/voice, /api/chat (rate-limit + quota
    │                       #   + erros OpenAI tratados)
    ├── translate.py        # POST /<slug>/api/translate (PT/EN/ES/FR)
    │                       #   + GET /api/translate/languages (lista publica)
    ├── sync.py             # GET /<slug>/api/sync/version (publico, kiosk poll)
    │                       #   + GET /api/sync/snapshot (HMAC, snapshot completo
    │                       #   com ETag + 304)
    ├── quiz.py             # GET /<slug>/quiz (intro + perguntas embebidas)
    │                       #   + POST /<slug>/api/quiz/answer (valida + loga)
    ├── rating.py           # GET /<slug>/rating (SPA estrelas + comentario)
    │                       #   + POST /<slug>/api/rating (anonimo, rate-limit)
    ├── admin_auth.py       # /admin/login, logout, change_password, forgot_password,
    │                       #   totp_setup, totp_challenge, totp_backup_codes (+ regen)
    ├── admin_platform.py   # /admin/platform/* (super_admin):
    │                       #   dashboard (com metricas inline), institutions,
    │                       #   users, logs, metrics_view + metrics_json,
    │                       #   institution_preview (white-label sem persistir)
    ├── admin_institution.py # /admin/institutions/<iid>/* (client_admin):
    │                       #   dashboard + CRUD (animais, eventos, lojas,
    │                       #   produtos, FAQs, logs)
    ├── devices.py          # /admin/platform/devices/* + /admin/platform/audit
    │                       #   + /api/heartbeat (HMAC + anti-replay)
    │                       #   + /api/local/wake + /api/local/wake-stream
    │                       #     (loopback + shared secret, SSE para o kiosk)
    └── health.py           # /health

app/services/               # Integracoes externas plugaveis (registry pattern)
├── __init__.py             # Exporta `registry` (singleton) e `IntegrationRegistry`
├── integrations.py         # Protocol `Integration` + registry com health-check
├── translation.py          # TranslationIntegration (OpenAI gpt-4o-mini)
│                           #   PT/EN/ES/FR + cache (Redis ou memoria) + erros
│                           #   classificados (offline/rate_limit/auth/generic)
├── metrics.py              # Agregacoes de InteractionLog por instituicao:
│                           #   daily counts, canais (voice/text/translate),
│                           #   idiomas e top-questions normalizadas
└── i18n.py                 # Catalogo PT/EN puro Python + helpers t(),
                            #   get_locale, set_locale (sessao). Sem Babel.

app/sensors/                # Drivers de sensores fisicos do totem (Pi-only)
├── __init__.py             # Exports do pacote (PirSensor, Dht22Sensor)
├── base.py                 # SensorReading + is_pi_hardware()
├── pir.py                  # PIR HC-SR501 — RPi.GPIO + fallback mock
├── dht22.py                # DHT22 — adafruit-circuitpython-dht + mock
└── daemon.py               # SensorDaemon: agrega leituras, posta wake local
                            #   e envia heartbeat HMAC ao servidor

scripts/
└── totem_sensor_daemon.py  # Entry point standalone do daemon de sensores
                            #   (executado via systemd: totem-sensors.service)

templates/
├── base.html               # Layout público (banner offline, link privacidade,
│                           #   registro do SW)
├── offline.html            # Fallback do service worker
├── privacidade.html        # Aviso LGPD
├── selector.html           # Seletor de instituição
├── 403.html · 404.html · 500.html
├── core/                   # home, mapa, programacao, alimentacao
├── modules/
│   ├── zoo/                # especies, lista, detalhe, catalogo
│   ├── shopping/           # lojas, loja_detalhe
│   ├── pharmacy/           # produtos
│   ├── quiz/quiz.html      # State-machine SPA: intro → pergunta →
│   │                       #   feedback → final (timer Trello 3.2/3.7)
│   └── rating/rating.html  # SPA: pergunta SIM/NAO → estrelas + comentario
│                           #   → obrigado (Trello Modulo 4 - Avaliacao)
├── voice/index.html        # Assistente (consentimento LGPD + microfone + chat)
└── admin/
    ├── base.html           # Layout do painel (role-aware, noindex, no-store)
    ├── login.html
    ├── change_password.html
    ├── forgot_password.html # Placeholder v1
    ├── totp_setup.html              # QR code + verificação inicial
    ├── totp_challenge.html          # Segundo fator no login
    ├── totp_backup_codes.html       # Exibição única após setup
    ├── totp_backup_codes_regen.html # Regeneração protegida
    ├── platform/           # super_admin
    │   ├── dashboard.html        # (com totais por instituicao nos 30d)
    │   ├── metrics.html          # Drilldown por instituicao: serie diaria,
    │   │                          # canais, idiomas, top-questions
    │   ├── institution_list.html / institution_form.html
    │   │                          # (campo daily_ai_quota + contador do dia)
    │   ├── user_list.html / user_form.html
    │   ├── device_list.html / device_credentials.html  # API key + HMAC secret
    │   ├── audit_list.html         # Trilha de AdminAuditLog
    │   └── log_list.html
    └── institution/        # client_admin
        ├── dashboard.html
        ├── content_animals.html / animal_form.html
        ├── content_events.html  / event_form.html
        ├── content_stores.html  / store_form.html
        ├── content_products.html / product_form.html
        ├── faq_list.html        / faq_form.html
        ├── quiz_list.html       / quiz_form.html
        └── log_list.html

static/
├── css/style.css           # Totem
├── css/admin.css           # Painel admin
├── js/sw.js                # Service worker (cache estáticos + fallback offline)
├── images/                 # Logo + imagens do zoo demo
└── uploads/                # Uploads por instituição (gitignored)

migrations/                 # Alembic (Flask-Migrate) — NÃO editar manualmente
                            #   sem rodar flask db migrate

tests/
├── conftest.py             # Fixture: app "testing", SQLite em memória, seed
├── test_smoke.py           # Rotas públicas (home, selector, privacidade,
│                           #   offline, /sw.js, IA, admin login)
├── test_voice_api.py       # /api/chat e /api/voice com OpenAI mockada
│                           #   (quota, offline, feliz)
├── test_2fa.py             # Setup de TOTP, códigos de backup, challenge
├── test_security.py        # Política de senha, lockout, auditoria, CSRF
├── test_heartbeat.py       # /api/heartbeat (HMAC, API key, anti-replay)
├── test_sensors.py         # PIR/DHT22 mocks, /api/local/wake (loopback +
│                           #   secret), telemetria de sensores no heartbeat
├── test_translation.py     # Registry, cache, classificacao de erros e rota
│                           #   POST /<slug>/api/translate (OpenAI mockada)
├── test_metrics.py         # Agregacoes (daily/canais/idiomas/top), janela
│                           #   temporal, normalizacao de perguntas, summary
├── test_tenant_isolation.py # Cross-tenant: 404 vs 403, audit
│                           #   ACTION_TENANT_DENIED, super_admin atravessa
├── test_sync.py            # bump_content_version + endpoints
│                           #   /api/sync/version e /api/sync/snapshot (HMAC,
│                           #   ETag, 304, isolamento de tenant)
├── test_preview.py         # Pre-visualizacao de white-label: auth gate,
│                           #   override hex/tema/tagline, validacao defensiva
│                           #   (input lixo nao quebra layout), garantia de
│                           #   nao-persistencia no banco
├── test_quiz.py            # Modelo (options, is_valid, to_public_dict NAO
│                           #   vaza gabarito), rota publica + answer (logs,
│                           #   isolamento cross-tenant, payload invalido)
├── test_i18n.py            # Catalogo PT/EN consistente, t() + fallback,
│                           #   /api/locale persistente, voice/chat respeitam
│                           #   locale (mock OpenAI capturando system prompt)
└── test_rating.py          # Validacao de estrelas, anonimato (sem PII no
                            #   schema), gate por modulo, isolamento tenant,
                            #   metricas com avg/distribuicao/janela temporal

deploy/
├── backup.sh               # Backup datado SQLite/Postgres + retenção 14d
├── install_production.sh   # Instalador prod: Nginx + Gunicorn + systemd + SSL
├── nginx.conf.template
├── totem-flexmedia.service
└── totem-sensors.service   # systemd unit do daemon de sensores (Pi-only)

docs/
└── OPERACAO.md             # Manual de operação (Pi 3): instalação, troca de
                            #   chaves, restauração de backup, nova instituição

data/
├── animais.json            # Seed zoo demo
└── programacao.json        # Seed eventos demo

install_totem.sh            # Configura Raspberry como kiosk: systemd auto-restart,
                            #   Chromium fullscreen, watchdog, unclutter, autostart
INSTALACAO.md               # Guia passo a passo (Pi real ou VM Debian 12)
wsgi.py                     # Entrypoint de produção (Gunicorn)
run.py                      # Entrypoint de desenvolvimento (python run.py)
gunicorn.conf.py            # Config do Gunicorn para deploy
.env.example                # Template (SECRET_KEY, OPENAI_API_KEY, SUPERADMIN_*,
                            #   DATABASE_URL, REDIS_URL,
                            #   INTERACTION_LOG_RETENTION_DAYS,
                            #   REQUIRE_TOTP_FOR_SUPERADMIN)
config.py                   # Config / ProductionConfig / TestingConfig
                            #   + INTERACTION_LOG_RETENTION_DAYS (LGPD, default 90)
pytest.ini
requirements.txt            # Flask, SQLAlchemy, Migrate, Login, Limiter, OpenAI,
                            #   psycopg, redis, pyotp, qrcode[pil], Pillow, gunicorn
requirements-dev.txt        # pytest + pytest-cov
requirements-pi.txt         # Drivers de sensores (RPi.GPIO + adafruit-dht);
                            #   so instalar quando o host for um Raspberry Pi
README.md                   # Apresentação pública do projeto
```

---

## Regras de engenharia

- Tudo em **pt-BR** (comentários, variáveis, mensagens de erro, flashes, commits).
- **Nunca** chamar OpenAI em testes — sempre mockar via `unittest.mock`.
- Toda nova coluna em `models/*` requer migration: `flask db migrate -m "msg" && flask db upgrade`.
- Erros da OpenAI diferenciados em `voice.py`:
  - `APIConnectionError` / `APITimeoutError` → 503 "offline"
  - `RateLimitError` → 429 "muita gente"
  - `AuthenticationError` → 503 + `log.error` (chave inválida)
  - Quota tenant estourada → 429 "limite diário"
- Retenção de `InteractionLog`: agendar `flask purge-logs` no cron diariamente.
- **Toda ação administrativa sensível** grava em `AdminAuditLog` via `audit_log(actor, action, target, ...)` — usar as constantes `ACTION_*` em `app/models/audit.py`.
- **Senhas** validadas por `validate_password_strength` (mín. 10 caracteres) e protegidas com Werkzeug scrypt.
- **2FA**: códigos de backup armazenados como hash (Werkzeug); só são exibidos uma vez ao gerar.
- **CSRF**: usar `generate_csrf_token` (helpers) no template e `validate_csrf_token()` no início de cada POST do admin.
- **Heartbeat de totem**: validar HMAC SHA-256 com janela anti-replay de 5 minutos.
- **Sensores fisicos (PIR + DHT22)**: nunca rodar dentro do worker Gunicorn.
  Sempre via `scripts/totem_sensor_daemon.py` como systemd unit separada
  (`totem-sensors.service`). Em laptop/CI/servidor remoto, `is_pi_hardware()`
  retorna False e os modulos caem em mock automaticamente.
- **/api/local/wake**: loopback-only + `X-Wake-Secret` (env `TOTEM_WAKE_SECRET`).
  Fail-closed se o segredo nao estiver configurado. Usado pelo daemon de
  sensores (mesmo host) para acordar o kiosk via SSE.
- **Integracoes externas (tradução, visão, analytics)**: sempre via
  `app.services.registry`. Para adicionar uma nova, criar a classe em
  `app/services/<nome>.py` (com `name`, `is_available`, `health_check`) e
  fazer `registry.register(...)` no factory. NUNCA acoplar APIs ao core.
  Erros classificados como em `voice.py` (offline/rate_limit/auth/generic).
- **Metricas por instituicao**: `app.services.metrics` e' a fonte unica
  da verdade sobre como `InteractionLog.input_type` codifica canais
  (`voice`/`text`/`translate:<lang>`). Mudancas de codificacao se atualizam
  ali e refletem no dashboard, na pagina de metricas e no JSON endpoint.
- **Isolamento multi-tenant**: toda rota de `client_admin` que aceita
  `child_id` no path DEVE usar `tenant_get_or_404(Model, child_id, iid)`.
  Filtragem manual por `institution_id` ainda funciona, mas o helper
  centraliza a regra e e' o canal coberto pelos testes de regressao em
  `test_tenant_isolation.py`. `client_admin_required` audita tentativas
  cross-tenant em `AdminAuditLog` (`ACTION_TENANT_DENIED`) — sinal forte
  de credencial vazada ou bug de UI.
- **Avaliacao de experiencia**: anonima por design — `ExperienceRating` NAO
  pode ganhar campos de PII (IP, session, user_agent, email) sem revisitar
  LGPD. O teste `test_modelo_nao_persiste_dados_pessoais` falha
  proativamente se alguem adicionar um desses. Estrelas validadas server-side
  (`is_valid_stars`, range 1-5). Comentario e' truncado a 600 chars
  silenciosamente — entrada acidental de PII fica limitada.
- **i18n**: strings traduziveis vivem em `app/services/i18n.py:CATALOG` (PT/EN
  hoje, expansivel). Templates usam `{{ t('chave') }}`; rotas/codigo Python
  importam `from app.services.i18n import t`. Chave inexistente devolve a
  propria chave — sinal visual obvio em revisao. Toda chave PT precisa ter
  par em EN (testado em `test_i18n.py:test_chaves_consistentes_entre_idiomas`).
  Voz/chat: quando `locale != 'pt'`, instrucao "Respond in <idioma>" e'
  anexada ao system prompt — IA responde no idioma correto.
- **Quiz**: o gabarito (`correct_index` + `curiosity`) NUNCA vai no payload
  publico. `QuizQuestion.to_public_dict()` e' o unico canal de serializacao
  para o totem. O endpoint `/api/quiz/answer` recebe `{question_id,
  choice_index}`, consulta o gabarito server-side, registra
  `InteractionLog(input_type='quiz:correct'|'quiz:incorrect')` para
  alimentar metricas, e devolve resultado + curiosidade.
- **Pre-visualizacao de white-label**: rota `/admin/platform/institutions/<iid>/preview`
  renderiza a Home do totem com cores/tema/tagline propostos sem persistir
  nada. NUNCA fazer `db.session.commit()` nessa rota — o `db.session.rollback()`
  explicito + `session.remove()` no teardown garantem que mutacoes em memoria
  nao colem no banco. Inputs validados (hex regex, tema enum, tamanho max)
  para que entrada lixo cair no valor persistido em vez de quebrar o layout.
- **Sync de conteudo com totem**: toda mutacao de conteudo gerenciado pelo
  client_admin (Animal/Event/Store/Product/FAQ) DEVE chamar
  `bump_content_version(iid)` antes do `db.session.commit()`. O kiosk polla
  `/<slug>/api/sync/version` a cada 60s; quando o numero muda, recarrega.
  Endpoints de sync chamam `db.session.expire(inst, ['content_version'])`
  para nao retornar valor cached da identity map. Em testes, `TestingConfig`
  usa `StaticPool` no SQLite para que commits feitos em uma sessao sejam
  visiveis em outra (sem isso, `:memory:` cria DBs isolados por conexao).
- Segredos só em `.env` (nunca commitar); produção mantém `chmod 600`.
- Entrypoints: `run.py` em dev, `wsgi.py` em produção (Gunicorn).
- Não editar `migrations/versions/*` manualmente — sempre via Flask-Migrate.

---

## Alvo de hardware

- Piloto roda em **Raspberry Pi 3 B/B+** com Raspberry Pi OS **32 bits**
  (1 GB de RAM — SO 64 bits prejudica performance).
- Ajustes do Pi 3 (swap 1 GB, `gpu_mem=64`, desabilitar Bluetooth) estão
  documentados em `docs/OPERACAO.md` §1.1.1.
- Em alto tráfego, separar servidor (host dedicado) do kiosk (Pi 3 só exibe).

---

## Contexto de Produto — FlexMedia

### Estado atual (Sprint 4 — em andamento)

- Interface do totem funcional e responsiva.
- Integração de voz completa (Whisper + GPT-4o-mini + TTS).
- Painel admin redesenhado com identidade visual Flexmedia.
- White label: troca de contexto por instituição já implementada
  (`build_ai_context` lê dinamicamente do banco).
- Hardening de segurança: 2FA TOTP, lockout, auditoria, heartbeat HMAC,
  política de senha forte, CSP/CSRF.
- Tela administrativa de totens (CRUD + API key) e trilha de auditoria.

### Problema central validado pelo cliente

O sistema é **white label**: a FlexMedia configura o totem para diferentes
segmentos (zoológico, museu, hotel, shopping) sem tocar no código — apenas
pelo painel administrativo.

### Foco da Sprint 4

**Prioridade alta**
- Estabilizar troca de contexto entre verticais (zoológico → museu/hotel).
- Refinar dashboard admin com métricas por instituição.
- Polir UX do CRUD de prompts/conteúdo por instituição.

**Prioridade média**
- Login único (SSO) sem bloquear as entregas acima.
- Melhorias de UI/UX e acessibilidade do painel admin.

### Fora do escopo agora (não implementar)

- Integração com câmera.
- Avatar animado (maioria das soluções é paga).
- Sensor de luminosidade nativo Android.

### Cybersecurity como parte do processo

Toda feature precisa nascer com hardening embutido — não é etapa
posterior. Padrão mínimo:

- Inputs validados em servidor (não confiar no front).
- Logs em `AdminAuditLog` para qualquer mutação relevante.
- Rate-limit em rotas autenticáveis e de IA.
- Tenant isolation revalidado em cada query do client_admin.
- HMAC + anti-replay em endpoints de máquina (devices/heartbeat).
- CSP, X-Frame-Options, Cache-Control no admin.
