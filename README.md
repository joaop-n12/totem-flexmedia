# Totem FlexMedia — Plataforma White Label Multi-Instituições

> Projeto desenvolvido para o **Challenge FIAP** em parceria com a empresa **Flexmedia**.
> Plataforma de totem interativo multi-tenant com IA por voz e texto.

---

## Sobre o projeto

O **Totem FlexMedia** é uma plataforma white label que permite operar totens interativos em múltiplas instituições — zoológicos, shoppings, farmácias, museus, aquários e parques — com uma única base de código.

Cada instituição tem tema visual próprio, módulos configuráveis e um assistente de IA contextualizado com seu conteúdo (animais, lojas, produtos, eventos e FAQs).

---

## Como funciona a IA

1. O visitante toca no botão e **fala** sua pergunta (ou digita)
2. O áudio é transcrito pelo **OpenAI Whisper**
3. A pergunta é processada pelo **GPT-4o-mini** com contexto da instituição
4. A resposta volta em fala via **OpenAI TTS**
5. O totem responde em voz com animação visual sincronizada

---

## Tecnologias

| Camada | Tecnologia |
|--------|-----------|
| Backend | Python, Flask, Flask-SQLAlchemy, Flask-Migrate, Flask-Login, Flask-Limiter |
| Auth | Werkzeug scrypt, **TOTP 2FA** (`pyotp` + `qrcode`), códigos de backup |
| IA STT / Chat / TTS | OpenAI Whisper · GPT-4o-mini · OpenAI TTS |
| Tradução | OpenAI (`gpt-4o-mini`) · cache Redis · PT/EN/ES/FR (`app/services/translation.py`) |
| i18n da UI | Catálogo puro Python PT/EN (`app/services/i18n.py`) — sem Babel |
| Banco | SQLite (dev) · PostgreSQL via `psycopg[binary]` (prod) |
| Cache / Rate limit | Redis (loopback) |
| Frontend | HTML, CSS e JavaScript vanilla |
| Servidor produção | Gunicorn + Nginx + systemd + Let's Encrypt **ou** Cloudflare Tunnel |
| HTTPS público (frota) | **Cloudflare Tunnel** (`deploy/install_cloudflared.sh`) — sem IP público, sem cert próprio, microfone/câmera funcionam em qualquer rede |
| Sensores físicos | **DHT11/DHT22** (ambiente) + **HC-SR04** (presença/distância) via daemon systemd separado (`totem-sensors.service`) |
| Hardware alvo | **Raspberry Pi 3 B/B+** (piloto) — Pi 4 também suportado |
| Kiosk | Chromium fullscreen + watchdog + unclutter (`install_totem.sh`) ou Fully Kiosk Browser (Android) |

---

## Início rápido (desenvolvimento)

```bash
# 1. Ambiente virtual
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Linux/macOS

# 2. Dependências
pip install -r requirements.txt

# 3. Configuração
cp .env.example .env           # editar SECRET_KEY, OPENAI_API_KEY, SUPERADMIN_*

# 4. Banco e seed
flask --app run.py db upgrade  # aplica migrations
python run.py                  # cria seed na primeira execução
```

Acesse `http://localhost:5000`.

> Para guia detalhado (Raspberry Pi, VM Debian, troubleshooting) veja **[INSTALACAO.md](INSTALACAO.md)**.

---

## Variáveis de ambiente

| Variável | Obrig. | Descrição |
|----------|--------|-----------|
| `SECRET_KEY` | sim | Chave Flask (`python -c "import secrets; print(secrets.token_hex(32))"`) |
| `FIELD_ENCRYPTION_KEY` | sim em prod | Fernet — cifra TOTP secret e `device.api_key_secret` (`Fernet.generate_key()`) |
| `OPENAI_API_KEY` | sim | Chave OpenAI |
| `SUPERADMIN_EMAIL` | sim | E-mail do primeiro super admin (seed) |
| `SUPERADMIN_PASSWORD` | sim | Senha (mín. 12 caracteres) |
| `DATABASE_URL` | não | Ex: `postgresql+psycopg://user:pw@host/flexmedia` (default: SQLite) |
| `INTERACTION_LOG_RETENTION_DAYS` | não | Retenção LGPD — default 90 |
| `REDIS_URL` | não | Para Flask-Limiter e cache de tradução em produção (default: memória) |
| `TOTEM_PUBLIC_URL` | não | URL HTTPS pública (preenchido automaticamente por `install_cloudflared.sh`) |
| `TOTEM_WAKE_SECRET` | sim no Pi | Segredo loopback do `/api/local/wake` (daemon de sensores ↔ Flask) |
| `TOTEM_DISABLE_SENSORS` | não | `1` força sensores em mock no próprio Pi (e suprime overlay) |
| `DHT_MODEL` | não | `DHT11` ou `DHT22` — default `DHT22` |
| `REQUIRE_TOTP_FOR_SUPERADMIN` | não | `1` (default) obriga 2FA em super admins |

