# Totem FlexMedia — Plataforma White Label Multi-Instituições

> Projeto desenvolvido para o **Challenge FIAP**, em parceria com a empresa **FlexMedia**.  
> Plataforma de totens interativos multi-tenant com inteligência artificial, interação por voz e texto e gerenciamento centralizado.

---

## 💡 Sobre o projeto

O **Totem FlexMedia** é uma plataforma White Label que permite operar totens interativos em múltiplas instituições — zoológicos, shoppings, farmácias, museus, aquários e parques — utilizando uma única base de código.

Cada instituição possui identidade visual própria, módulos configuráveis e um assistente de IA contextualizado com seus conteúdos, como animais, lojas, produtos, eventos e perguntas frequentes.

A arquitetura **Multi-Tenant** permite que diferentes instituições compartilhem a mesma aplicação, mantendo seus dados, usuários, configurações e conteúdos isolados.

A solução também foi preparada para operação em hardware de baixo custo, incluindo Raspberry Pi.

## ✨ Funcionalidades

- **Assistente com IA:** interação por voz e texto para responder dúvidas e orientar visitantes.
- **Reconhecimento de voz:** transcrição de áudio utilizando OpenAI Whisper.
- **Síntese de voz:** respostas faladas com OpenAI TTS.
- **Mapa interativo:** navegação por ambientes, setores e diferentes andares.
- **Módulos personalizados:** conteúdos específicos para zoológicos, shoppings e farmácias.
- **Catálogos interativos:** consulta de animais, lojas e produtos.
- **Programação de eventos:** apresentação de atividades e eventos da instituição.
- **Quiz educativo:** perguntas interativas com validação no servidor.
- **Avaliação de experiência:** coleta anônima de feedback dos visitantes.
- **Multilíngue:** tradução de conteúdos em português, inglês, espanhol e francês.
- **Modo offline:** disponibilização de recursos previamente armazenados quando a conexão cai.
- **Sensores físicos:** detecção de aproximação e monitoramento de temperatura e umidade.

## 🤖 Como funciona a inteligência artificial

A plataforma integra serviços da OpenAI para permitir uma interação natural entre visitantes e o totem.

1. O visitante toca no botão e fala sua pergunta ou utiliza a entrada por texto.
2. O áudio é transcrito pelo **OpenAI Whisper**.
3. A pergunta é processada pelo **GPT-4o-mini**, utilizando o contexto da instituição.
4. A resposta é convertida em áudio pelo **OpenAI TTS**.
5. O totem reproduz a resposta em voz, acompanhada de animação visual sincronizada.

A plataforma também utiliza o GPT-4o-mini para tradução de conteúdos, com cache Redis para reduzir chamadas externas e melhorar o desempenho.

## 🛠️ Tecnologias utilizadas

| Camada | Tecnologias |
|---|---|
| Backend | Python, Flask, Flask-SQLAlchemy, Flask-Migrate, Flask-Login, Flask-Limiter |
| Autenticação | Werkzeug scrypt, TOTP 2FA, PyOTP, QRCode e códigos de backup |
| IA — STT / Chat / TTS | OpenAI Whisper, GPT-4o-mini e OpenAI TTS |
| Tradução | OpenAI GPT-4o-mini, Redis, PT/EN/ES/FR |
| Internacionalização da UI | Catálogo próprio em Python (PT/EN) |
| Banco de dados | SQLite (desenvolvimento) e PostgreSQL (produção) |
| Cache e Rate Limit | Redis |
| Frontend | HTML5, CSS3 e JavaScript vanilla |
| Servidor de produção | Gunicorn, Nginx, systemd e Let's Encrypt |
| Acesso HTTPS público | Cloudflare Tunnel |
| Sensores físicos | DHT11/DHT22 e HC-SR04 |
| Hardware | Raspberry Pi 3 B/B+ (piloto) e Raspberry Pi 4 |
| Kiosk | Chromium fullscreen ou Fully Kiosk Browser (Android) |
| Testes | Pytest |

## 👥 Experiência do visitante

A interface foi desenvolvida para utilização em telas touch, priorizando uma navegação intuitiva e acessível.

O visitante pode:

