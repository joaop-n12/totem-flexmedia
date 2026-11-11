# Totem FlexMedia — Plataforma White Label Multi-Instituições

Plataforma de totens interativos inteligentes, desenvolvida para o **Challenge FIAP em parceria com a FlexMedia**.

Uma solução white label, multi-instituições, que combina inteligência artificial, interação por voz e texto, mapas interativos e gerenciamento centralizado de conteúdo.

---

## Sobre o projeto

O **Totem FlexMedia** é uma plataforma desenvolvida para transformar totens convencionais em pontos de atendimento e informação inteligentes.

A solução permite atender diferentes tipos de estabelecimentos utilizando uma única base de código, com identidade visual, conteúdos e funcionalidades configuráveis para cada instituição.

Entre os cenários de aplicação estão:

- Shopping centers;
- Zoológicos e aquários;
- Museus e parques;
- Farmácias;
- Centros comerciais e instituições.

Cada instituição possui seu próprio ambiente, com módulos específicos e um assistente de inteligência artificial contextualizado com seus conteúdos.

O sistema foi desenvolvido com arquitetura multi-tenant, permitindo administrar diferentes instituições, usuários e dispositivos de forma centralizada.

## Principais funcionalidades

### Experiência do visitante
- Interface interativa adaptada à identidade visual de cada instituição.
- Assistente de IA com interação por voz e texto.
- Reconhecimento de fala utilizando OpenAI Whisper.
- Respostas inteligentes utilizando GPT-4o-mini.
- Conversão de respostas em áudio com OpenAI TTS.
- Mapas interativos para localização de estabelecimentos e pontos de interesse.
- Filtros por andar e categorias de conteúdo.
- Catálogos de animais, lojas, produtos e eventos.
- Quiz educativo com validação de respostas no servidor.
- Avaliação da experiência do visitante.
- Suporte a diferentes idiomas.
- Interface preparada para operação em telas touchscreen.

### Painel administrativo
- Gerenciamento centralizado de instituições.
- Cadastro e gerenciamento de usuários.
- Controle de dispositivos e totens.
- Gerenciamento de conteúdos por instituição.
- Visualização de métricas e registros de interação.
- Controle de permissões por perfil de usuário.
- Autenticação com segundo fator (2FA).
- Trilha de auditoria para ações administrativas.

### Operação dos totens
- Seleção do cliente e dispositivo pelo operador.
- Inicialização da interface específica do equipamento.
- Execução em modo kiosk, com navegação em tela cheia.
- Comunicação com servidor para sincronização de conteúdo.
- Monitoramento de disponibilidade por heartbeat.
- Integração com sensores físicos para detecção de presença e telemetria.
- Possibilidade de operação em diferentes ambientes e dispositivos.

---

## Inteligência Artificial

A plataforma integra serviços da OpenAI para proporcionar uma experiência conversacional por voz e texto.

### Fluxo de interação por voz

1. O visitante toca no botão de interação e faz uma pergunta.
2. O áudio é enviado para transcrição pelo OpenAI Whisper.
3. A pergunta é processada pelo GPT-4o-mini, considerando o contexto da instituição.
4. A resposta é convertida em áudio pelo OpenAI TTS.
5. O visitante recebe a resposta em voz, acompanhada de elementos visuais da interface.

Também existe a possibilidade de interação exclusivamente por texto.

### Tradução e internacionalização

- Tradução dinâmica de conteúdo utilizando OpenAI.
- Suporte a português, inglês, espanhol e francês na tradução de conteúdo.
- Interface com catálogo de internacionalização em português e inglês.
- Cache de traduções para reduzir chamadas externas.

---

## Tecnologias utilizadas

