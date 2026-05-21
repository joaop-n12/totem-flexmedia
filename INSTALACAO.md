# Instalação do Totem FlexMedia no Raspberry Pi

Guia passo a passo para instalar do zero. **Cada passo tem 3 partes:** o
comando para copiar, o que deve acontecer e por que esse passo existe.

> Tempo estimado: ~30 min (sem contar download de pacotes).
> Pré-requisito mental: você sabe abrir um terminal e copiar/colar comandos.

---

## O que você precisa antes de começar

| Item | Detalhe |
|---|---|
| Raspberry Pi 3 B/B+ | Fonte oficial 5V/2.5A (fonte fraca trava o Pi em uso) |
| Cartão SD | 16 GB ou maior, classe 10 |
| Cabo de rede | Wi-Fi do Pi 3 é instável em ambiente cheio; prefira cabo |
| Chave OpenAI | Formato `sk-proj-...` (criada em platform.openai.com) |
| Domínio na Cloudflare | Ex: `flextotem.uk`. É grátis para .uk em alguns anos |
| PC para SSH | Windows/Mac/Linux — qualquer um |

---

## 1. Gravar o sistema no SD

**Comando:** baixe o **Raspberry Pi Imager** em rpi.org e abra.

No Imager:
1. Sistema operacional → **Raspberry Pi OS Lite (32-bit)**.
2. Clique na **engrenagem (⚙)** e configure:
   - Hostname: `totem-pi01`
   - SSH: **habilitado** (com senha)
   - Usuário: `pi` + senha forte
   - Wi-Fi (se for usar): país `BR`
3. Escolha o SD e clique **Gravar**.

**O que deve acontecer:** ~10 minutos depois, o SD está pronto. Coloque
no Pi, ligue na energia e na rede.

**Por que assim:** o sistema "Lite" é sem interface gráfica — menos
software rodando, mais RAM livre para o totem. O hostname `totem-pi01`
deixa você acessar via `totem-pi01.local` sem precisar saber o IP.

---

## 2. Entrar no Pi via SSH

**Comando** (no seu PC):

```bash
ssh pi@totem-pi01.local
```

Digite a senha que você configurou no Imager. Já dentro do Pi:

```bash
sudo apt update && sudo apt upgrade -y
sudo reboot
```

Espere ~1 minuto e entre de novo:

```bash
ssh pi@totem-pi01.local
```

**O que deve acontecer:** terminal mostra `pi@totem-pi01:~ $` — você
está dentro do Pi.

**Por que assim:** `apt upgrade` atualiza tudo antes de instalar coisa
nova. `reboot` aplica updates de kernel.

---

## 3. Instalar pacotes do sistema

```bash
sudo apt install -y git python3-venv python3-pip sqlite3 redis-server
```

**O que deve acontecer:** ~3 minutos baixando. Termina sem erro vermelho.

**Por que assim:** `git` clona o projeto · `python3-venv` cria ambiente
isolado · `sqlite3` é o banco do totem · `redis-server` faz cache e
rate-limit em produção.

---

## 4. Clonar o projeto

```bash
cd ~
git clone <URL-DO-REPO> totem_flexmedia
cd totem_flexmedia
```

Troque `<URL-DO-REPO>` pelo link real do Git (ex:
`https://github.com/sua-org/totem_flexmedia.git`).

**O que deve acontecer:** pasta `~/totem_flexmedia` criada com os
arquivos do projeto.

**Por que assim:** `cd ~` garante que você está na home do `pi`.
Mantenha sempre o projeto em `~/totem_flexmedia` — os scripts do
deploy assumem esse caminho.

---