- Consultar informações sobre a instituição.
- Interagir com o assistente virtual por voz ou texto.
- Explorar mapas e localizar pontos de interesse.
- Consultar lojas, produtos, animais e eventos.
- Participar de quizzes educativos.
- Avaliar anonimamente sua experiência.
- Acessar conteúdos em diferentes idiomas.

Os módulos e a identidade visual são adaptáveis conforme o tipo de instituição.

## 🖥️ Painel administrativo

O sistema possui uma área administrativa para gerenciamento das instituições, usuários, dispositivos e conteúdos.

O acesso é dividido em três níveis de permissão:

| Papel | Acesso |
|---|---|
| `super_admin` | Gerenciamento global de instituições, usuários, dispositivos, logs de auditoria e IA |
| `client_admin` | Acesso restrito à própria instituição, incluindo conteúdos e logs de IA |
| `operational` | Seleção de um cliente e totem ativo para iniciar a interface operacional |

### Recursos administrativos

- Gerenciamento de instituições.
- Cadastro e gerenciamento de usuários.
- Controle de permissões por perfil.
- Gerenciamento de dispositivos e respectivos acessos.
- Monitoramento de heartbeat dos totens.
- Consulta de logs de IA.
- Trilha de auditoria de ações administrativas.
- Configuração de conteúdos por instituição.

O `super_admin` é criado uma única vez por meio das variáveis de ambiente na primeira execução.

Os demais administradores são cadastrados pelo painel da plataforma. Senhas temporárias exigem alteração no primeiro acesso.

O perfil `operational` não possui acesso ao dashboard administrativo. Após o login, acessa `/operacional/`, seleciona um dispositivo ativo e inicia a interface do totem. A seleção fica armazenada na sessão assinada por até 8 horas.

O painel também oferece autenticação de dois fatores (2FA) via TOTP.

## 🏗️ Arquitetura e infraestrutura

A aplicação utiliza Flask como backend, responsável pelas rotas, regras de negócio, autenticação, integração com serviços externos e comunicação com o banco de dados.

A arquitetura foi organizada em módulos para facilitar a manutenção e permitir a expansão da plataforma.

Entre os principais componentes estão:

- **App Factory:** inicialização e configuração da aplicação.
- **Blueprints:** separação das rotas por funcionalidade.
- **Models:** representação das entidades e relacionamentos.
- **Services:** integrações externas e serviços reutilizáveis.
- **Registry Pattern:** registro de integrações com health-check.
- **Multi-Tenant:** isolamento de dados entre instituições.
- **Migrations:** controle de evolução do banco de dados.

### Fluxo simplificado

1. O visitante interage com a interface do totem.
2. O frontend envia a solicitação ao backend Flask.
3. O backend identifica a instituição e o contexto da interação.
4. A solicitação é processada pelas regras de negócio ou encaminhada à IA.
5. A resposta retorna à interface para exibição ou reprodução em áudio.

## 🍓 Implantação em Raspberry Pi

O projeto foi preparado para execução em hardware físico, utilizando Raspberry Pi como dispositivo de operação do totem.

**Ambiente do piloto:**

- Raspberry Pi 3 B/B+.
- Debian 13 (Trixie).
- Chromium em modo fullscreen.
- Fully Kiosk Browser como alternativa em dispositivos Android.
- systemd para gerenciamento dos serviços.
- Cloudflare Tunnel para disponibilização de acesso HTTPS.

O script `install_totem.sh` automatiza a configuração do ambiente kiosk, incluindo dependências, ambiente virtual, serviços e inicialização do navegador.

O Cloudflare Tunnel permite disponibilizar o acesso HTTPS sem depender de IP público ou certificado próprio no dispositivo, facilitando o funcionamento de recursos como microfone e câmera em diferentes redes.

## 🔐 Segurança

A aplicação possui mecanismos de autenticação, proteção de rotas, controle de acesso e segurança na comunicação entre os dispositivos.