| Camada | Tecnologias |
|---|---|
| Backend | Python, Flask |
| ORM e banco | Flask-SQLAlchemy, SQLite, PostgreSQL |
| Migrações | Flask-Migrate, Alembic |
| Autenticação | Flask-Login, Werkzeug, TOTP 2FA |
| Inteligência Artificial | OpenAI Whisper, GPT-4o-mini, OpenAI TTS |
| Tradução | OpenAI API, Redis |
| Frontend | HTML5, CSS3, JavaScript |
| Segurança | CSRF, Fernet, HMAC SHA-256, rate limiting |
| Infraestrutura | Gunicorn, Nginx, systemd |
| Acesso externo | Cloudflare Tunnel |
| Hardware | Raspberry Pi 3 B/B+ e Raspberry Pi 4 |
| Sensores | DHT11/DHT22 e HC-SR04 |
| Navegador kiosk | Chromium e Fully Kiosk Browser |
| Testes | Pytest |

---

## Arquitetura da solução

A aplicação foi organizada para separar a experiência pública, a administração da plataforma e a operação dos equipamentos.

| Perfil | Responsabilidade |
|---|---|
| `super_admin` | Administração global de instituições, usuários, dispositivos, métricas e auditoria. |
| `client_admin` | Gerenciamento de conteúdos e informações da própria instituição. |
| `operational` | Seleção do cliente e do equipamento e inicialização da interface do totem. |
| Visitante | Utilização dos módulos públicos e interação com a inteligência artificial. |

### Arquitetura multi-tenant

Cada instituição possui configurações e conteúdos próprios, permitindo personalizar a experiência sem precisar manter uma aplicação independente para cada cliente.

A separação de permissões também impede que administradores de uma instituição acessem os dados de outra.

---

## Implantação em hardware real

Um dos diferenciais do projeto é sua preparação para execução em equipamentos físicos.

O piloto foi configurado em um **Raspberry Pi 3 B**, utilizando Debian 13 (Trixie), com execução da aplicação e interface em modo kiosk.

### Ambiente de implantação

- Raspberry Pi 3 B.
- Debian 13.
- Python e Flask.
- Banco de dados SQLite no ambiente piloto.
- Fully Kiosk Browser para execução da interface.
- Cloudflare Tunnel para disponibilização de acesso HTTPS externo.
- systemd para gerenciamento de serviços.
- Daemon independente para integração com sensores físicos.

### Acesso externo com Cloudflare Tunnel

A integração com Cloudflare Tunnel permite disponibilizar a aplicação por HTTPS sem necessidade de expor diretamente o endereço IP da rede local.

Essa configuração também permite utilizar recursos do navegador que dependem de contexto seguro, como microfone e câmera, respeitando as permissões concedidas pelo navegador.

### Operação do equipamento

O sistema possui uma estrutura para inicialização e gerenciamento do totem, incluindo:

- Inicialização automática dos serviços.
- Execução da interface em modo kiosk.
- Comunicação entre o equipamento e o servidor.
- Monitoramento periódico de disponibilidade.
- Sincronização de conteúdo.
- Integração com sensores.

---

## Início rápido — Ambiente de desenvolvimento

### 1. Clonar o repositório

```bash
git clone https://github.com/SEU-USUARIO/SEU-REPOSITORIO.git
cd totem_flexmedia
```

### 2. Criar ambiente virtual

**Windows:**

```bash
python -m venv venv
venv\Scripts\activate
```

**Linux/macOS:**

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Instalar dependências

```bash
pip install -r requirements.txt
```

### 4. Configurar variáveis de ambiente

```bash
cp .env.example .env
```

Configure as credenciais necessárias, incluindo a chave da OpenAI e as configurações de segurança.

### 5. Preparar o banco de dados

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

Para instalação em Raspberry Pi, configuração do Cloudflare Tunnel e operação em produção, consulte `INSTALACAO.md` e `docs/OPERACAO.md`.

---

## Variáveis de ambiente

| Variável | Descrição |
|---|---|
| `SECRET_KEY` | Chave de segurança da aplicação Flask. |
| `FIELD_ENCRYPTION_KEY` | Chave Fernet para criptografia de dados sensíveis. |
| `OPENAI_API_KEY` | Chave de acesso à API da OpenAI. |
| `SUPERADMIN_EMAIL` | E-mail do administrador principal. |
| `SUPERADMIN_PASSWORD` | Senha inicial do administrador. |
| `DATABASE_URL` | URL de conexão com o banco de dados. |
| `REDIS_URL` | Configuração do Redis para cache e rate limiting. |
| `TOTEM_PUBLIC_URL` | Endereço HTTPS público da aplicação. |
| `TOTEM_WAKE_SECRET` | Segredo de comunicação com o daemon de sensores. |
| `TOTEM_DISABLE_SENSORS` | Desativa a integração com sensores físicos. |
| `DHT_MODEL` | Modelo do sensor de temperatura e umidade. |
| `REQUIRE_TOTP_FOR_SUPERADMIN` | Define a obrigatoriedade de 2FA para super administradores. |