## 5. Criar ambiente virtual Python

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt -r requirements-pi.txt
```

**O que deve acontecer:** ~5-8 minutos. Aparece `(.venv)` no início do
prompt depois do `source`.

**Por que assim:** o ambiente virtual evita conflito com pacotes do
sistema. `requirements-pi.txt` instala drivers dos sensores (RPi.GPIO,
adafruit-dht) que **só funcionam no Pi** — não rodam em laptop.

> **A partir daqui, sempre rode `source .venv/bin/activate`** antes de
> usar `flask` ou `pip` no projeto. Sem isso, os comandos não acham as
> dependências.

---

## 6. Configurar o `.env`

Esse arquivo guarda chaves secretas. Vamos criar:

```bash
cp .env.example .env
python3 -c "import secrets; print('SECRET_KEY='+secrets.token_urlsafe(64))" >> .env
python3 -c "from cryptography.fernet import Fernet; print('FIELD_ENCRYPTION_KEY='+Fernet.generate_key().decode())" >> .env
nano .env
```

No editor `nano`, preencha estas três linhas (procure usando `Ctrl+W`):

```
OPENAI_API_KEY=sk-proj-... (cole sua chave)
SUPERADMIN_EMAIL=seu@email.com
SUPERADMIN_PASSWORD=SenhaForte-Pelo-Menos-12-Chars!
```

Salve: `Ctrl+O`, `Enter`, `Ctrl+X`. Agora trave o arquivo:

```bash
chmod 600 .env
```

**O que deve acontecer:** `ls -la .env` mostra `-rw-------` (só o dono
lê).

**Por que assim:** `SECRET_KEY` assina sessões e `FIELD_ENCRYPTION_KEY`
cifra dados sensíveis no banco (TOTP, segredos de totem). Sem eles, o
app **não sobe em produção** — falha duro de propósito. `chmod 600` é
obrigatório: senha forte em arquivo legível por todo mundo é o mesmo
que senha fraca.

---

## 7. Criar o banco de dados

```bash
export FLASK_APP=wsgi.py
flask db upgrade
flask seed
```

**O que deve acontecer:** `flask db upgrade` aplica migrations sem erro.
`flask seed` cria o super admin e o zoo demo. No log: "Super admin
criado: seu@email.com".

**Por que assim:** o seed é **idempotente** — rodar duas vezes não cria
duplicado. Útil em reinstalações.

---

## 8. Túnel Cloudflare (HTTPS público)

Esse passo é **obrigatório** se você quer usar o microfone. Navegador
moderno bloqueia microfone em HTTP fora de `localhost`.

```bash
bash deploy/install_cloudflared.sh
```

O script pergunta:
- **Domínio raiz:** `flextotem.uk`
- **Subdomínio:** `pi01` (deixa o totem em `pi01.flextotem.uk`)
- **Nome do túnel:** `totem-pi01`

Vai abrir uma URL para você autorizar na Cloudflare — copie, cole no
navegador do PC, faça login, autorize o domínio. Volta pro Pi e o
script termina sozinho.

**O que deve acontecer:** ~2 minutos. No final, o script grava
`TOTEM_PUBLIC_URL=https://pi01.flextotem.uk` no `.env` automaticamente.
Teste: abra essa URL no PC — deve carregar a tela do totem em HTTPS.

**Por que assim:** o Cloudflare Tunnel cria um caminho HTTPS público
sem precisar de IP fixo, port-forwarding ou certificado SSL próprio.
Funciona em qualquer rede que tenha internet de saída (até atrás do
NAT do roteador 4G).

---

## 9. Modo quiosque (Chromium em tela cheia)

```bash
./install_totem.sh
```

O script pergunta **uma vez** se os sensores físicos (HC-SR04 +
DHT11/DHT22) já estão plugados nos GPIOs:

- **Responda `s`** se o hardware está ligado → sensores reais ativos.
- **Responda `n`** (padrão) se ainda vai conectar depois → grava
  `TOTEM_DISABLE_SENSORS=1` no `.env`. O totem fica utilizável
  imediatamente, sem overlay "Aproxime-se" preso na tela.

Quando terminar:

```bash
sudo reboot
```

**O que deve acontecer:** o Pi reinicia, monitor abre Chromium em tela
cheia direto no totem. Cursor do mouse some sozinho depois de 1s.

**Por que assim:** o script cria três serviços systemd:
- `totem-flexmedia` (o servidor Flask)
- `totem-sensors` (o daemon dos sensores, só roda se `TOTEM_DISABLE_SENSORS=0`)
- `totem-kiosk` (Chromium fullscreen com watchdog)

Cada um reinicia sozinho se cair. Se o navegador travar, watchdog
reabre em segundos.

**Trocar de modo depois:** edite `.env` E `/etc/totem/credenciais.env`
(os dois!), mude `TOTEM_DISABLE_SENSORS=0|1`, e:

```bash
sudo systemctl restart totem-flexmedia totem-sensors
```

---

## 10. Primeiro login no admin

No seu PC, abra `https://pi01.flextotem.uk/admin/login` e use:
- E-mail: o `SUPERADMIN_EMAIL` que você botou no `.env`
- Senha: o `SUPERADMIN_PASSWORD`

