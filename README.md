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
| Banco | SQLite (dev) · PostgreSQL via `psycopg[binary]` (prod) |
| Cache / Rate limit | Redis (loopback) |
| Frontend | HTML, CSS e JavaScript vanilla |
| Servidor produção | Gunicorn + Nginx + systemd + Let's Encrypt |
| Hardware alvo | **Raspberry Pi 3 B/B+** (piloto) — Pi 4 também suportado |
| Kiosk | Chromium fullscreen + watchdog + unclutter (`install_totem.sh`) |

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
flask --app app.py db upgrade  # aplica migrations
python app.py                  # cria seed na primeira execução
```

Acesse `http://localhost:5000`.

> Para guia detalhado (Raspberry Pi, VM Debian, troubleshooting) veja **[INSTALACAO.md](INSTALACAO.md)**.

---

## Variáveis de ambiente

| Variável | Obrig. | Descrição |
|----------|--------|-----------|
| `SECRET_KEY` | sim | Chave Flask (`python -c "import secrets; print(secrets.token_hex(32))"`) |
| `OPENAI_API_KEY` | sim | Chave OpenAI |
| `SUPERADMIN_EMAIL` | sim | E-mail do primeiro super admin (seed) |
| `SUPERADMIN_PASSWORD` | sim | Senha (mín. 10 caracteres) |
| `DATABASE_URL` | não | Ex: `postgresql+psycopg://user:pw@host/flexmedia` (default: SQLite) |
| `INTERACTION_LOG_RETENTION_DAYS` | não | Retenção LGPD — default 90 |
| `REDIS_URL` | não | Para Flask-Limiter em produção (default: memória) |

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
| `/privacidade` | Aviso LGPD |
| `/offline` · `/sw.js` | Modo offline + service worker |

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
| `/api/heartbeat` | POST | Pulso do totem (HMAC + API key) |
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

```
totem_flexmedia/
├── app/
│   ├── __init__.py              # App factory + CLI (seed, init-db, purge-logs)
│   ├── extensions.py            # db, migrate, login_manager, limiter
│   ├── helpers.py               # CSRF, decoradores, load_institution, build_ai_context
│   ├── twofa.py                 # TOTP, QR code, códigos de backup
│   ├── seed.py                  # Seed inicial (zoo demo + super admin)
│   ├── models/
│   │   ├── institution.py       # Institution, Module, InstitutionModule
│   │   ├── content.py           # Animal, Event, Store, Product, FAQ, MapArea
│   │   ├── log.py               # InteractionLog
│   │   ├── user.py              # User, AuthLog
│   │   ├── device.py            # TotemDevice (API key + HMAC)
│   │   └── audit.py             # AdminAuditLog
│   └── routes/
│       ├── core.py              # Home, mapa, programação, alimentação, /sw.js
│       ├── zoo.py · shopping.py · pharmacy.py
│       ├── voice.py             # IA voz/chat (rate-limit + quota)
│       ├── admin_auth.py        # Login, logout, 2FA, troca de senha
│       ├── admin_platform.py    # Super admin (instituições, usuários, logs)
│       ├── admin_institution.py # Client admin (conteúdo)
│       ├── devices.py           # CRUD de totens + heartbeat
│       └── health.py            # /health
├── templates/
│   ├── base.html · selector.html · privacidade.html · offline.html
│   ├── 403.html · 404.html · 500.html
│   ├── core/                    # home, mapa, programacao, alimentacao
│   ├── modules/                 # zoo/, shopping/, pharmacy/
│   ├── voice/index.html         # Assistente (consentimento LGPD + microfone)
│   └── admin/
│       ├── base.html · login.html · change_password.html · forgot_password.html
│       ├── totp_setup.html · totp_challenge.html
│       ├── totp_backup_codes.html · totp_backup_codes_regen.html
│       ├── platform/            # dashboard, institutions, users, devices, audit, logs
│       └── institution/         # dashboard + CRUD por instituição
├── static/
│   ├── css/style.css            # Totem
│   ├── css/admin.css            # Painel admin
│   ├── js/sw.js                 # Service worker
│   ├── images/                  # Assets do zoo demo + logo
│   └── uploads/                 # Uploads via admin (gitignored)
├── migrations/                  # Alembic (Flask-Migrate)
├── tests/
│   ├── conftest.py
│   ├── test_smoke.py            # Rotas públicas
│   ├── test_voice_api.py        # /api/chat e /api/voice (OpenAI mockada)
│   ├── test_2fa.py              # TOTP + códigos de backup
│   ├── test_security.py         # Política de senha, lockout, auditoria
│   └── test_heartbeat.py        # /api/heartbeat (HMAC, API key)
├── data/                        # Seed JSON (zoo demo)
├── deploy/                      # Nginx + systemd + backup + install_production.sh
├── docs/OPERACAO.md             # Manual de operação (Pi 3)
├── instance/                    # SQLite + uploads (gitignored)
├── logs/app.log                 # Log rotativo (gitignored)
├── app.py                       # Entrypoint dev
├── wsgi.py                      # Entrypoint prod (Gunicorn)
├── gunicorn.conf.py
├── install_totem.sh             # Configura Pi como kiosk
├── INSTALACAO.md                # Guia passo a passo
├── config.py · pytest.ini
├── requirements.txt · requirements-dev.txt
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
- **Heartbeat de totem** — HMAC SHA-256 com timestamp anti-replay (janela 5 min) + API key rotacionável.

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
| `deploy/install_production.sh` | Nginx + Gunicorn + SSL + cron |
| `deploy/backup.sh` | Backup diário (retenção 14 dias) |
| `install_totem.sh` | Kiosk no Raspberry (Chromium fullscreen + watchdog) |

---

## Licença

Projeto acadêmico (Challenge FIAP × Flexmedia). Uso restrito conforme acordo entre as partes.
