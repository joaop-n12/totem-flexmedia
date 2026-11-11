# Totem FlexMedia — Plataforma White Label Multi-Instituições

> Projeto desenvolvido para o **Challenge FIAP**, em parceria com a **FlexMedia**.  
> Plataforma de totens interativos multi-instituições, com inteligência artificial, interação por voz e texto e gerenciamento centralizado.

---

## 💡 Sobre o projeto

O **Totem FlexMedia** é uma plataforma desenvolvida para transformar totens físicos em pontos de atendimento e interação inteligentes.

A solução utiliza inteligência artificial para oferecer experiências interativas e personalizadas em diferentes ambientes, como shoppings, zoológicos, museus e outros estabelecimentos.

Sua arquitetura **White Label e Multi-Tenant** permite que diferentes instituições utilizem a mesma plataforma, com identidade visual, conteúdos e configurações próprias.

O projeto também contempla operação em hardware de baixo custo, incluindo implantação em Raspberry Pi.

## ✨ Funcionalidades

- **Assistente com IA:** interação por voz e texto para responder dúvidas e orientar visitantes.
- **Reconhecimento de voz:** conversão de fala em texto para interação com o assistente.
- **Síntese de voz:** respostas faladas para proporcionar uma experiência mais acessível e natural.
- **Mapa interativo:** navegação por ambientes, setores e diferentes andares.
- **Quiz interativo:** atividades para engajar visitantes.
- **Avaliação de experiência:** coleta de feedback dos usuários.
- **Suporte a múltiplos idiomas:** experiência adaptável a diferentes públicos.
- **Conteúdo personalizado:** informações específicas de cada instituição.
- **Modo offline:** recursos de operação e acesso a conteúdos previamente disponibilizados.

## 👥 Experiência do visitante

A interface foi desenvolvida para ser simples, intuitiva e adequada ao uso em telas touch.

O visitante pode:

- Consultar informações sobre o estabelecimento.
- Interagir com o assistente virtual.
- Explorar mapas e localizar pontos de interesse.
- Acessar informações de lojas, produtos, animais ou eventos, conforme o ambiente.
- Participar de quizzes e avaliar sua experiência.

## 🖥️ Painel administrativo

A plataforma conta com uma área administrativa para gerenciamento e configuração dos ambientes.

Entre os recursos previstos na estrutura do projeto estão:

- Gerenciamento de instituições e seus respectivos conteúdos.
- Administração de usuários e permissões.
- Configuração e acompanhamento dos dispositivos.
- Organização de informações e módulos.
- Monitoramento operacional dos totens.

A aplicação utiliza diferentes níveis de acesso, incluindo perfis administrativos e operacionais.

## 🤖 Inteligência artificial

A integração com os serviços da OpenAI permite oferecer recursos de interação inteligente.

**Recursos utilizados:**
- **Whisper:** reconhecimento e transcrição de voz.
- **GPT-4o-mini:** processamento de perguntas e geração de respostas.
- **OpenAI Text-to-Speech:** conversão das respostas em áudio.

O objetivo é proporcionar uma interação mais natural, reduzindo a necessidade de navegação manual pelos conteúdos.

## 🛠️ Tecnologias utilizadas

| Categoria | Tecnologias |
|---|---|
| Backend | Python, Flask |
| Frontend | HTML5, CSS3, JavaScript |
| Banco de dados | SQLite |
| Inteligência Artificial | OpenAI API |
| Reconhecimento de voz | Whisper |
| Síntese de voz | OpenAI TTS |
| Controle de versão | Git e GitHub |
| Hardware | Raspberry Pi |
| Infraestrutura | Linux, Cloudflare Tunnel |

## 🏗️ Arquitetura do projeto

A aplicação utiliza uma arquitetura baseada em Flask, responsável por gerenciar as rotas, regras de negócio, integração com serviços externos e comunicação com o banco de dados.

De forma geral, o fluxo funciona assim:

1. O visitante interage com a interface do totem.
2. A aplicação recebe a solicitação por texto ou voz.
3. O backend processa a requisição.
4. Quando necessário, a solicitação é encaminhada aos serviços de IA.
5. A resposta é apresentada na interface ou reproduzida em áudio.

## 🍓 Implantação em Raspberry Pi

O projeto também foi preparado para execução em hardware físico, utilizando Raspberry Pi como dispositivo de operação do totem.

**Ambiente utilizado no piloto:**
- Raspberry Pi 3 Model B.
- Debian 13 (Trixie).
- Navegador em modo kiosk.
- Fully Kiosk Browser.
- Cloudflare Tunnel para acesso remoto.

Essa implementação permite executar a interface em uma tela dedicada, mantendo o dispositivo configurado para uso contínuo.

## 🚀 Como executar o projeto

### 1. Clonar o repositório

```bash
git clone https://github.com/joaop-n12/totem-flexmedia.git
cd totem-flexmedia
```

### 2. Criar um ambiente virtual

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

Crie um arquivo `.env` a partir do exemplo:

**Windows:**

```powershell
Copy-Item .env.example .env
```

**Linux / macOS:**

```bash
cp .env.example .env
```

Configure as variáveis necessárias, incluindo a chave da API da OpenAI.

### 5. Executar a aplicação

```bash
python app.py
```

Acesse no navegador:

```text
http://127.0.0.1:5000
```

> Os comandos podem variar conforme a configuração e os módulos habilitados no ambiente.

## 🔐 Segurança

A aplicação contempla mecanismos de proteção e controle de acesso, incluindo:

- Autenticação de usuários.
- Controle de permissões por perfil.
- Proteção de rotas administrativas.
- Gerenciamento de configurações sensíveis por variáveis de ambiente.
- Separação de dados por instituição.

**Importante:** não compartilhe chaves de API, senhas ou arquivos `.env` no repositório.

## 📂 Estrutura do projeto

A organização pode variar conforme a versão e os módulos habilitados. De forma geral, o projeto está dividido entre:

- **Backend:** rotas, serviços e regras de negócio.
- **Frontend:** páginas, componentes, estilos e scripts.
- **Banco de dados:** persistência das informações.
- **IA:** integrações com os serviços da OpenAI.
- **Configurações:** variáveis de ambiente e parâmetros de execução.
- **Infraestrutura:** arquivos e configurações para implantação.

## 🎯 Objetivo do projeto

O Totem FlexMedia representa a aplicação prática de conhecimentos em desenvolvimento web, inteligência artificial, integração de APIs, bancos de dados e implantação em hardware.

Mais do que uma interface interativa, a proposta é oferecer uma solução flexível, escalável e adaptável a diferentes tipos de instituições.

---

**Desenvolvido durante o Challenge FIAP em parceria com a FlexMedia.**