| Recurso | Implementação |
|---|---|
| Senhas | Werkzeug scrypt e política mínima de 10 caracteres |
| Autenticação 2FA | TOTP com códigos de backup hashados |
| CSRF | Proteção dos formulários POST |
| Lockout | Bloqueio progressivo após falhas de login |
| Login | Verificação timing-safe para mitigar enumeração de usuários |
| Rate Limit | Flask-Limiter para controle de requisições |
| Headers HTTP | X-Frame-Options, X-Content-Type-Options e Referrer-Policy |
| Cookies | HttpOnly, SameSite=Lax e Secure em produção |
| Isolamento | Separação de dados por instituição |
| Auditoria | Registro de ações sensíveis em AdminAuditLog |
| Heartbeat | HMAC SHA-256, timestamp anti-replay e API key rotacionável |
| Criptografia | Fernet para dados sensíveis em repouso |

### Proteção dos dispositivos

O heartbeat dos totens utiliza HMAC SHA-256 com timestamp e proteção anti-replay, considerando uma janela de 5 minutos.

Os segredos de autenticação dos dispositivos podem ser rotacionados.

Os sensores físicos executam em um serviço separado do Gunicorn. A comunicação local com o Flask utiliza loopback e `X-Wake-Secret`, com comportamento fail-closed quando o segredo não está configurado.

Os segredos TOTP dos usuários e as chaves de API dos dispositivos são armazenados cifrados por meio de Fernet, utilizando `FIELD_ENCRYPTION_KEY`, com suporte à rotação dual-key.

## 📋 LGPD e experiência offline

A plataforma contempla recursos para transparência no tratamento de informações e continuidade da experiência em situações de instabilidade de rede.

- `/privacidade`: aviso sobre coleta, utilização da OpenAI, retenção e direitos do titular.
- **Consentimento de microfone:** modal apresentado antes do primeiro uso do recurso.
- **Service Worker:** cache de arquivos estáticos e disponibilização da página `/offline`.
- **Retenção de logs:** `InteractionLog` com período configurável, padrão de 90 dias.
- **Avaliações anônimas:** coleta de feedback sem identificação pessoal direta.

A limpeza dos registros pode ser executada pelo comando `flask purge-logs`, conforme agendamento operacional.

## 🌐 Tradução e internacionalização

A plataforma utiliza dois mecanismos complementares:

- **Tradução de conteúdo:** integração com GPT-4o-mini, com suporte a português, inglês, espanhol e francês e cache Redis.
- **Internacionalização da interface:** catálogo próprio em Python, com suporte a português e inglês, sem dependência do Babel.

Os serviços estão organizados em:

- `app/services/translation.py`
- `app/services/i18n.py`

## 📡 Sensores físicos

O piloto conta com dois sensores integrados por meio de um daemon independente do servidor Flask.

| Sensor | GPIO padrão | Função |
|---|---|---|
| HC-SR04 (ultrassônico) | TRIG=23, ECHO=24 | Detecta aproximação e altera o estado da sessão de IDLE para ACTIVE, acionando o áudio de boas-vindas |
| DHT11 / DHT22 | DATA=GPIO 4 | Monitora temperatura e umidade, alimentando os indicadores da interface e o heartbeat |

### Características da implementação

- **Daemon isolado:** `totem-sensors.service`, executado separadamente do worker Gunicorn.
- **Mock automático:** funcionamento simulado fora do Raspberry Pi, como em notebooks e ambientes de CI.
- **Modo de simulação:** `TOTEM_DISABLE_SENSORS=1` força o uso de mock no próprio Pi e suprime o overlay de proximidade.
- **Sem PIR:** a detecção de presença utiliza exclusivamente o HC-SR04.
- **Simuladores:** scripts para testar os fluxos sem necessidade de hardware físico.

Os drivers estão organizados em `app/sensors/`, com implementação individual para cada sensor.

## 💰 Controle de consumo da IA

Cada instituição possui uma configuração individual de `daily_ai_quota`, responsável por limitar o consumo diário de chamadas à IA.

O backend controla o número de chamadas e, quando o limite é atingido, retorna HTTP 429 sem realizar uma nova solicitação à OpenAI.

Isso permite controlar custos e disponibilidade da plataforma por instituição.

### Tratamento de erros da OpenAI