---

## Painel administrativo

Acesse `/admin/login`. Suporta **2FA via TOTP** (Google Authenticator, Authy, 1Password) com códigos de backup.

| Papel | Acesso |
|-------|--------|
| `super_admin` | Global: instituições, usuários, dispositivos, logs de auditoria, IA |
| `client_admin` | Restrito à própria instituição: conteúdo + logs de IA |

- Super admin é criado **uma única vez** via `.env` na primeira execução.
- Demais admins são criados em `/admin/platform/users` (super admin).
- Senhas temporárias forçam troca no primeiro login (`must_change_password`).
- Cada `client_admin` enxerga apenas dados da sua instituição.

---

## URLs principais

### Totem (público)
| URL | Descrição |
|-----|-----------|
| `/` | Redireciona para o seletor |
| `/selector` | Seleção de instituição |
| `/<slug>/` | Home |
| `/<slug>/mapa` | Mapa interativo |
| `/<slug>/programacao` | Eventos |
| `/<slug>/animais/especies` | Catálogo (zoo) |
| `/<slug>/lojas` | Lojas (shopping) |
| `/<slug>/produtos` | Produtos (farmácia) |
| `/<slug>/ia` | Assistente IA |
| `/<slug>/quiz` | Quiz educativo (gabarito server-side) |
| `/<slug>/rating` | Avaliação anônima (estrelas + comentário) |
| `/privacidade` | Aviso LGPD |
| `/offline` · `/sw.js` | Modo offline + service worker |
| `POST /api/locale` | Toggle de idioma da UI (PT/EN) |

### Admin
| URL | Descrição |
|-----|-----------|
| `/admin/login` · `/admin/logout` | Login com 2FA opcional |
| `/admin/totp/setup` | Cadastro do segundo fator |
| `/admin/totp/backup-codes` | Códigos de recuperação |
| `/admin/platform/` | Dashboard super admin |
| `/admin/platform/institutions/` | CRUD instituições |
| `/admin/platform/users/` | CRUD usuários |
| `/admin/platform/devices/` | CRUD totens (API key + heartbeat) |
| `/admin/platform/audit` | Trilha de auditoria |
| `/admin/platform/logs` | Logs globais de IA |
| `/admin/institutions/<id>/` | Dashboard client admin |

### API
| URL | Método | Descrição |
|-----|--------|-----------|
| `/api/voice` | POST | Áudio → resposta em áudio |
| `/api/chat` | POST | Texto → texto |
| `/<slug>/api/translate` | POST | Tradução PT/EN/ES/FR (cache Redis) |
| `/api/translate/languages` | GET | Lista pública de idiomas suportados |
| `/<slug>/api/quiz/answer` | POST | Valida resposta (gabarito server-side) + curiosidade |
| `/<slug>/api/rating` | POST | Avaliação anônima (sem PII) |
| `/<slug>/api/sync/version` | GET | Versão do conteúdo (polling do kiosk) |
| `/api/sync/snapshot` | GET | Snapshot completo (HMAC + ETag/304) |
| `/api/heartbeat` | POST | Pulso do totem (HMAC + API key + anti-replay) |
| `/api/local/wake` | POST | Daemon de sensores → Flask local (loopback + secret) |
| `/api/local/wake-stream` | GET | SSE consumido pelo kiosk para reagir a presença |
| `/api/session/state` | GET | Snapshot da máquina de estados (kiosk polla) |
| `/health` | GET | Liveness / readiness |

---

## Módulos disponíveis

| Slug | Nome | Ícone |
|------|------|-------|
| `home` | Home | ⊞ |
| `animais` | Catálogo de Animais | 🐾 |
| `mapa` | Mapa Interativo | 🗺️ |
| `programacao` | Programação | 📅 |
| `alimentacao` | Praça de Alimentação | 🍽️ |
| `ia` | Assistente IA | 💬 |
| `lojas` | Lojas | 🛍️ |
| `produtos` | Produtos | 💊 |

---

## Estrutura do projeto

Visão de alto nível — para a árvore completa e regras de cada arquivo,
ver [CLAUDE.md](CLAUDE.md).