**No primeiro acesso o sistema obriga:**
1. **Trocar a senha** (a do `.env` é considerada temporária).
2. **Configurar 2FA** — abra Google Authenticator no celular, escaneie
   o QR code, digite o código de 6 dígitos.
3. **Salvar os códigos de backup** — aparecem **uma única vez**.
   Imprima ou guarde em gerenciador de senhas. Se você perder o celular
   sem esses códigos, vai precisar resetar o Pi.

Depois, vá em **Plataforma → Instituições → Editar** e preencha
**URL pública** com `https://pi01.flextotem.uk`.

**Pronto.** O totem está no ar.

---

## Se algo der errado

### Servidor não sobe (Pi liga mas totem mostra erro)

```bash
sudo journalctl -u totem-flexmedia -n 50
```

Procure linhas em vermelho. Erros comuns:
- `SECRET_KEY ausente` → você pulou parte do passo 6.
- `no such column` → falta rodar migration. Veja "Migration" abaixo.
- `OPENAI_API_KEY invalid` → chave errada ou revogada.

### Túnel Cloudflare não responde

```bash
sudo systemctl restart cloudflared
sudo journalctl -u cloudflared -f
```

Se o problema persistir, verifique status em
`https://www.cloudflarestatus.com`.

### Erro `no such column` depois de atualizar o código

Você puxou código novo que tem mudanças no banco. Rode a migration:

```bash
cd ~/totem_flexmedia && source .venv/bin/activate
export FLASK_APP=wsgi.py
flask db upgrade
sudo systemctl restart totem-flexmedia
```

### Microfone não funciona

Confirme que você está acessando via `https://...` (não `http://`).
Cloudflare Tunnel cuida disso automaticamente. Se acessar pelo IP
local (`192.168.x.x:8000`) o navegador bloqueia microfone.

### Overlay "Aproxime-se" preso na tela

```bash
grep TOTEM_DISABLE_SENSORS .env /etc/totem/credenciais.env
```

- Se você **não tem** o hardware: ambos os arquivos devem mostrar `=1`.
  Se algum estiver `=0`, mude para `=1` e reinicie:
  `sudo systemctl restart totem-flexmedia totem-sensors`.
- Se você **tem** o hardware mas o overlay persiste:
  `sudo journalctl -u totem-sensors -n 50`. Procure erro de GPIO ou
  permissão.

### Esqueci a senha do admin / perdi o 2FA

Veja `docs/OPERACAO.md` §2.3.

---

## Testar sem hardware físico (simulador)

Útil para validar overlay, áudio de boas-vindas e máquina de estados
**antes** de plugar sensores reais. Roda no Pi ou em laptop.

```bash
cd ~/totem_flexmedia
source ./scripts/simular_sensores.sh
```

Comandos disponíveis depois do `source`:

| Comando | O que faz |
|---|---|
| `aproximar` | Simula visitante chegando (50 cm) — totem entra em ACTIVE, áudio toca |
| `afastar` | Simula visitante saindo (250 cm) — entra em IDLE em ~30s |
| `fora_alcance` | Sensor sem eco — entra em IDLE em ~30s |
| `presenca_constante` | Visitante parado a 50 cm por 100s (testa fix de IDLE espúrio) |
| `ambiente 25.5 60` | DHT11/DHT22 mock — manda temp/umidade |
| `estado` | Mostra snapshot atual da máquina de estados |
| `reset` | Força IDLE sem reiniciar |
| `demo` | Roteiro completo de ponta a ponta |

No Windows (PowerShell):

```powershell
. .\scripts\simular_sensores.ps1
```

Mesmas funções com nomes equivalentes (`Aproximar`, `Afastar`, etc.).

---

## Backup antes de reinstalar

Já tem totem em produção e vai reinstalar?

```bash
bash deploy/backup.sh
```

Os backups ficam em `backups/` com data no nome. Copie para outra
máquina via `scp`. Para restaurar no Pi novo: substitua
`instance/flexmedia.db` entre os passos 6 e 7, e **pule o `flask seed`**
para não sobrescrever.

---

## Próximos passos

- Adicionar mais instituições: `docs/OPERACAO.md` §4
- Rotacionar chaves: `docs/OPERACAO.md` §2 ou `bash deploy/rotate_secrets.sh`
- Adicionar outro totem à frota: `docs/OPERACAO.md` §5.4
- Entender o que cada sensor faz: `app/sensors/` (cada arquivo tem
  docstring explicando)

Mais detalhes em [docs/OPERACAO.md](docs/OPERACAO.md).
