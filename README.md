# Totem FlexMedia — Plataforma White Label Multi-Instituições

> Projeto desenvolvido para o **Challenge FIAP** em parceria com a empresa **Flexmedia**.
> Plataforma de totem interativo multi-tenant com IA por voz e texto.

---

## Sobre o projeto

O **Totem FlexMedia** é uma plataforma white label que permite operar totens interativos em múltiplas instituições — zoológicos, shoppings, farmácias, museus, aquários e parques — com uma única base de código.

Cada instituição possui tema visual próprio, módulos configuráveis e um assistente de IA contextualizado com seu conteúdo (animais, lojas, produtos, eventos e FAQs).

---

## Como funciona a IA

1. O visitante toca no botão e **fala sua pergunta** (ou digita)
2. O áudio é transcrito pelo **OpenAI Whisper**
3. A pergunta é processada pelo **GPT-4o-mini** com contexto da instituição
4. A resposta é convertida em fala pelo **OpenAI TTS**
5. O totem **responde em voz** com animação visual sincronizada

---

## Tecnologias

| Camada | Tecnologia |
|--------|-----------|
| Backend | Python, Flask, Flask-SQLAlchemy, Flask-Migrate, Flask-Login |
| Autenticação | Flask-Login + Werkzeug (scrypt), Flask-Limiter |
| IA / STT | OpenAI Whisper |
| IA / Chat | GPT-4o-mini |
| IA / TTS | OpenAI TTS |
| Banco de dados | SQLite (dev) / PostgreSQL (prod) |
| Frontend | HTML, CSS, JavaScript vanilla |
| Servidor produção | Gunicorn + Nginx + systemd + Let's Encrypt |
| Cache / Rate limit | Redis (local, loopback) |
| Hardware alvo | **Raspberry Pi 3 B/B+** (piloto) — Pi 4 também suportado |
| Kiosk | Chromium fullscreen + watchdog + unclutter (via `install_totem.sh`) |

---

## Instalação

### 1. Ambiente virtual

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/macOS
```

### 2. Dependências

```bash
pip install -r requirements.txt
```

### 3. Variáveis de ambiente

Copie `.env.example` para `.env` e preencha os valores:

```bash
cp .env.example .env
```

Variáveis obrigatórias:

| Variável | Descrição |
|----------|-----------|
| `SECRET_KEY` | Chave secreta do Flask (use `python -c "import secrets; print(secrets.token_hex(32))"`) |
| `OPENAI_API_KEY` | Chave da API OpenAI |
| `SUPERADMIN_EMAIL` | E-mail do primeiro super admin (seeded na primeira execução) |
| `SUPERADMIN_PASSWORD` | Senha do super admin (mín. 10 caracteres) |

Variáveis opcionais:

| Variável | Descrição |
|----------|-----------|
| `DATABASE_URL` | Ex: `postgresql+psycopg://user:pw@host:5432/flexmedia` (se ausente, usa SQLite em `instance/`) |
| `INTERACTION_LOG_RETENTION_DAYS` | Retenção LGPD de `InteractionLog` — default 90 (purga via `flask purge-logs`) |

### 4. Executar

```bash
python run.py
```

Acesse: `http://localhost:5000`

Para produção (Nginx + Gunicorn + SSL) o entrypoint é `wsgi.py` e o instalador
automático é `deploy/install_production.sh` — ver [docs/OPERACAO.md](docs/OPERACAO.md).

Na primeira execução o banco SQLite é criado em `instance/flexmedia.db` e a instituição de demonstração (Neural Crew Zoo) é semeada automaticamente a partir dos JSONs em `data/`.

> **Atenção:** O super admin é criado **apenas uma vez**, na primeira execução. Se o banco já existir, o seed é ignorado. Para recriar, delete `instance/flexmedia.db` e reinicie.

---

## Painel Administrativo

Acesse `/admin/login`.

### Níveis de acesso

| Papel | Acesso |
|-------|--------|
| `super_admin` | Acesso global: todas as instituições, usuários, logs de auth e IA |
| `client_admin` | Acesso restrito à sua instituição: conteúdo (animais, eventos, lojas, produtos, FAQs) e logs de IA |

- O `super_admin` é criado via variáveis de ambiente no `.env` (seed na primeira execução)
- Admins de instituição são criados pelo super admin em `/admin/platform/users`
- Cada `client_admin` só vê e edita dados da sua própria instituição (isolamento por tenant)

---

## URLs principais

