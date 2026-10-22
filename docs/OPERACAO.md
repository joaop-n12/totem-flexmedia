# Manual de Operação — Totem FlexMedia

Guia prático para quem opera a plataforma em produção. Cobre seis fluxos:

1. [Instalação no Raspberry Pi](#1-instalação-no-raspberry-pi)
2. [Troca de chaves e segredos](#2-troca-de-chaves-e-segredos)
3. [Restauração de backup](#3-restauração-de-backup)
4. [Adicionar uma nova instituição](#4-adicionar-uma-nova-instituição)
5. [Operar o Cloudflare Tunnel (HTTPS público)](#5-operar-o-cloudflare-tunnel-https-público)
6. [Sensores físicos (HC-SR04 + DHT)](#6-sensores-físicos-hc-sr04--dht)

Todos os caminhos assumem a instalação padrão em `/opt/totem-flexmedia`
com usuário de serviço `totem`.

> **Para a primeira instalação**, use o guia simplificado
> [INSTALACAO.md](../INSTALACAO.md). Este manual cobre operação contínua
> e cenários avançados.

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

O script pergunta **uma única vez** se os sensores físicos (HC-SR04 +
DHT11/DHT22) já estão conectados nos GPIOs:

- `s` → daemon `totem-sensors` ativo, lê GPIO real.
- `n` (default) → grava `TOTEM_DISABLE_SENSORS=1` em `.env` e em
  `/etc/totem/credenciais.env`. Daemon roda em mock e o overlay
  "Aproxime-se" some — totem fica usável imediatamente, sem hardware.

Override não-interativo (CI/automação):

```bash
DISABLE_SENSORS=1 ./install_totem.sh   # força mock
DISABLE_SENSORS=0 ./install_totem.sh   # força hardware real
```

Esse script configura:

- Chromium em modo fullscreen apontando para a URL do totem.
- Unclutter para esconder o cursor do mouse.
- Watchdog para reiniciar o navegador em caso de travamento.
- Autostart no LXDE/GNOME para subir após o boot.
- Três serviços systemd: `totem-flexmedia` (Flask), `totem-sensors`
  (daemon de sensores) e `totem-kiosk` (Chromium), todos com `Restart=always`.

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

### 2.0 Rotação assistida (recomendado)

Pra emergência (vazamento de chave em chat/screenshot/commit) ou rotação
rotineira de higiene, use o helper:

```bash
cd /opt/totem-flexmedia
bash deploy/rotate_secrets.sh
```

O script é interativo e cobre:

- **`SECRET_KEY`** — invalida sessões ativas do admin
- **`TOTEM_WAKE_SECRET`** — oferece sincronizar automaticamente em
  `/etc/totem/credenciais.env` e reiniciar o `totem-sensors`
- **`FIELD_ENCRYPTION_KEY`** — rotação no modo *dual-key*
  (`FIELD_ENCRYPTION_KEYS=nova,antiga`): o app lê pelas duas e escreve com
  a nova, permitindo migração progressiva sem perder dados criptografados

O `.env` atual é **sempre salvo** como `.env.bak-<timestamp>` antes de qualquer
escrita — rollback de 1 linha em caso de problema.

**Não coberto pelo script** (precisa ação manual fora do Pi):

| Item | Onde resolver |
|------|---------------|
| `OPENAI_API_KEY` vazada | https://platform.openai.com/api-keys → Revoke |
| Senha do super admin | Login no painel → `/admin/change_password` |
| `TOTEM_API_KEY_SECRET` de totens | Painel → `/admin/platform/devices` → regenerar |

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

### 4.4 Acesso operacional no equipamento

O super admin pode criar em **Usuários → Novo** uma conta com role
`operational`. Essa conta não é vinculada a um cliente e não acessa dashboard,
clientes, usuários, relatórios ou configurações administrativas.

Fluxo no Raspberry Pi:

1. Acesse `/admin/login` e autentique a conta operacional.
2. Em `/operacional/`, escolha o cliente e um Totem ativo.
3. Clique em **INICIAR TOTEM**; o sistema reutiliza a interface `/<slug>/`.
4. Para trocar o equipamento, use a engrenagem discreta no canto superior do
   kiosk e faça uma nova seleção.

O ID selecionado é mantido somente na sessão assinada do Flask por até 8 horas.
Senhas, API keys e segredos HMAC nunca são gravados no navegador. Se o Totem for
revogado ou o cliente desativado, `/operacional/iniciar` descarta a seleção e
volta ao seletor.

### 4.5 Checklist pós-criação

- [ ] Logo carregada e visível na home da instituição.
- [ ] Pelo menos um item em cada módulo habilitado (evita tela vazia).
- [ ] FAQ populado — alimenta o contexto da IA (`build_ai_context` em
      `app/helpers.py`).
- [ ] Quota diária condizente com o volume esperado.
- [ ] Teste o assistente de voz para validar o consentimento LGPD e
      a resposta da OpenAI com o contexto da instituição.

---

## 5. Operar o Cloudflare Tunnel (HTTPS público)

O `cloudflared` expõe o totem em HTTPS público sem precisar de IP fixo,
port-forwarding ou certificado SSL próprio. Substitui Nginx+Let's Encrypt em
cenários onde o totem tem internet de saída (que já é requisito da OpenAI).

> **Quando preferir o caminho Nginx+SSL** (em vez de Cloudflare Tunnel):
> totem em rede air-gapped, cliente exige tudo on-prem, ou requisito de
> não depender de serviço externo. Use `deploy/install_production.sh`
> documentado em §1.2.

### 5.1 Provisionar (primeira vez)

```bash
cd /opt/totem-flexmedia
bash deploy/install_cloudflared.sh
```

O script é idempotente — pode reexecutar sem quebrar nada. Cobre:

1. Download do binário `cloudflared` (detecta `armhf`/`arm64`/`amd64`)
2. Autenticação na conta Cloudflare (abre URL pra autorizar o domínio)
3. Criação do túnel nomeado (reaproveita se já existir)
4. Registro CNAME do subdomínio apontando pro túnel
5. Geração de `/etc/cloudflared/config.yml`
6. Instalação como systemd unit (`cloudflared.service`)
7. Atualização do `.env` com `TOTEM_PUBLIC_URL` (usado pelo `install_totem.sh`)

Para provisionar **vários totens em lote**:

```bash
DOMINIO=flextotem.uk SUBDOMINIO=pi02 TUNNEL_NAME=totem-pi02 \
  bash deploy/install_cloudflared.sh
```

### 5.2 Operação do dia a dia

| Ação | Comando |
|------|---------|
| Status do túnel | `sudo systemctl status cloudflared` |
| Logs ao vivo | `sudo journalctl -u cloudflared -f` |
| Reiniciar | `sudo systemctl restart cloudflared` |
| Listar túneis da conta | `cloudflared tunnel list` |
| Listar conexões ativas | `cloudflared tunnel info <nome>` |
| Ver config aplicada | `sudo cat /etc/cloudflared/config.yml` |

### 5.3 Trocar o subdomínio público

```bash
# Apaga o CNAME antigo no painel da Cloudflare (DNS → Records) e crie o novo:
cloudflared tunnel route dns <nome-tunel> novo-subdominio.flextotem.uk

# Edita o config.yml pra refletir o novo hostname
sudo nano /etc/cloudflared/config.yml
# (altere o campo `hostname:` na seção `ingress:`)

sudo systemctl restart cloudflared

# Atualize TOTEM_PUBLIC_URL no .env e refaça o kiosk
sudo -u totem sed -i 's|^TOTEM_PUBLIC_URL=.*|TOTEM_PUBLIC_URL=https://novo-subdominio.flextotem.uk|' /opt/totem-flexmedia/.env
```

### 5.4 Adicionar um totem novo à frota

Cada totem precisa do **seu próprio túnel** (UUID único, credenciais únicas).
No novo Pi, depois do `install_totem.sh`:

```bash
cd ~/totem_flexmedia
DOMINIO=flextotem.uk SUBDOMINIO=pi03 TUNNEL_NAME=totem-pi03 \
  bash deploy/install_cloudflared.sh
```

Recomendação de nomenclatura:

- **`pi<NN>.<dominio>`** — URL fixa por hardware (resiste a realocação entre
  instituições, já que o totem é white-label)
- **`<instituicao>.<dominio>`** — só se o totem for dedicado permanentemente
  a uma instituição

### 5.5 Revogar / desinstalar

```bash
# 1. Desliga o serviço
sudo systemctl disable --now cloudflared

# 2. Deleta o túnel na conta Cloudflare (precisa estar sem conexões ativas)
cloudflared tunnel delete <nome-tunel>

# 3. Remove o CNAME no painel da Cloudflare (DNS → Records)

# 4. Limpa artefatos locais
sudo rm -rf /etc/cloudflared /etc/systemd/system/cloudflared.service
sudo systemctl daemon-reload
```

### 5.6 Quando a Cloudflare cai

A SLA da Cloudflare Tunnel é alta (>99.99% historicamente), mas se houver
incidente: o `cloudflared` registra retry automático no journal, e o totem
mostra a página offline servida pelo Service Worker (`static/js/sw.js`).
Nenhuma ação manual é necessária — o túnel reconecta sozinho.

Para verificar status global: https://www.cloudflarestatus.com/

---

## 6. Sensores físicos (HC-SR04 + DHT)

### 6.1 Arquitetura

O daemon `totem-sensors.service` roda **fora** do worker Gunicorn:

- **HC-SR04** (presença/distância) — GPIO TRIG=23, ECHO=24 por padrão.
- **DHT11 ou DHT22** (temp/umidade) — GPIO DATA=4, modelo via env
  `DHT_MODEL`.

Fluxo de dados:

```
[GPIO] → app/sensors/daemon.py
            ├─ HC-SR04: POST /api/local/wake type=distance (loopback)
            │           → SessionStateMachine → SSE → kiosk reage
            └─ DHT:     POST /api/local/wake type=environment (loopback)
                        → widgets TEMP/UMID na home (templates/base.html)
                       + heartbeat HMAC → painel admin (frota)
```

Detalhes técnicos por arquivo em `app/sensors/` (docstrings explicam
cada decisão).

### 6.2 Verificar status no Pi

```bash
sudo systemctl status totem-sensors
sudo journalctl -u totem-sensors -f
```

Sinais de saúde:
- `SensorDaemon online (dht mock=False, hcsr04 mock=False)` → hardware OK.
- `mock=True` em Pi com hardware plugado → veja `TOTEM_DISABLE_SENSORS`
  no `.env` E em `/etc/totem/credenciais.env` (precisam estar **ambos** `=0`).

### 6.3 Alternar entre hardware e mock sem reinstalar

```bash
# Para mock (overlay some, widgets ficam em "--")
sudo sed -i 's/^TOTEM_DISABLE_SENSORS=.*/TOTEM_DISABLE_SENSORS=1/' \
  /opt/totem-flexmedia/.env /etc/totem/credenciais.env

# Para hardware real
sudo sed -i 's/^TOTEM_DISABLE_SENSORS=.*/TOTEM_DISABLE_SENSORS=0/' \
  /opt/totem-flexmedia/.env /etc/totem/credenciais.env

# Aplica nos dois serviços
sudo systemctl restart totem-flexmedia totem-sensors
```

**Por que dois arquivos:** `.env` é lido pelo Flask (controla overlay
no template); `/etc/totem/credenciais.env` é lido pelo daemon (controla
leitura real do GPIO). Mudar só um deixa os dois canais
dessincronizados — daemon lendo GPIO e overlay sumido, ou vice-versa.

### 6.4 Trocar o modelo DHT (DHT11 ↔ DHT22)

```bash
sudo nano /etc/totem/credenciais.env
# Adicione ou altere: DHT_MODEL=DHT11   (ou DHT22)
sudo systemctl restart totem-sensors
```

O driver propaga essa env via `os.environ.setdefault` no startup do
daemon — não precisa mexer no systemd unit.

### 6.5 Testar widgets TEMP/UMID sem hardware

Use o simulador (também serve para HC-SR04):

```bash
cd /opt/totem-flexmedia
source ./scripts/simular_sensores.sh
ambiente 25.5 60        # manda temp=25.5 / umid=60
estado                  # ver snapshot atual
```

Mais cenários em [INSTALACAO.md](../INSTALACAO.md#testar-sem-hardware-físico-simulador).

### 6.6 Telemetria no painel admin

`totem-sensors` envia heartbeat HMAC a cada 60s incluindo
`ambient_temp_c` e `ambient_humidity_pct`. Aparece em
**Plataforma → Totens** → linha do device, colunas TEMP/UMID.

Se ficar `null` no painel:
1. Daemon está rodando? `systemctl status totem-sensors`.
2. Credenciais HMAC corretas? `cat /etc/totem/credenciais.env` deve
   ter `TOTEM_API_KEY_ID` e `TOTEM_API_KEY_SECRET` válidos
   (regerados em `/admin/platform/devices`).
3. Heartbeat aceito? `journalctl -u totem-sensors | grep -i heartbeat`.

---

## Referência rápida — comandos do dia a dia

| Ação                         | Comando                                              |
|------------------------------|------------------------------------------------------|
| Status do serviço            | `systemctl status totem-flexmedia`                   |
| Logs ao vivo                 | `journalctl -u totem-flexmedia -f`                   |
| Status do daemon de sensores | `systemctl status totem-sensors`                     |
| Logs dos sensores            | `journalctl -u totem-sensors -f`                     |
| Reiniciar após mudar `.env`  | `sudo systemctl restart totem-flexmedia totem-sensors` |
| Backup manual                | `sudo -u totem /opt/totem-flexmedia/deploy/backup.sh`|
| Purga de logs (LGPD, 90d)    | `flask purge-logs` (agendado no cron)                |
| Aplicar migrations           | `flask db upgrade`                                   |
| Recriar seed                 | `flask seed`                                         |
| Rotacionar segredos          | `bash deploy/rotate_secrets.sh`                      |
| Status do túnel HTTPS        | `sudo systemctl status cloudflared`                  |
| Logs do túnel                | `sudo journalctl -u cloudflared -f`                  |
| Simular sensores             | `source ./scripts/simular_sensores.sh`               |