```
totem_flexmedia/
├── app/
│   ├── __init__.py              # App factory + CLI (seed, init-db, purge-logs, security-upgrade)
│   ├── extensions.py            # db, migrate, login_manager, limiter
│   ├── crypto.py                # Fernet helpers (FIELD_ENCRYPTION_KEY) — dual-key
│   ├── helpers.py               # CSRF, decoradores, tenant_get_or_404, build_ai_context, save_upload
│   ├── twofa.py                 # TOTP + códigos de backup (hashados)
│   ├── seed.py                  # Seed inicial (zoo demo + super admin)
│   ├── models/                  # Institution, User, Device, Animal/Event/Store/Product/FAQ,
│   │                            # InteractionLog, AdminAuditLog, QuizQuestion, ExperienceRating
│   ├── routes/
│   │   ├── core.py              # Totem público + /api/locale + service worker
│   │   ├── zoo.py · shopping.py · pharmacy.py
│   │   ├── voice.py             # IA voz/chat (rate-limit + quota + erros OpenAI)
│   │   ├── translate.py         # POST /<slug>/api/translate (PT/EN/ES/FR)
│   │   ├── quiz.py · rating.py  # Quiz com gabarito server-side + rating anônimo
│   │   ├── sync.py              # /<slug>/api/sync/version + /api/sync/snapshot (HMAC + ETag)
│   │   ├── admin_auth.py        # Login, 2FA, troca de senha, backup codes
│   │   ├── admin_platform.py    # super_admin (instituições, usuários, devices, métricas, audit)
│   │   ├── admin_institution.py # client_admin (conteúdo da própria instituição)
│   │   ├── devices.py           # CRUD totens + /api/heartbeat + /api/local/wake(-stream) + /api/session/state
│   │   └── health.py
│   ├── services/                # Integrações plugáveis (registry pattern)
│   │   ├── integrations.py      # Protocol + registry com health-check
│   │   ├── translation.py       # OpenAI gpt-4o-mini + cache Redis
│   │   ├── metrics.py           # Agregações de InteractionLog por instituição
│   │   └── i18n.py              # Catálogo PT/EN puro Python — t(), get_locale, set_locale
│   └── sensors/                 # Drivers físicos (Pi-only; mock automático fora do Pi)
│       ├── base.py · dht22.py · hcsr04.py
│       └── daemon.py            # SensorDaemon (threads + heartbeat HMAC + post local wake)
├── templates/                   # Layout + módulos (zoo/shopping/pharmacy/quiz/rating) + admin
├── static/                      # CSS, sw.js, images, uploads (gitignored)
├── migrations/                  # Alembic — sempre via flask db migrate
├── tests/                       # 14 suites: smoke, voice, 2fa, security, heartbeat, sensors,
│                                # translation, metrics, tenant_isolation, sync, preview, quiz,
│                                # i18n, rating
├── scripts/
│   ├── totem_sensor_daemon.py   # Entry point do daemon (systemd: totem-sensors.service)
│   ├── simular_sensores.sh      # Simulador HC-SR04 + DHT (Linux/Pi)
│   ├── simular_sensores.ps1     # Mesma coisa para Windows/dev
│   └── teste_dht11.py           # Teste rápido isolado do DHT
├── deploy/
│   ├── install_production.sh    # Nginx + Gunicorn + Let's Encrypt + cron
│   ├── install_cloudflared.sh   # Cloudflare Tunnel (HTTPS público)
│   ├── rotate_secrets.sh        # Rotação assistida (SECRET_KEY, WAKE_SECRET, FIELD_ENCRYPTION_KEY)
│   ├── backup.sh                # Backup diário com retenção 14 dias
│   ├── nginx.conf.template
│   ├── totem-flexmedia.service
│   └── totem-sensors.service    # systemd unit do daemon de sensores
├── docs/
│   ├── OPERACAO.md              # Manual operacional (Pi 3 piloto)
│   └── AUDITORIA_SEGURANCA.md   # Auditoria de hardening (histórico)
├── data/                        # Seeds JSON
├── instance/                    # SQLite + uploads (gitignored)
├── logs/                        # Rotativo (gitignored)
├── install_totem.sh             # Configura Pi como kiosk (prompt: TOTEM_DISABLE_SENSORS)
├── INSTALACAO.md                # Guia passo a passo
├── CLAUDE.md                    # Mapa completo + regras de engenharia
├── config.py · run.py · wsgi.py · gunicorn.conf.py · pytest.ini
├── requirements.txt · requirements-dev.txt · requirements-pi.txt
└── .env.example
```

---

## Segurança

