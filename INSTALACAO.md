# Instalação do Totem FlexMedia — Passo a Passo Completo

Guia validado para Raspberry Pi 3 B/B+ (Raspberry Pi OS 32 bits) e VMs Debian 12 / Raspberry Pi OS Desktop. Siga **na ordem** — cada passo valida o anterior antes de avançar.

> ⚠️ **Regra de ouro**: nunca conecte ou desconecte sensores com o Pi ligado. Hardware sempre com energia desligada.

> 🔌 **Porta**: produção (kiosk + admin) sempre em **`8000`** (TCP, via Gunicorn). A porta `5000` só aparece se você rodar `python run.py` manualmente em modo dev — não é usada no totem.

---

## 📋 Antes de começar

Tenha em mãos:

- Raspberry Pi 3 B/B+ + fonte oficial 5V/2.5A (fonte fraca = boot infinito)
- Cartão microSD ≥ 16 GB classe 10
- Monitor HDMI + teclado USB
- Cabo de rede ou Wi-Fi disponível
- **Chave da OpenAI** (https://platform.openai.com/api-keys) — começa com `sk-`
- **Acesso ao GitHub** (chave SSH ou token) com permissão no repositório

---

## 1️⃣ Gravar o sistema no cartão SD

1. Baixe o **Raspberry Pi Imager**: https://www.raspberrypi.com/software/
2. Escolha:
   - **Device**: Raspberry Pi 3
   - **OS**: Raspberry Pi OS (Legacy, 32-bit) — Bookworm Desktop
   - **Storage**: seu cartão SD
3. Clique em **⚙️ (engrenagem)** antes de gravar:
   - ✅ Set hostname: `totem`
   - ✅ Set username and password — **usuário: `pi`** (o instalador procura por esse usuário)
   - ✅ Configure wireless LAN (se for Wi-Fi)
   - ✅ Enable SSH → "Use password authentication"
   - ✅ Set locale: America/Sao_Paulo, teclado br
4. Grave, espete o cartão no Pi, ligue, espere o desktop carregar (~2 min na primeira vez).

> 💡 **VM em vez de Pi**: instale Debian 12 ou Raspberry Pi OS Desktop no VirtualBox. Use **VBoxSVGA + 128 MB VRAM, 3D desativado** (driver `vmwgfx` quebra o Chromium).

---

## 2️⃣ Atualizar o sistema e instalar o git

Abra o terminal (no desktop ou via SSH `ssh pi@totem.local`):

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git
```

---

## 3️⃣ Configurar acesso ao GitHub (SSH)

```bash
ssh-keygen -t ed25519 -C "totem@raspberry"
```

Aperte **Enter 3 vezes** (nome padrão, sem senha).

```bash
cat ~/.ssh/id_ed25519.pub
```

Copie a linha inteira (começa com `ssh-ed25519`). No GitHub:

1. https://github.com/settings/keys → **New SSH key**
2. Title: `Totem Raspberry`
3. Cole a chave → **Add SSH key**

Teste:

```bash
ssh -T git@github.com
```

Se perguntar "Are you sure...", digite `yes`. Deve aparecer:

```
Hi <seu-usuario>! You've successfully authenticated...
```

---

## 4️⃣ Clonar o projeto

```bash
cd ~
git clone -b totem_tela_admin git@github.com:depaolii/totem_flexmedia.git totem_flexmedia
cd totem_flexmedia
```

> ⚠️ A pasta deve se chamar **exatamente `totem_flexmedia`** (minúsculo). O instalador também aceita rodar de qualquer pasta que contenha `wsgi.py` e `app/`, mas o systemd e o kiosk assumem `~/totem_flexmedia`.

Confirme:

```bash
ls
```

Deve listar: `app/`, `run.py`, `wsgi.py`, `install_totem.sh`, `requirements.txt`, etc.

---

## 5️⃣ Corrigir line endings (só se você editou no Windows)

Se você abriu o repositório no Windows antes, o `install_totem.sh` pode ter `\r\n` (CRLF) e o bash recusa com `/bin/bash^M: bad interpreter`. Prevenção:

```bash
sudo apt install -y dos2unix
dos2unix install_totem.sh 2>/dev/null || sed -i 's/\r$//' install_totem.sh
```

---

## 6️⃣ Rodar o instalador

```bash
chmod +x install_totem.sh
./install_totem.sh
```

> ❌ **NÃO use `sudo ./install_totem.sh`** — o script se recusa a rodar como root. Ele chama `sudo` internamente quando precisa.

O que ele faz, na ordem:

| Etapa | O que acontece | Tempo |
|-------|----------------|-------|
| 0 | Pre-checks (não-root, sudo, pasta do projeto, detecta Pi) | instantâneo |
| 1 | `apt install` de Python, Chromium, unclutter, git | 2-5 min |
| 2 | Cria `venv/` e instala `requirements.txt` (+ `requirements-pi.txt` se for Pi) | 3-7 min |
| 3 | Pergunta seus 3 segredos e gera `.env` (chmod 600) | 30 s |
| 3.1 | `flask init-db` + `flask seed` (banco SQLite + zoo demo) | 10 s |
| 4 | Cria `totem-flexmedia.service` (systemd) e sobe o backend | 5 s |
| 4.1 | Se for Pi: instala `totem-sensors.service` (fica parado esperando credenciais) | 5 s |
| 5 | Cria `~/.config/totem-kiosk.sh` (Chromium em loop) | instantâneo |
| 6-8 | Autostart no LXDE/GNOME, desabilita screensaver | instantâneo |

### O que digitar quando ele perguntar

```
Cole sua OPENAI_API_KEY (comeca com 'sk-'): sk-proj-XXXXXXXX...
Email do super admin (ex.: admin@totem.com): admin@flexmedia.com
Senha do super admin (min. 10 caracteres): ************
Confirme a senha: ************
```

> 🔐 **Anote essa senha**. Sem ela você não entra no painel admin (precisa restaurar via CLI). Veja [docs/OPERACAO.md](docs/OPERACAO.md) para reset.

No final aparece:

```
=========================================
  INSTALACAO CONCLUIDA COM SUCESSO
=========================================

Proximos passos:
  1. Acesse o painel admin:  http://192.168.x.x:8000/admin/login
  ...
```

---

## 7️⃣ Validar o backend ANTES de seguir

Não pule isso. Se algum check falhar, conserte agora — não adianta seguir.

```bash
# 1. Servico ativo?
sudo systemctl status totem-flexmedia
```

A linha `Active:` precisa estar **verde com `active (running)`**. Aperte `q` para sair.

```bash
# 2. Backend respondendo?
curl -i http://localhost:8000/
```

Esperado: `HTTP/1.1 302 FOUND` redirecionando para `/zoo/` ou `/selector`.

```bash
# 3. Banco populado?
ls -la instance/
```

Deve ter `app.db` (~50 KB).

```bash
# 4. .env protegido?
ls -la .env
```

Permissão deve ser `-rw-------` (chmod 600).

Se algo falhar, veja **🆘 Troubleshooting** no fim deste arquivo.

---

## 7️⃣.5 Expor o totem em HTTPS público (Cloudflare Tunnel)

> 🎤 **Por que esse passo é obrigatório se você usa microfone:** todos os navegadores modernos (Chrome, Safari, Firefox e o Chromium embutido no Fully Kiosk Browser) bloqueiam `getUserMedia()` em HTTP fora de localhost. Sem HTTPS, o botão de voz falha com "microfone requer HTTPS ou localhost". A versão gratuita do Fully Kiosk **não tem** as flags pra contornar isso.
>
> A solução adotada é o **Cloudflare Tunnel** — gera uma URL HTTPS pública (`https://pi01.flextotem.uk`) sem precisar de IP público, port-forwarding, certificado SSL próprio ou Nginx. Funciona em qualquer rede (incluindo hotspot de celular) e custa só o preço do domínio (~US$ 5/ano em `.uk`/`.xyz`).

### 7.5.1 Pré-requisitos

- Domínio próprio comprado e gerenciado na **Cloudflare** (https://dash.cloudflare.com → Domain Registration). `.uk`, `.xyz`, `.click` saem em torno de US$ 5–10/ano.
- Pi com internet (já é requisito do projeto pra OpenAI).

### 7.5.2 Rodar o instalador do túnel

```bash
cd ~/totem_flexmedia
bash deploy/install_cloudflared.sh
```

O script automatiza tudo que antes era manual:

| Etapa | O que faz |
|-------|-----------|
| 1 | Detecta arquitetura (`armhf`/`arm64`/`amd64`) e baixa o binário `cloudflared` do GitHub releases |
| 2 | Pergunta domínio (ex.: `flextotem.uk`), subdomínio (ex.: `pi01`) e nome do túnel |
| 3 | Abre URL de autorização da Cloudflare — você cola no celular/laptop, seleciona o domínio e clica em "Authorize" |
| 4 | Cria o túnel nomeado (`cloudflared tunnel create`) — idempotente, reaproveita se já existir |
| 5 | Cria registro CNAME do subdomínio apontando pro túnel |
| 6 | Gera `/etc/cloudflared/config.yml` apontando pro Gunicorn local (`localhost:8000`) |
| 7 | Instala como systemd (`cloudflared.service`) e sobe |
| 8 | Adiciona `TOTEM_PUBLIC_URL=https://...` no `.env` do projeto (consumido pelo `install_totem.sh` na próxima rodada) |

> 💡 **Modo não-interativo** (útil pra provisionar vários totens):
> ```bash
> DOMINIO=flextotem.uk SUBDOMINIO=pi02 TUNNEL_NAME=totem-pi02 \
>   bash deploy/install_cloudflared.sh
> ```

### 7.5.3 Validar

```bash
sudo systemctl status cloudflared        # active (running) + "Connection registered"
curl -I https://pi01.flextotem.uk         # 200 ou 302 (saiu do Pi -> Cloudflare -> Pi)
```

Abra `https://pi01.flextotem.uk` no celular: deve carregar a home do totem com **cadeado verde**. Clique no botão de voz — agora o microfone libera.

### 7.5.4 Apontar o kiosk (Fully Kiosk Browser ou Chromium do `install_totem.sh`)

**Se você usa Fully Kiosk Browser** (Android):

1. Settings → Web Content Settings → **Start URL** → `https://pi01.flextotem.uk`
2. Settings → **Exit Fully Kiosk** → reabrir (Start URL só vale após restart)

**Se você usa o Chromium do `install_totem.sh`** (kiosk no próprio Pi):

O `install_totem.sh` lê `TOTEM_PUBLIC_URL` do `.env` automaticamente. Reaplique:

```bash
cd ~/totem_flexmedia
bash install_totem.sh           # vai usar a TOTEM_PUBLIC_URL gravada no .env
```

Ou force uma URL específica:

```bash
KIOSK_URL=https://pi01.flextotem.uk bash install_totem.sh
```

### 7.5.5 Quando NÃO usar Cloudflare Tunnel

- **Instituição air-gapped** (sem internet de saída): use `deploy/install_production.sh` (Nginx + Let's Encrypt) com um IP/domínio interno.
- **Cliente exige tudo on-prem**: idem.
- **Totem sem necessidade de microfone/câmera**: HTTP local basta.

Nesses cenários, o caminho é o `deploy/install_production.sh` (Nginx + SSL), documentado em [docs/OPERACAO.md §1.2](docs/OPERACAO.md#12-passo-a-passo--servidor).

---

## 8️⃣ Provisionar o totem no painel admin

Antes de conectar sensores, gere as credenciais HMAC do totem.

### 8.1 Descubra o IP

```bash
hostname -I
```

### 8.2 Acesse o painel

No próprio Pi (Chromium ainda não está em kiosk) ou de outro computador na mesma rede:

```
http://<IP>:8000/admin/login
```

Faça login com o email/senha do passo 6.

### 8.3 Crie o totem

1. **Frota → Totens → + Novo Totem**
2. Preencha nome (ex.: "Totem Recepção"), instituição
3. Salve → a tela mostra **uma única vez**:
   - `TOTEM_API_KEY_ID` (ex.: `tk_abc123...`)
   - `TOTEM_API_KEY_SECRET` (ex.: `s_xyz789...`)
4. **Copie os dois agora** — depois você não consegue mais ver o secret.

### 8.4 Salve as credenciais no Pi

```bash
sudo mkdir -p /etc/totem
sudo nano /etc/totem/credenciais.env
```

Cole (ajustando os valores) e o `TOTEM_WAKE_SECRET` precisa ser **idêntico** ao que está em `~/totem_flexmedia/.env`:

```
TOTEM_API_KEY_ID=tk_abc123...
TOTEM_API_KEY_SECRET=s_xyz789...
TOTEM_WAKE_SECRET=<mesmo valor do .env do Flask>
```

Para descobrir o `TOTEM_WAKE_SECRET` que o instalador gerou:

```bash
grep TOTEM_WAKE_SECRET ~/totem_flexmedia/.env
```

Salve (Ctrl+O, Enter, Ctrl+X) e proteja:

```bash
sudo chmod 600 /etc/totem/credenciais.env
```

---

## 9️⃣ Conectar os sensores físicos (só Pi real)

> ⚠️ **DESLIGUE o Pi antes** — nunca conecte GPIO com energia.

```bash
sudo shutdown -h now
```

Espere o LED verde apagar, **tire o cabo de força**, então conecte:

### DHT11 / DHT22 (temperatura + umidade)

| DHT | GPIO Pi |
|-----|---------|
| VCC | Pino 1 (3.3V) |
| GND | Pino 9 (GND) |
| DATA | Pino 7 (GPIO 4) — com resistor 10kΩ pull-up até VCC |

> ℹ️ DHT11 e DHT22 usam a mesma pinagem e a mesma biblioteca. Escolha o modelo
> via `DHT_MODEL=DHT11` (ou `DHT22`) no `.env`. Padrão é `DHT22`.

### HC-SR04 (sensor ultrassônico de distância)

| HC-SR04 | GPIO Pi |
|---------|---------|
| VCC  | Pino 2 (5V) |
| TRIG | Pino 16 (GPIO 23) |
| ECHO | Pino 18 (GPIO 24) — com divisor resistivo 1kΩ/2kΩ até 3.3V |
| GND  | Pino 6 (GND) |

> ⚠️ O pino ECHO entrega 5V. Sem o divisor resistivo, o GPIO do Pi (tolerante
> a 3.3V) pode ser danificado a longo prazo.

Religue o cabo de força. Espere o boot.

---

## 🔟 Iniciar o daemon de sensores

```bash
sudo systemctl start totem-sensors
sudo systemctl status totem-sensors
```

Deve estar `active (running)`. Confira leituras ao vivo:

```bash
journalctl -u totem-sensors -f
```

A cada poucos segundos aparece algo como:

```
temp=24.3°C umidade=58.1% distancia=120cm (heartbeat OK)
```

`Ctrl+C` sai do journalctl (não para o daemon).

---

## 1️⃣1️⃣ Reboot final

```bash
sudo reboot
```

O que esperar:

- Boot (~1-2 min no Pi 3)
- `totem-flexmedia` sobe via systemd (porta 8000)
- `totem-sensors` sobe e começa a postar heartbeats
- Desktop carrega → **Chromium abre em fullscreen** mostrando o tótem
- Cursor some após 100 ms

---

## 1️⃣2️⃣ Conteúdo: criar instituições

Sem cadastrar conteúdo, o tótem mostra só o demo "Neural Crew Zoo". Pelo painel:

- ✅ **Instituições**: criar zoo, museu, hotel etc. (white label)
- ✅ **Personalização**: cores, logo, tagline, idioma padrão
- ✅ **Conteúdo**: animais, eventos, lojas, produtos, FAQs, quiz
- ✅ **Módulos**: ativar/desativar mapa, IA, quiz, avaliação por instituição
- ✅ **Quota IA**: limite diário de chamadas OpenAI por instituição

---

## 🆘 Troubleshooting

### Erro `/bin/bash^M: bad interpreter`
Line endings do Windows. Rode antes do instalador:
```bash
sed -i 's/\r$//' install_totem.sh
```

### Erro "Permissão negada" ao rodar `./install_totem.sh`
```bash
chmod +x install_totem.sh
```

### Instalador aborta com "Nao rode este script como root"
Saia do sudo. Rode com seu usuário normal:
```bash
exit   # se estiver em sudo -i
./install_totem.sh
```

### `flask init-db` falha com "no such command"
O `venv` não foi ativado. Rode manualmente:
```bash
cd ~/totem_flexmedia
source venv/bin/activate
export FLASK_APP=wsgi.py
set -a; source .env; set +a
flask init-db && flask seed
```

### Chromium mostra "This site can't be reached"
Backend não subiu. Diagnóstico:
```bash
sudo systemctl status totem-flexmedia
journalctl -u totem-flexmedia --no-pager -n 50
```
Confira o bind do Gunicorn:
```bash
grep bind ~/totem_flexmedia/gunicorn.conf.py
# precisa ser: bind = os.environ.get("GUNICORN_BIND", "127.0.0.1:8000")
```

### Daemon de sensores não sobe — `credenciais.env not found`
Você pulou o passo 8. Crie `/etc/totem/credenciais.env` com `chmod 600` e:
```bash
sudo systemctl start totem-sensors
```

### `TOTEM_WAKE_SECRET` diferente entre `.env` e `credenciais.env`
O daemon não consegue acordar o kiosk via SSE. Sincronize:
```bash
grep TOTEM_WAKE_SECRET ~/totem_flexmedia/.env
sudo nano /etc/totem/credenciais.env   # cole o mesmo valor
sudo systemctl restart totem-sensors
```

### Sair do kiosk pra mexer no terminal
- **Ctrl direito + Alt + F2** → terminal texto (login `pi`)
- **Ctrl direito + Alt + F1** ou **F7** → volta pro desktop
- Matar Chromium em loop:
  ```bash
  pkill chromium && pkill -f totem-kiosk
  ```

### Esqueci a senha do super admin
```bash
cd ~/totem_flexmedia && source venv/bin/activate
export FLASK_APP=wsgi.py
flask shell
```
No shell:
```python
from app.extensions import db
from app.models.user import User
u = User.query.filter_by(email="admin@flexmedia.com").first()
u.set_password("NovaSenhaForte123")
u.must_change_password = False
u.failed_logins = 0
u.locked_until = None
db.session.commit()
```

### VM: erro `vmwgfx Failed to send host log`
Driver gráfico errado. Desligue, vá em **Configurações → Tela** do VirtualBox: **VBoxSVGA**, 128 MB VRAM, 3D **desativado**.

### Microfone bloqueado: "Microfone requer HTTPS ou acesso por localhost"
Você está acessando o totem por HTTP (`http://<IP>:8000` ou `http://<IP>:5000`). Navegadores modernos bloqueiam `getUserMedia` em HTTP fora de localhost. Rode o passo 7.5 (Cloudflare Tunnel) — gera URL HTTPS sem custo de cert.

### `cloudflared` instalado mas túnel não sobe — "tunnel credentials file not found"
Provavelmente as credenciais ficaram só no `$HOME/.cloudflared/` mas o systemd procura em `/etc/cloudflared/`. O `install_cloudflared.sh` já copia, mas se você criou o túnel manualmente:
```bash
sudo cp ~/.cloudflared/<UUID>.json /etc/cloudflared/
sudo chmod 600 /etc/cloudflared/<UUID>.json
sudo systemctl restart cloudflared
```

### `cloudflared` ativo mas a URL pública dá erro 1033
DNS aponta pro túnel, mas o `cloudflared` local não tem `config.yml` válido. Confira:
```bash
sudo cat /etc/cloudflared/config.yml      # precisa ter tunnel + ingress
sudo journalctl -u cloudflared -n 50
```
Re-rode `bash deploy/install_cloudflared.sh` — ele é idempotente.

---

## 📚 Comandos do dia a dia

| Ação | Comando |
|------|---------|
| Logs do backend ao vivo | `journalctl -u totem-flexmedia -f` |
| Logs dos sensores | `journalctl -u totem-sensors -f` |
| Reiniciar só o backend | `sudo systemctl restart totem-flexmedia` |
| Reiniciar sensores | `sudo systemctl restart totem-sensors` |
| Testar HTTP | `curl http://localhost:8000/` |
| Sair do kiosk | Ctrl direito + Alt + F2 |
| Voltar pro desktop | Ctrl direito + Alt + F1 |
| IP da máquina | `hostname -I` |
| Atualizar o código | `cd ~/totem_flexmedia && git pull && sudo systemctl restart totem-flexmedia` |
| Backup do banco | `bash deploy/backup.sh` |

---

## 🗂️ Estrutura após instalação

```
~/totem_flexmedia/
├── app/                # código Flask
├── instance/app.db     # banco SQLite (criado por flask init-db)
├── venv/               # virtualenv
├── .env                # segredos (chmod 600)
└── install_totem.sh

~/.config/
├── totem-kiosk.sh                   # watchdog do Chromium
└── autostart/totem-kiosk.desktop    # autostart no login

/etc/systemd/system/
├── totem-flexmedia.service          # backend Flask
├── totem-sensors.service            # daemon DHT11/DHT22 + HC-SR04 (Pi only)
└── cloudflared.service              # túnel HTTPS público (se usar Cloudflare Tunnel)

/etc/cloudflared/                    # criado por install_cloudflared.sh
├── config.yml                       # mapeia hostname público → localhost:8000
└── <UUID>.json                      # credenciais do túnel (chmod 600)

/etc/totem/
└── credenciais.env                  # API key + HMAC do totem (chmod 600)
```

---

## ✅ Checklist de instalação bem-sucedida

- [ ] `sudo systemctl status totem-flexmedia` → `active (running)` (verde)
- [ ] `curl http://localhost:8000/` → 302 ou 200
- [ ] Login no admin funciona
- [ ] Kiosk abre fullscreen depois do reboot
- [ ] (Pi) `sudo systemctl status totem-sensors` → `active (running)`
- [ ] (Pi) `journalctl -u totem-sensors -f` mostra `heartbeat OK`
- [ ] `.env` com `chmod 600`
- [ ] `/etc/totem/credenciais.env` com `chmod 600`
- [ ] (Se usar microfone) `sudo systemctl status cloudflared` → `active (running)`
- [ ] (Se usar microfone) `https://<sub>.<dominio>` abre no celular com cadeado verde
- [ ] (Se usar microfone) Botão de voz captura áudio sem erro de HTTPS

Se todos os ✅ passaram, a instalação está pronta para produção. Veja [docs/OPERACAO.md](docs/OPERACAO.md) para troca de chaves, backup e nova instituição.