| URL | Descrição |
|-----|-----------|
| `/` | Redireciona para o seletor |
| `/selector` | Seleção de instituição |
| `/<slug>/` | Home do totem |
| `/<slug>/mapa` | Mapa interativo |
| `/<slug>/programacao` | Eventos e programação |
| `/<slug>/animais/especies` | Catálogo de animais (zoo) |
| `/<slug>/lojas` | Lojas (shopping) |
| `/<slug>/produtos` | Produtos (farmácia) |
| `/<slug>/ia` | Assistente IA |
| `/admin/login` | Login do painel administrativo |
| `/admin/platform/` | Dashboard super admin |
| `/admin/institutions/<id>/` | Dashboard client admin |

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
Totem_Flexmedia/
├── app/
│   ├── __init__.py              # App factory
│   ├── extensions.py            # SQLAlchemy, Migrate, LoginManager, Limiter
│   ├── helpers.py               # Decorators, CSRF, load_institution, build_ai_context
│   ├── seed.py                  # Seed inicial (zoo + super admin)
│   ├── models/                  # Institution, Animal, Event, Store, Product, FAQ, InteractionLog, User, AuthLog
│   └── routes/
│       ├── core.py              # Home, mapa, programação, alimentação
│       ├── zoo.py               # Animais
│       ├── shopping.py          # Lojas
│       ├── pharmacy.py          # Produtos
│       ├── voice.py             # IA (voz + chat)
│       ├── admin_auth.py        # Login / logout
│       ├── admin_platform.py    # Super admin (instituições, usuários, logs globais)
│       └── admin_institution.py # Client admin (conteúdo por instituição)
├── templates/
│   ├── base.html                # Layout totem
│   ├── selector.html            # Seletor de instituição
│   ├── admin/
│   │   ├── base.html            # Layout admin
│   │   ├── login.html           # Tela de login
│   │   ├── platform/            # Templates super admin
│   │   └── institution/         # Templates client admin
│   ├── core/                    # Home, mapa, programação, alimentação
│   ├── modules/                 # zoo/, shopping/, pharmacy/
│   └── voice/                   # Interface IA
├── static/
│   ├── css/style.css            # Estilos do totem
│   ├── css/admin.css            # Estilos do painel admin
│   ├── images/                  # Imagens dos animais
│   └── uploads/                 # Uploads via admin
├── data/
│   ├── animais.json             # Seed zoo
│   └── programacao.json         # Seed eventos
├── instance/flexmedia.db        # Banco SQLite (auto-criado, não commitado)
├── .env.example                 # Template de variáveis de ambiente
├── config.py
├── run.py
└── requirements.txt
```

---

## Segurança

- Senhas protegidas com Werkzeug scrypt (Python ≥ 3.9)
- CSRF protection em todos os formulários POST
- Rate limiting: login (20/min, 100/h), voice API (10/min, 30/h), chat API (20/min, 60/h)
- Isolamento de tenant: `client_admin` não pode acessar dados de outras instituições
- Login timing-safe (previne enumeração de usuários por tempo de resposta)
- Headers de segurança: `X-Frame-Options`, `X-Content-Type-Options`, `X-XSS-Protection`, `Referrer-Policy`
- Admin panel: `Cache-Control: no-store`, `noindex, nofollow`
- `SESSION_COOKIE_SECURE=True` em produção, `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE=Lax`
- Parâmetro `next=` validado (só aceita paths `/admin/...`)

---

## LGPD e experiência offline

- `/privacidade` — aviso de coleta, uso da OpenAI, retenção e direitos do titular.
- Assistente de IA exibe **modal de consentimento** antes do primeiro uso do microfone.
- `static/js/sw.js` — service worker que cacheia estáticos e serve `/offline`
  quando a rede cai (banner de status é exibido no layout público).
- `InteractionLog` tem retenção configurável (default 90 dias).
  Agende `flask purge-logs` no cron para cumprir a retenção.

---

## Quota de IA por instituição

Cada `Institution` tem `daily_ai_quota` (limite diário de chamadas OpenAI).
`app/routes/voice.py` incrementa `ai_calls_today` a cada chamada e, ao estourar,
retorna **429 "limite diário atingido"** sem consultar a OpenAI — protegendo
custo e disponibilidade.

Erros da OpenAI são diferenciados em `voice.py`:

| Erro OpenAI                              | Resposta HTTP | Mensagem ao usuário |
|------------------------------------------|---------------|---------------------|
| `APIConnectionError` / `APITimeoutError` | 503           | "offline"           |
| `RateLimitError`                         | 429           | "muita gente"       |
| `AuthenticationError`                    | 503           | "indisponível" + log ERROR |
| Quota tenant estourada                   | 429           | "limite diário"     |

---

## Testes

```bash
pip install -r requirements-dev.txt
pytest
```

- `tests/test_smoke.py` — rotas públicas (home, selector, privacidade, offline, `/sw.js`, admin login).
- `tests/test_voice_api.py` — `/api/chat` e `/api/voice` com OpenAI **mockada**
  (nunca bate na API real em testes).

---

## Deploy e operação

Documentação operacional completa em **[docs/OPERACAO.md](docs/OPERACAO.md)**:

1. Instalação no Raspberry Pi 3 (servidor + kiosk).
2. Troca de chaves e segredos (`.env`).
3. Restauração de backup (SQLite e Postgres).
4. Adicionar nova instituição (painel ou CLI).

Scripts auxiliares:

| Script                         | Função                                                    |
|--------------------------------|-----------------------------------------------------------|
| `deploy/install_production.sh` | Instalador end-to-end: Nginx + Gunicorn + SSL + cron      |
| `deploy/backup.sh`             | Backup diário do banco (SQLite ou Postgres), retenção 14d |
| `install_totem.sh`             | Configura o Raspberry como kiosk (Chromium fullscreen)    |