| Erro | HTTP | Comportamento |
|---|---|---|
| `APIConnectionError` / `APITimeoutError` | 503 | Retorna mensagem de indisponibilidade |
| `RateLimitError` | 429 | Informa excesso de requisições |
| `AuthenticationError` | 503 | Registra erro e informa indisponibilidade |
| Quota da instituição excedida | 429 | Informa que o limite diário foi atingido |

## 🚀 Início rápido — Desenvolvimento

### 1. Clonar o repositório

```bash
git clone https://github.com/joaop-n12/totem-flexmedia.git
cd totem-flexmedia
```

### 2. Criar o ambiente virtual

**Windows:**

```powershell
python -m venv venv
venv\Scripts\activate
```

**Linux / macOS:**

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Instalar as dependências

```bash
pip install -r requirements.txt
```

### 4. Configurar as variáveis de ambiente

**Windows:**

```powershell
Copy-Item .env.example .env
```

**Linux / macOS:**

```bash
cp .env.example .env
```

Edite o arquivo `.env` e configure as variáveis obrigatórias, incluindo `SECRET_KEY`, `OPENAI_API_KEY`, `SUPERADMIN_EMAIL` e `SUPERADMIN_PASSWORD`.

### 5. Aplicar as migrations

```bash
flask --app run.py db upgrade
```

### 6. Executar a aplicação

```bash
python run.py
```

Acesse:

```text
http://localhost:5000
```

O seed inicial é criado na primeira execução, conforme a configuração da aplicação.

Para instruções detalhadas de instalação em Raspberry Pi, VM Debian e troubleshooting, consulte [INSTALACAO.md](INSTALACAO.md).

## ⚙️ Variáveis de ambiente

| Variável | Obrigatória | Descrição |
|---|---|---|
| `SECRET_KEY` | Sim | Chave secreta do Flask |
| `FIELD_ENCRYPTION_KEY` | Sim em produção | Chave Fernet para cifrar TOTP e segredos de dispositivos |
| `OPENAI_API_KEY` | Sim | Chave de acesso à OpenAI |
| `SUPERADMIN_EMAIL` | Sim | E-mail do primeiro super admin |
| `SUPERADMIN_PASSWORD` | Sim | Senha inicial, mínimo de 12 caracteres |
| `DATABASE_URL` | Não | URL de conexão com o banco; padrão SQLite |
| `INTERACTION_LOG_RETENTION_DAYS` | Não | Retenção dos logs; padrão de 90 dias |
| `REDIS_URL` | Não | Endereço do Redis para cache e Flask-Limiter |
| `TOTEM_PUBLIC_URL` | Não | URL HTTPS pública do totem |
| `TOTEM_WAKE_SECRET` | Sim no Pi | Segredo local para comunicação entre daemon e Flask |
| `TOTEM_DISABLE_SENSORS` | Não | Define `1` para forçar sensores em modo mock |
| `DHT_MODEL` | Não | Modelo do sensor: `DHT11` ou `DHT22`; padrão `DHT22` |
| `REQUIRE_TOTP_FOR_SUPERADMIN` | Não | Define `1` para exigir 2FA de super admins; padrão habilitado |

Para gerar uma `SECRET_KEY`:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Para gerar uma chave Fernet:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Exemplo de URL PostgreSQL:

```text
postgresql+psycopg://user:password@host/flexmedia
```

## 🔗 URLs principais

### Totem público

| URL | Descrição |
|---|---|
| `/` | Redirecionamento para o seletor |
| `/selector` | Seleção de instituição |
| `/<slug>/` | Página inicial |
| `/<slug>/mapa` | Mapa interativo |
| `/<slug>/programacao` | Eventos |
| `/<slug>/animais/especies` | Catálogo de animais |
| `/<slug>/lojas` | Lojas |
| `/<slug>/produtos` | Produtos |
| `/<slug>/ia` | Assistente de IA |
| `/<slug>/quiz` | Quiz educativo |
| `/<slug>/rating` | Avaliação anônima |
| `/privacidade` | Aviso de privacidade e LGPD |
| `/offline` | Página de operação offline |
| `/sw.js` | Service Worker |
| `POST /api/locale` | Alteração do idioma da interface |

### Painel administrativo