Consulte `.env.example` para verificar os valores e configurações esperados.

---

## Principais rotas

### Interface pública

| Rota | Descrição |
|---|---|
| `/` | Redirecionamento inicial. |
| `/selector` | Seleção de instituição. |
| `/<slug>/` | Página inicial da instituição. |
| `/<slug>/mapa` | Mapa interativo. |
| `/<slug>/programacao` | Programação e eventos. |
| `/<slug>/animais/especies` | Catálogo de animais. |
| `/<slug>/lojas` | Catálogo de lojas. |
| `/<slug>/produtos` | Catálogo de produtos. |
| `/<slug>/ia` | Assistente de inteligência artificial. |
| `/<slug>/quiz` | Quiz educativo. |
| `/<slug>/rating` | Avaliação da experiência. |
| `/privacidade` | Aviso de privacidade e LGPD. |

### Administração

| Rota | Descrição |
|---|---|
| `/admin/login` | Autenticação administrativa. |
| `/admin/platform/` | Painel global. |
| `/admin/platform/institutions/` | Gerenciamento de instituições. |
| `/admin/platform/users/` | Gerenciamento de usuários. |
| `/admin/platform/devices/` | Gerenciamento de dispositivos. |
| `/admin/platform/audit` | Registros de auditoria. |
| `/admin/platform/logs` | Logs globais de IA. |
| `/admin/institutions/<id>/` | Painel da instituição. |

### Operacional

| Rota | Descrição |
|---|---|
| `/operacional/` | Seleção de cliente e dispositivo. |
| `/operacional/iniciar` | Inicialização do último equipamento selecionado. |

### API

| Rota | Método | Descrição |
|---|---|---|
| `/api/voice` | POST | Processamento de áudio e resposta em voz. |
| `/api/chat` | POST | Interação por texto. |
| `/<slug>/api/translate` | POST | Tradução de conteúdo. |
| `/api/translate/languages` | GET | Idiomas suportados. |
| `/<slug>/api/quiz/answer` | POST | Validação de respostas do quiz. |
| `/<slug>/api/rating` | POST | Registro de avaliações. |
| `/<slug>/api/sync/version` | GET | Verificação da versão do conteúdo. |
| `/api/sync/snapshot` | GET | Sincronização de conteúdo. |
| `/api/heartbeat` | POST | Monitoramento do dispositivo. |
| `/api/local/wake` | POST | Comunicação local com sensores. |
| `/api/session/state` | GET | Estado da sessão do totem. |
| `/health` | GET | Verificação de disponibilidade. |

---

## Módulos disponíveis

| Módulo | Funcionalidade |
|---|---|
| Home | Página inicial personalizada. |
| Animais | Catálogo de espécies e informações educativas. |
| Mapa | Localização de pontos de interesse. |
| Programação | Eventos e atividades. |
| Alimentação | Praça de alimentação. |
| IA | Assistente inteligente. |
| Lojas | Catálogo de estabelecimentos. |
| Produtos | Catálogo de produtos. |

Os módulos são configuráveis de acordo com o segmento e as necessidades de cada instituição.

---

## Sensores físicos

A plataforma possui integração com sensores para ampliar a interação entre o visitante e o equipamento.

| Sensor | GPIO | Funcionalidade |
|---|---|---|
| HC-SR04 | TRIG 23 / ECHO 24 | Detecção de aproximação e presença. |
| DHT11/DHT22 | DATA 4 | Monitoramento de temperatura e umidade. |

O processamento dos sensores é executado por um daemon independente do servidor Flask, gerenciado pelo systemd.

Também existem simuladores para testar os fluxos sem necessidade de conexão com o hardware físico.

---

## Segurança e LGPD