- **Senhas** Werkzeug scrypt; política mínima de 10 caracteres validada em `validate_password_strength`.
- **2FA TOTP** opcional para todos os admins (obrigatório para super admins via `REQUIRE_TOTP_FOR_SUPERADMIN`); códigos de backup hashados.
- **CSRF** em todos os formulários POST (`generate_csrf_token` + `validate_csrf_token`).
- **Lockout** progressivo após falhas de login + log em `AuthLog`.
- **Login timing-safe** (mitiga enumeração de usuários).
- **Rate limit** Flask-Limiter: login 20/min · voice 10/min · chat 20/min.
- **Headers** `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`, `Cache-Control: no-store` no admin.
- **Cookies** `SESSION_COOKIE_SECURE=True` em prod, `HttpOnly`, `SameSite=Lax`.
- **Tenant isolation** — `client_admin` não acessa outra instituição.
- **Auditoria** — toda ação sensível (criar/editar/excluir, login, 2FA, devices) grava em `AdminAuditLog`.
- **Heartbeat de totem** — HMAC SHA-256 com timestamp anti-replay (janela 5 min, comparado com `time.time()` Unix epoch — independente de timezone do host) + API key rotacionável.
- **Sensores físicos isolados** — `totem-sensors.service` roda fora do worker Gunicorn; `/api/local/wake` exige loopback + `X-Wake-Secret` (fail-closed sem segredo).
- **Cifragem em repouso** — `User.totp_secret` e `TotemDevice.api_key_secret` cifrados via Fernet (`FIELD_ENCRYPTION_KEY`), com rotação dual-key suportada.

---

## LGPD e experiência offline

- `/privacidade` — aviso de coleta, uso da OpenAI, retenção e direitos do titular.
- Modal de consentimento antes do primeiro uso do microfone.
- Service worker (`static/js/sw.js`) cacheia estáticos e serve `/offline` quando a rede cai.
- `InteractionLog` com retenção configurável (default 90 dias). Agende `flask purge-logs` no cron.

---

## Quota de IA por instituição

Cada `Institution` tem `daily_ai_quota`. `voice.py` incrementa `ai_calls_today` e, ao estourar, retorna **429 "limite diário"** sem chamar a OpenAI — protegendo custo e disponibilidade.

| Erro OpenAI | HTTP | Mensagem |
|-------------|------|----------|
| `APIConnectionError` / `APITimeoutError` | 503 | "offline" |
| `RateLimitError` | 429 | "muita gente" |
| `AuthenticationError` | 503 | "indisponível" + log ERROR |
| Quota tenant estourada | 429 | "limite diário" |

---

## Testes

```bash
pip install -r requirements-dev.txt
pytest
```

OpenAI é sempre **mockada** — nunca bate na API real em testes.

---

## Deploy e operação

Documentação operacional completa em **[docs/OPERACAO.md](docs/OPERACAO.md)** (instalação Pi 3, troca de chaves, restauração de backup, nova instituição).

| Script | Função |
|--------|--------|
| `install_totem.sh` | Setup do Pi como kiosk (venv, .env, banco, systemd, Chromium fullscreen, prompt de sensores) |
| `deploy/install_cloudflared.sh` | HTTPS público via Cloudflare Tunnel (resolve bloqueio de microfone) |
| `deploy/install_production.sh` | Alternativa on-prem: Nginx + Gunicorn + Let's Encrypt + cron |
| `deploy/rotate_secrets.sh` | Rotação assistida de `SECRET_KEY`, `TOTEM_WAKE_SECRET`, `FIELD_ENCRYPTION_KEY` |
| `deploy/backup.sh` | Backup diário (retenção 14 dias) |
| `scripts/simular_sensores.{sh,ps1}` | Simulador de HC-SR04 + DHT (testar overlay/áudio sem hardware) |
| `scripts/totem_sensor_daemon.py` | Entry point do daemon de sensores (rodado via `totem-sensors.service`) |

---

## Sensores físicos (piloto Pi 3)

Dois sensores integrados via daemon systemd separado do Flask:

| Sensor | GPIO padrão | Função |
|---|---|---|
| **HC-SR04** (ultrassônico) | TRIG=23, ECHO=24 | Detecta aproximação → muda estado da sessão (IDLE → ACTIVE) → toca áudio de boas-vindas |
| **DHT11 / DHT22** | DATA=GPIO 4 | Telemetria de temperatura/umidade — alimenta widgets TEMP/UMID na home e heartbeat para o painel admin |

Características:
- **Daemon isolado** (`totem-sensors.service`) — não roda no worker Gunicorn.
- **Mock automático** fora do Pi (laptop, CI, servidor remoto).
- **`TOTEM_DISABLE_SENSORS=1`** força mock no próprio Pi e suprime o overlay de proximidade.
- **Sem PIR** — presença detectada apenas pelo HC-SR04 (evita falsos positivos com passantes distantes).
- **Simuladores** em `scripts/simular_sensores.{sh,ps1}` para testar fluxo completo sem hardware.

Detalhes técnicos de cada driver em `app/sensors/` (cada arquivo tem docstring explicativa).

---

## Licença

Projeto acadêmico (Challenge FIAP × Flexmedia). Uso restrito conforme acordo entre as partes.