| URL | Descrição |
|---|---|
| `/admin/login` | Login administrativo |
| `/admin/logout` | Encerramento da sessão |
| `/admin/totp/setup` | Configuração do segundo fator |
| `/admin/totp/backup-codes` | Códigos de recuperação |
| `/admin/platform/` | Dashboard super admin |
| `/admin/platform/institutions/` | Gerenciamento de instituições |
| `/admin/platform/users/` | Gerenciamento de usuários |
| `/admin/platform/devices/` | Gerenciamento de totens |
| `/admin/platform/audit` | Trilha de auditoria |
| `/admin/platform/logs` | Logs globais de IA |
| `/admin/institutions/<id>/` | Dashboard do client admin |

### Área operacional

| URL | Descrição |
|---|---|
| `/operacional/` | Seleção de cliente e totem ativo |
| `/operacional/iniciar` | Reabertura do último totem selecionado |

### API

| URL | Método | Descrição |
|---|---|---|
| `/api/voice` | POST | Áudio → resposta em áudio |
| `/api/chat` | POST | Texto → texto |
| `/<slug>/api/translate` | POST | Tradução PT/EN/ES/FR com cache Redis |
| `/api/translate/languages` | GET | Lista de idiomas suportados |
| `/<slug>/api/quiz/answer` | POST | Validação de resposta e retorno de curiosidade |
| `/<slug>/api/rating` | POST | Registro de avaliação anônima |
| `/<slug>/api/sync/version` | GET | Versão do conteúdo para sincronização |
| `/api/sync/snapshot` | GET | Snapshot com HMAC e ETag/304 |
| `/api/heartbeat` | POST | Heartbeat autenticado do dispositivo |
| `/api/local/wake` | POST | Comunicação local entre daemon e Flask |
| `/api/local/wake-stream` | GET | SSE para reação do kiosk à presença |
| `/api/session/state` | GET | Estado atual da máquina de estados |
| `/health` | GET | Verificação de liveness e readiness |

## 🧩 Módulos disponíveis

Os módulos podem ser habilitados conforme o tipo de instituição.

| Slug | Nome | Ícone |
|---|---|---|
| `home` | Home | ⊞ |
| `animais` | Catálogo de Animais | 🐾 |
| `mapa` | Mapa Interativo | 🗺️ |
| `programacao` | Programação | 📅 |
| `alimentacao` | Praça de Alimentação | 🍽️ |
| `ia` | Assistente IA | 💬 |
| `lojas` | Lojas | 🛍️ |
| `produtos` | Produtos | 💊 |

## 🧪 Testes

O projeto utiliza Pytest para validar funcionalidades, integrações e mecanismos de segurança.

Para executar os testes:

```bash
pip install -r requirements-dev.txt
pytest
```

A suíte contempla testes de:

- Inicialização e funcionamento básico.
- Interação por voz.
- Autenticação e 2FA.
- Segurança e controle de acesso.
- Heartbeat e dispositivos.
- Sensores físicos.
- Tradução e internacionalização.
- Métricas e isolamento multi-tenant.
- Sincronização de conteúdo.
- Quiz e avaliação de experiência.

As integrações com a OpenAI são mockadas durante os testes, evitando chamadas à API real.

## 📦 Estrutura do projeto

Visão geral dos principais diretórios e arquivos. Para a árvore completa e as regras de engenharia, consulte [CLAUDE.md](CLAUDE.md).