A plataforma possui mecanismos de proteção e controle de acesso:

- Senhas protegidas com hash Werkzeug scrypt.
- Autenticação de dois fatores (TOTP).
- Códigos de recuperação armazenados com hash.
- Proteção CSRF em formulários.
- Limitação de requisições (rate limiting).
- Controle de acesso por perfil.
- Isolamento de dados entre instituições.
- Auditoria de operações administrativas.
- Comunicação autenticada entre dispositivos e servidor.
- Criptografia Fernet para dados sensíveis.
- Retenção configurável de registros de interação.
- Aviso de privacidade e consentimento para utilização do microfone.

A integração com serviços externos de IA também é considerada na política de privacidade da aplicação.

---

## Experiência offline

A aplicação possui suporte a recursos de funcionamento offline por meio de Service Worker.

- Cache de arquivos estáticos.
- Página específica para indisponibilidade de conexão.
- Estrutura de sincronização de conteúdo.
- Verificação periódica de atualização dos dados.

As funcionalidades que dependem da API da OpenAI ou de comunicação com o servidor exigem conectividade.

---

## Testes

Para instalar as dependências de desenvolvimento:

```bash
pip install -r requirements-dev.txt
```

Executar os testes:

```bash
pytest
```

As chamadas à OpenAI são simuladas nos testes para evitar consumo de API e dependência de serviços externos.

---

## Estrutura do projeto

```text
totem_flexmedia/
├── app/
│   ├── __init__.py
│   ├── extensions.py
│   ├── crypto.py
│   ├── helpers.py
│   ├── twofa.py
│   ├── seed.py
│   ├── models/
│   ├── routes/
│   │   ├── core.py
│   │   ├── zoo.py
│   │   ├── shopping.py
│   │   ├── pharmacy.py
│   │   ├── voice.py
│   │   ├── translate.py
│   │   ├── quiz.py
│   │   ├── rating.py
│   │   ├── sync.py
│   │   ├── admin_auth.py
│   │   ├── admin_platform.py
│   │   ├── admin_institution.py
│   │   ├── devices.py
│   │   └── health.py
│   ├── services/
│   │   ├── integrations.py
│   │   ├── translation.py
│   │   ├── metrics.py
│   │   └── i18n.py
│   └── sensors/
│       ├── base.py
│       ├── dht22.py
│       ├── hcsr04.py
│       └── daemon.py
├── templates/
├── static/
├── migrations/
├── tests/
├── scripts/
├── deploy/
├── docs/
├── data/
├── instance/
├── logs/
├── install_totem.sh
├── INSTALACAO.md
├── CLAUDE.md
├── config.py
├── run.py
├── wsgi.py
├── requirements.txt
├── requirements-dev.txt
├── requirements-pi.txt
└── .env.example
```

---

## Documentação complementar

| Arquivo | Conteúdo |
|---|---|
| `INSTALACAO.md` | Instalação e configuração do ambiente. |
| `docs/OPERACAO.md` | Operação do Raspberry Pi, manutenção e backups. |
| `docs/AUDITORIA_SEGURANCA.md` | Histórico de auditoria e segurança. |
| `CLAUDE.md` | Arquitetura, estrutura e regras de engenharia. |

### Scripts de implantação

| Script | Finalidade |
|---|---|
| `install_totem.sh` | Preparação do Raspberry Pi para operação kiosk. |
| `deploy/install_cloudflared.sh` | Configuração do Cloudflare Tunnel. |
| `deploy/install_production.sh` | Instalação com Nginx e Gunicorn. |
| `deploy/rotate_secrets.sh` | Rotação de chaves e segredos. |
| `deploy/backup.sh` | Backup e retenção de dados. |
| `scripts/totem_sensor_daemon.py` | Inicialização do daemon de sensores. |
| `scripts/simular_sensores.sh` | Simulação de sensores no Linux. |
| `scripts/simular_sensores.ps1` | Simulação de sensores no Windows. |

---

## Licença

Projeto acadêmico desenvolvido para o **Challenge FIAP em parceria com a FlexMedia**.

Uso restrito conforme os termos e acordos estabelecidos entre as partes.
