# Manual de Operação — Totem FlexMedia

Guia prático para quem opera a plataforma em produção. Cobre quatro fluxos:

1. [Instalação no Raspberry Pi](#1-instalação-no-raspberry-pi)
2. [Troca de chaves e segredos](#2-troca-de-chaves-e-segredos)
3. [Restauração de backup](#3-restauração-de-backup)
4. [Adicionar uma nova instituição](#4-adicionar-uma-nova-instituição)

Todos os caminhos assumem a instalação padrão em `/opt/totem-flexmedia`
com usuário de serviço `totem`.

---

## 1. Instalação no Raspberry Pi

A instalação tem **duas camadas independentes**:

| Camada   | O que instala                                        | Script                          |
|----------|------------------------------------------------------|---------------------------------|
| Servidor | Flask + Gunicorn + Nginx + SSL + backup diário       | `deploy/install_production.sh`  |
| Kiosk    | Chromium fullscreen + watchdog + autostart do totem  | `install_totem.sh`              |

Em cenário de totem único, normalmente **ambos** rodam no mesmo Raspberry.
Em cenário multi-totem, o servidor fica centralizado e cada Raspberry roda
apenas a camada kiosk apontando para a URL pública.

### 1.1 Pré-requisitos

- **Raspberry Pi 3 Model B / B+** (plataforma homologada do piloto).
  Pi 4 também é suportado sem alterações.
- Raspberry Pi OS **32 bits (Bullseye ou Bookworm)** — o Pi 3 tem 1 GB de
  RAM e performa melhor no SO de 32 bits. Evite a imagem 64 bits nele.
- Cartão SD classe 10, **mínimo 16 GB** (recomendado 32 GB) — espaço para
  SO, venv, uploads e 14 dias de backup.
- Fonte oficial de 2.5 A (o Pi 3 trava em undervoltage com fonte fraca).
- Acesso root (`sudo`).
- Rede com internet (para CDNs, OpenAI e Let's Encrypt).
  Preferir **cabo Ethernet** — o Wi-Fi do Pi 3 é 2.4 GHz e instável
  em ambientes com muitos dispositivos (shopping, zoo).
- Um domínio apontado para o IP (registro A) se for usar SSL — ex: `totem.cliente.com.br`.
- Portas 80 e 443 liberadas no roteador/firewall.
- Chave `OPENAI_API_KEY` em mãos.

### 1.1.1 Ajustes recomendados para o Pi 3

O Pi 3 é limitado (CPU ARMv7 4 núcleos, 1 GB RAM). Antes de instalar:

```bash
# Swap de 1 GB — evita OOM durante pip install de pacotes pesados
sudo dphys-swapfile swapoff
sudo sed -i 's/^CONF_SWAPSIZE=.*/CONF_SWAPSIZE=1024/' /etc/dphys-swapfile
sudo dphys-swapfile setup
sudo dphys-swapfile swapon

# GPU com pouca memória (sobra mais RAM para a app)
sudo sed -i '/^gpu_mem=/d' /boot/config.txt
echo 'gpu_mem=64' | sudo tee -a /boot/config.txt

# Desligar serviços desnecessários no kiosk
sudo systemctl disable bluetooth hciuart triggerhappy
```

Com o servidor **e** o kiosk no mesmo Pi 3, use apenas **1 worker
Gunicorn** (já é o default). Em cenário com muito tráfego, centralize
o servidor em outro host e deixe o Pi 3 só como kiosk.

### 1.2 Passo a passo — servidor

```bash
# 1) Clone ou copie o projeto para o Raspberry
git clone <repo> ~/Totem_Flexmedia
cd ~/Totem_Flexmedia

# 2) Rode o instalador de produção (pedirá domínio, e-mail e senhas)
sudo bash deploy/install_production.sh
```

O script executa, de ponta a ponta:

- Instala Python, Nginx, Redis, SQLite, Certbot e cron.
- Cria o usuário de serviço `totem` e o diretório `/opt/totem-flexmedia`.
- Copia os arquivos, cria o virtualenv e instala `requirements.txt`.
- Gera `.env` com `SECRET_KEY` aleatória (pergunta `OPENAI_API_KEY`,
  e-mail e senha do super admin, escolha de SQLite local ou Postgres externo).
- Roda `flask db upgrade` e `flask seed` (idempotente — seguro em reinstalações).
- Habilita o serviço `totem-flexmedia.service` (Gunicorn + systemd).
- Configura Nginx a partir do template e emite certificado Let's Encrypt.
- Agenda o `deploy/backup.sh` no cron às **03:00** diariamente (retenção 14 dias).

Ao final o admin está em `https://<dominio>/admin/login`.

### 1.3 Passo a passo — kiosk

Em cada Raspberry que vai exibir o totem:

```bash
sudo bash install_totem.sh
```

Esse script configura:

- Chromium em modo fullscreen apontando para a URL do totem.
- Unclutter para esconder o cursor do mouse.
- Watchdog para reiniciar o navegador em caso de travamento.
- Autostart no LXDE/GNOME para subir após o boot.
- Serviço systemd com `Restart=always`.

### 1.4 Verificação

```bash
systemctl status totem-flexmedia      # deve estar "active (running)"
journalctl -u totem-flexmedia -f      # logs ao vivo
curl -I https://<dominio>             # deve retornar 200
```

---

## 2. Troca de chaves e segredos

Todos os segredos vivem em **um único arquivo**: `/opt/totem-flexmedia/.env`
(permissão `600`, dono `totem`). Nunca comite esse arquivo.

### 2.1 Trocar a `OPENAI_API_KEY`

```bash
sudo -u totem nano /opt/totem-flexmedia/.env
# altere a linha: OPENAI_API_KEY=sk-...
sudo systemctl restart totem-flexmedia
```

Teste em seguida: abra o totem → botão de voz → faça uma pergunta.
Se a chave estiver inválida, `app/routes/voice.py` trata
`AuthenticationError` → retorna 503 e loga em `logs/`.

### 2.2 Trocar a `SECRET_KEY` do Flask

> **Atenção:** trocar invalida todas as sessões ativas (todo mundo precisa
> logar de novo). Faça fora do horário de pico.

```bash
NEW=$(python3 -c "import secrets; print(secrets.token_hex(32))")
sudo -u totem sed -i "s/^SECRET_KEY=.*/SECRET_KEY=$NEW/" /opt/totem-flexmedia/.env
sudo systemctl restart totem-flexmedia
```

### 2.3 Trocar a senha do super admin

Via CLI do Flask:

```bash
cd /opt/totem-flexmedia
sudo -u totem -E bash -c '
  source venv/bin/activate
  set -a; source .env; set +a
  export FLASK_APP=wsgi.py
  flask shell
'
```

Dentro do `flask shell`:

```python
from app.extensions import db
from app.models.user import User
u = User.query.filter_by(email="super@exemplo.com").first()
u.set_password("NovaSenhaForte123!")
db.session.commit()
```

### 2.4 Renovar certificado SSL

O `certbot.timer` renova automaticamente. Para forçar:

```bash
sudo certbot renew --force-renewal
sudo systemctl reload nginx
```

---

## 3. Restauração de backup

Os backups ficam em `/opt/totem-flexmedia/backups/` com nome
`flexmedia-YYYYMMDD-HHMMSS.{db,sql}.gz` (ver `deploy/backup.sh`).

### 3.1 Identificar o backup desejado

```bash
ls -lht /opt/totem-flexmedia/backups/
```

### 3.2 Restaurar SQLite (instalação padrão)

```bash
# 1) Pare o serviço para evitar escrita concorrente
sudo systemctl stop totem-flexmedia

# 2) Faça snapshot do banco atual (segurança)
sudo cp /opt/totem-flexmedia/instance/flexmedia.db \
        /opt/totem-flexmedia/instance/flexmedia.db.bak-$(date +%s)

# 3) Descompacte e substitua
BACKUP=/opt/totem-flexmedia/backups/flexmedia-20260419-030000.db.gz
sudo -u totem bash -c "gunzip -c $BACKUP > /opt/totem-flexmedia/instance/flexmedia.db"

# 4) Suba o serviço
sudo systemctl start totem-flexmedia
sudo systemctl status totem-flexmedia
```

### 3.3 Restaurar Postgres

```bash
sudo systemctl stop totem-flexmedia

BACKUP=/opt/totem-flexmedia/backups/flexmedia-20260419-030000.sql.gz
# O DATABASE_URL precisa apontar para um banco limpo (ou drop/recreate antes)
source /opt/totem-flexmedia/.env
gunzip -c "$BACKUP" | psql "$DATABASE_URL"

sudo systemctl start totem-flexmedia
```

### 3.4 Validar

- `https://<dominio>/admin/login` → consegue logar com o super admin?
- Abra uma instituição e confirme se animais, lojas e FAQ voltaram.
- Veja os logs: `journalctl -u totem-flexmedia -n 100`.

### 3.5 Backup manual sob demanda

```bash
sudo -u totem /opt/totem-flexmedia/deploy/backup.sh
```

---

## 4. Adicionar uma nova instituição

A plataforma é **multi-tenant**. Cada instituição (zoo, shopping, farmácia etc.)
tem seu próprio conteúdo, módulos habilitados, logo, quota diária de IA e
painel administrativo (`client_admin`).

### 4.1 Pelo painel (recomendado)

1. Logue como super admin em `https://<dominio>/admin/login`.
2. Menu **Plataforma → Instituições → Nova**.
3. Preencha:
   - **Nome** e **slug** (o slug vira parte da URL pública).
   - **Módulos** ativos (zoo, shopping, farmácia, eventos, FAQ, mapa…).
   - **Logo** (upload vai para `static/uploads/<slug>/`).
   - **daily_ai_quota** — limite diário de chamadas à OpenAI para esse tenant.
     Se estourar, `voice.py` devolve 429 "limite diário atingido" sem
     chamar a OpenAI.
4. Em **Usuários → Novo**, crie um `client_admin` vinculado à instituição.
   Ele poderá gerenciar apenas o conteúdo dela.
5. O cliente acessa `https://<dominio>/admin/login` e cai no painel da
   própria instituição (`admin_institution`).

### 4.2 Por CLI (instalação em lote ou automação)

```bash
cd /opt/totem-flexmedia
sudo -u totem -E bash -c '
  source venv/bin/activate
  set -a; source .env; set +a
  export FLASK_APP=wsgi.py
  flask shell
'
```

Dentro do shell:

```python
from app.extensions import db
from app.models.institution import Institution, Module, InstitutionModule
from app.models.user import User

inst = Institution(
    nome="Zoo Exemplo",
    slug="zoo-exemplo",
    daily_ai_quota=500,
)
db.session.add(inst)
db.session.flush()

# Habilita módulos (os códigos vêm do seed inicial)
for codigo in ["zoo", "eventos", "faq", "mapa"]:
    mod = Module.query.filter_by(codigo=codigo).one()
    db.session.add(InstitutionModule(institution_id=inst.id, module_id=mod.id))

admin = User(
    email="admin@zooexemplo.com.br",
    role="client_admin",
    institution_id=inst.id,
)
admin.set_password("TrocarNoPrimeiroLogin!")
db.session.add(admin)
db.session.commit()
```

### 4.3 URL pública da instituição

- `https://<dominio>/` → seletor (se houver várias instituições).
- `https://<dominio>/i/<slug>/` → entrada direta daquele totem
  (recomendado configurar como URL do kiosk em `install_totem.sh`).

### 4.4 Checklist pós-criação

- [ ] Logo carregada e visível na home da instituição.
- [ ] Pelo menos um item em cada módulo habilitado (evita tela vazia).
- [ ] FAQ populado — alimenta o contexto da IA (`build_ai_context` em
      `app/helpers.py`).
- [ ] Quota diária condizente com o volume esperado.
- [ ] Teste o assistente de voz para validar o consentimento LGPD e
      a resposta da OpenAI com o contexto da instituição.

---

## Referência rápida — comandos do dia a dia

| Ação                         | Comando                                              |
|------------------------------|------------------------------------------------------|
| Status do serviço            | `systemctl status totem-flexmedia`                   |
| Logs ao vivo                 | `journalctl -u totem-flexmedia -f`                   |
| Reiniciar após mudar `.env`  | `sudo systemctl restart totem-flexmedia`             |
| Backup manual                | `sudo -u totem /opt/totem-flexmedia/deploy/backup.sh`|
| Purga de logs (LGPD, 90d)    | `flask purge-logs` (agendado no cron)                |
| Aplicar migrations           | `flask db upgrade`                                   |
| Recriar seed                 | `flask seed`                                         |
