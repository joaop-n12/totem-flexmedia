# Instalação do Totem FlexMedia

Guia direto para colocar um Raspberry Pi 3 rodando como totem. **Siga na ordem.**

## Antes de começar

Você precisa de:
- Raspberry Pi 3 B/B+ com fonte 5V/2.5A
- Cartão SD ≥ 16 GB
- Chave da OpenAI (`sk-...`)
- Domínio na Cloudflare (ex: `flextotem.uk`)

---

## 1. Gravar o SD

No PC, instale o **Raspberry Pi Imager** → escolha **Raspberry Pi OS Lite (32-bit)**.

Na engrenagem ⚙ configure: hostname `totem-pi01`, **SSH habilitado**, usuário `pi`, senha forte, Wi-Fi com país `BR`.

Grave o SD, ponha no Pi, ligue.

## 2. Entrar no Pi

```bash
ssh pi@totem-pi01.local
sudo apt update && sudo apt upgrade -y
sudo reboot
```

Espere o reboot e entre de novo via SSH.

## 3. Instalar pacotes

```bash
sudo apt install -y git python3-venv python3-pip sqlite3 redis-server
```

## 4. Clonar o projeto

```bash
cd ~
git clone <URL-DO-REPO> totem_flexmedia
cd totem_flexmedia
```

## 5. Python + dependências

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-pi.txt
```

> A partir daqui, **sempre** rode `source .venv/bin/activate` antes de qualquer `flask` ou `pip`.

## 6. Configurar `.env`

```bash
cp .env.example .env
python3 -c "import secrets; print('SECRET_KEY='+secrets.token_urlsafe(64))" >> .env
python3 -c "from cryptography.fernet import Fernet; print('FIELD_ENCRYPTION_KEY='+Fernet.generate_key().decode())" >> .env
nano .env
```

No editor, preencha:

```
OPENAI_API_KEY=sk-proj-...
SUPERADMIN_EMAIL=seu@email.com
SUPERADMIN_PASSWORD=Senha-Forte-10-Chars!
```

Salve (`Ctrl+O`, `Enter`, `Ctrl+X`) e trave:

```bash
chmod 600 .env
```

## 7. Criar o banco

```bash
export FLASK_APP=wsgi.py
flask db upgrade
flask seed
```

## 8. Túnel Cloudflare (HTTPS público)

Necessário para liberar o microfone no navegador.

```bash
bash deploy/install_cloudflared.sh
```

Quando perguntar, informe: **domínio** (`flextotem.uk`), **subdomínio** (`pi01`), **nome do túnel** (`totem-pi01`).

O script grava `TOTEM_PUBLIC_URL=https://pi01.flextotem.uk` no `.env` automaticamente.

## 9. Modo quiosque

```bash
./install_totem.sh
sudo reboot
```

O instalador pergunta **uma única vez** se os sensores físicos (HC-SR04 + DHT11/DHT22) já estão conectados nos GPIOs:

- **Responda `s`** se o hardware já está plugado → daemon lê os pinos reais.
- **Responda `n` (default)** se ainda vai conectar depois → grava `TOTEM_DISABLE_SENSORS=1` no `.env` automaticamente. O overlay de proximidade some e o totem fica usável imediatamente.

Para rodar sem interação (CI, automação):
```bash
DISABLE_SENSORS=1 ./install_totem.sh   # forca mock
DISABLE_SENSORS=0 ./install_totem.sh   # forca hardware
```

Trocar depois sem reinstalar: edite `.env` (e `/etc/totem/credenciais.env` se já existir), troque `TOTEM_DISABLE_SENSORS=0|1` e reinicie:
```bash
sudo systemctl restart totem-flexmedia totem-sensors
```

Após o reboot, o monitor abre o Chromium em tela cheia direto no totem.

## 10. Primeiro login no admin

No seu PC, abra `https://pi01.flextotem.uk/admin/login` e use o e-mail/senha do passo 6.

No primeiro acesso: troque a senha → configure 2FA (Google Authenticator) → **salve os códigos de backup** (só aparecem uma vez).

Em **Clientes → Editar**, preencha o campo **URL pública** com `https://pi01.flextotem.uk`. Pronto.

---

## Se algo der errado

**Servidor não sobe:**
```bash
sudo journalctl -u totem-flexmedia -n 50
```

**Túnel não responde:**
```bash
sudo systemctl restart cloudflared
```

**Erro `no such column`** após atualizar o código:
```bash
cd ~/totem_flexmedia && source .venv/bin/activate
export FLASK_APP=wsgi.py
flask db upgrade
sudo systemctl restart totem-flexmedia
```

**Microfone não funciona:** confirme que está em `https://...` (não `http://`).

**Overlay "Aproxime-se" preso** mesmo com hardware plugado: confira `cat .env | grep TOTEM_DISABLE_SENSORS` — se estiver `=1`, troque para `=0` e reinicie os serviços. Se estiver `=0` e o overlay persiste, veja `journalctl -u totem-sensors -n 50`.

---

## Testar sem hardware físico (simulador)

Útil para validar overlay, áudio de boas-vindas e máquina de estados antes de plugar os sensores. Funciona no Pi ou em laptop/VM.

```bash
cd ~/totem_flexmedia
source ./scripts/simular_sensores.sh
```

Comandos disponíveis após o `source`:

| Comando | Cenário |
|---|---|
| `aproximar` | Visitante chega (50 cm) → ACTIVE, áudio toca |
| `afastar` | Visitante sai (250 cm) → IDLE após 30 s |
| `fora_alcance` | Sensor sem eco → IDLE após 30 s |
| `presenca_constante` | Parado a 50 cm por 100 s (valida o fix de IDLE espúrio) |
| `ambiente 25.5 60` | DHT11/DHT22 mock (só telemetria) |
| `estado` | Snapshot atual da máquina de estados |
| `reset` | Força IDLE sem reiniciar |
| `demo` | Roteiro completo de ponta a ponta |

No Windows (PowerShell): `. .\scripts\simular_sensores.ps1` — mesmas funções com nomes equivalentes (`Aproximar`, `Afastar`, etc.).

---

## Backup antes de reinstalar

Se já tem dados em produção:

```bash
bash deploy/backup.sh
```

Copie os arquivos de `backups/` para fora do Pi (`scp` para outra máquina). Para restaurar, substitua `instance/flexmedia.db` no Pi novo entre os passos 6 e 7, pulando o `flask seed`.

---

Mais detalhes em [docs/OPERACAO.md](docs/OPERACAO.md) (rotina, troubleshooting profundo, rotação de chaves).