```text
totem_flexmedia/
├── app/
│   ├── __init__.py              # App factory + comandos CLI
│   ├── extensions.py            # db, migrate, login_manager, limiter
│   ├── crypto.py                # Helpers de criptografia Fernet
│   ├── helpers.py               # CSRF, decoradores e funções auxiliares
│   ├── twofa.py                 # TOTP + códigos de backup
│   ├── seed.py                  # Seed inicial e super admin
│   ├── models/                  # Models e entidades do sistema
│   ├── routes/
│   │   ├── core.py              # Totem público e service worker
│   │   ├── zoo.py               # Módulo zoológico
│   │   ├── shopping.py          # Módulo shopping
│   │   ├── pharmacy.py          # Módulo farmácia
│   │   ├── voice.py             # IA por voz e texto
│   │   ├── translate.py         # Tradução
│   │   ├── quiz.py               # Quiz educativo
│   │   ├── rating.py             # Avaliações
│   │   ├── sync.py               # Sincronização e snapshots
│   │   ├── admin_auth.py         # Login e autenticação 2FA
│   │   ├── admin_platform.py     # Administração global
│   │   ├── admin_institution.py  # Administração por instituição
│   │   ├── devices.py            # Dispositivos e heartbeat
│   │   └── health.py             # Health checks
│   ├── services/
│   │   ├── integrations.py       # Registry de integrações
│   │   ├── translation.py        # Tradução com OpenAI e Redis
│   │   ├── metrics.py            # Agregações de métricas
│   │   └── i18n.py               # Internacionalização PT/EN
│   └── sensors/
│       ├── base.py
│       ├── dht22.py
│       ├── hcsr04.py
│       └── daemon.py             # Daemon de sensores
├── templates/                   # Templates e interfaces
├── static/                      # CSS, JavaScript, imagens e uploads
├── migrations/                  # Migrations Alembic
├── tests/                       # Suítes de testes automatizados
├── scripts/
│   ├── totem_sensor_daemon.py   # Entry point do daemon
│   ├── simular_sensores.sh      # Simulador para Linux/Pi
│   ├── simular_sensores.ps1     # Simulador para Windows
│   └── teste_dht11.py           # Teste isolado do DHT
├── deploy/
│   ├── install_production.sh    # Instalação de produção
│   ├── install_cloudflared.sh   # Configuração Cloudflare Tunnel
│   ├── rotate_secrets.sh        # Rotação de segredos
│   ├── backup.sh                # Backup automatizado
│   ├── nginx.conf.template
│   ├── totem-flexmedia.service
│   └── totem-sensors.service
├── docs/
│   ├── OPERACAO.md              # Manual operacional
│   └── AUDITORIA_SEGURANCA.md   # Histórico de auditoria
├── data/                        # Seeds JSON
├── instance/                    # SQLite e uploads (gitignored)
├── logs/                        # Logs rotativos (gitignored)
├── install_totem.sh             # Configuração do Raspberry Pi
├── INSTALACAO.md                # Guia de instalação
├── CLAUDE.md                    # Mapa e regras de engenharia
├── config.py
├── run.py
├── wsgi.py
├── gunicorn.conf.py
├── pytest.ini
├── requirements.txt
├── requirements-dev.txt
├── requirements-pi.txt
└── .env.example
```

## 🚀 Deploy e operação

A documentação operacional detalhada está disponível em [docs/OPERACAO.md](docs/OPERACAO.md).

| Script | Função |
|---|---|
| `install_totem.sh` | Configuração do Raspberry Pi como kiosk |
| `deploy/install_cloudflared.sh` | HTTPS público via Cloudflare Tunnel |
| `deploy/install_production.sh` | Instalação on-prem com Nginx, Gunicorn e Let's Encrypt |
| `deploy/rotate_secrets.sh` | Rotação assistida de segredos |
| `deploy/backup.sh` | Backup diário com retenção de 14 dias |
| `scripts/simular_sensores.sh` | Simulação de sensores em Linux/Pi |
| `scripts/simular_sensores.ps1` | Simulação de sensores no Windows |
| `scripts/totem_sensor_daemon.py` | Inicialização do daemon de sensores |

## 📄 Documentação adicional

- [INSTALACAO.md](INSTALACAO.md) — guia de instalação e configuração.
- [docs/OPERACAO.md](docs/OPERACAO.md) — manual operacional do Raspberry Pi.
- [CLAUDE.md](CLAUDE.md) — estrutura detalhada e regras de engenharia.
- [docs/AUDITORIA_SEGURANCA.md](docs/AUDITORIA_SEGURANCA.md) — histórico de auditoria de segurança.

## 📜 Licença

Projeto acadêmico desenvolvido durante o **Challenge FIAP em parceria com a FlexMedia**.

Uso restrito conforme acordo entre as partes.

---

**Totem FlexMedia — tecnologia e inteligência artificial aproximando instituições e pessoas.**
