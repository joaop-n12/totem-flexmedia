# Instalação do Totem FlexMedia

Guia passo a passo para instalar o projeto do zero — tanto em um Raspberry Pi real quanto em uma máquina virtual (VirtualBox) rodando Debian 12 ou Raspberry Pi OS.

Este documento reproduz exatamente o caminho validado em uma VM Debian 12 (amd64).

## 📋 Pré-requisitos

- Acesso à internet
- Usuário com privilégios de sudo
- Conta no GitHub com acesso ao repositório
- Uma chave da API da OpenAI (https://platform.openai.com/api-keys)

## 1️⃣ Preparar o ambiente

1. Baixe o Raspberry Pi Imager: https://www.raspberrypi.com/software/
2. Grave o Raspberry Pi OS (64-bit, Desktop) em um cartão SD de 16 GB ou mais.
3. Antes de gravar, clique na engrenagem ⚙️ do Imager e configure:
   - Usuário: `pi`
   - Hostname: `totem`
   - SSH habilitado
   - Wi-Fi (se aplicável)
4. Insira o SD no Raspberry, ligue e aguarde o boot inicial.

## 2️⃣ Instalar git e configurar SSH

### 2.1 Atualizar o sistema e instalar git

```bash
sudo apt update
sudo apt install -y git
```

### 2.2 Gerar chave SSH

```bash
ssh-keygen -t ed25519 -C "totem@raspberry"
```

Aperte Enter 3 vezes (nome padrão, sem senha).

### 2.3 Copiar a chave pública

```bash
cat ~/.ssh/id_ed25519.pub
```

Selecione a linha inteira que aparece (começa com `ssh-ed25519`) e copie.

### 2.4 Adicionar no GitHub

1. Acesse https://github.com/settings/keys
2. Clique em "New SSH key"
3. Title: `Totem Raspberry`
4. Cole a chave no campo "Key"
5. Clique em "Add SSH key"

### 2.5 Testar a conexão

```bash
ssh -T git@github.com
```

Digite `yes` se perguntar. Deve aparecer:

```
Hi <seu-usuario>! You've successfully authenticated...
```

## 3️⃣ Clonar o projeto

Sempre no seu HOME, clone já direto na branch correta:

```bash
cd ~
git clone -b totem_tela_admin git@github.com:depaolii/totem_flexmedia.git totem_flexmedia
cd totem_flexmedia
```

⚠️ **Importante:** a pasta deve se chamar exatamente `totem_flexmedia` (tudo minúsculo). O instalador procura por esse nome específico.

Confirme a estrutura:

```bash
ls
```

Deve aparecer: `app/`, `run.py`, `wsgi.py`, `install_totem.sh`, `INSTALACAO.md` etc.

## 4️⃣ Rodar o instalador automatizado

```bash
chmod +x install_totem.sh
./install_totem.sh
```

O script vai:

- Instalar as dependências do sistema (Python, Chromium, libs C do Pillow)
- Criar o virtualenv e instalar libs Python
- Perguntar 3 dados para gerar o `.env`:
  - `OPENAI_API_KEY` → sua chave da OpenAI
  - Email do super admin → ex.: `admin@totem.com`
  - Senha do super admin → escolha uma forte (anote!)
- Criar o banco de dados (`flask init-db` + `flask seed`)
- Configurar o systemd para subir o backend automaticamente
- Instalar o Chromium em modo kiosk com autostart

Leva 5-10 minutos. No final, aparece:

```
============================================
  INSTALACAO CONCLUIDA
============================================
```

## 5️⃣ Verificar que tudo subiu

### 5.1 Backend está rodando?

```bash
sudo systemctl status totem-flexmedia
```

A linha `Active:` deve estar verde com `active (running)`. Aperte `q` para sair.

### 5.2 Backend está respondendo na porta 8000?

```bash
curl -i http://localhost:8000/
```

Deve aparecer algo como:

```
HTTP/1.1 302 FOUND
Location: /zoo/
```

### 5.3 Todos os arquivos do kiosk estão no lugar?

```bash
systemctl is-enabled totem-flexmedia      # deve retornar "enabled"
ls ~/.config/totem-kiosk.sh                # deve existir
ls ~/.config/autostart/totem-kiosk.desktop # deve existir
ls ~/totem_flexmedia/.env                  # deve existir (permissão 600)
grep bind ~/totem_flexmedia/gunicorn.conf.py
# deve mostrar: bind = os.environ.get("GUNICORN_BIND", "127.0.0.1:8000")
```

Se todos os checks passarem, siga para o passo 7.

## 6️⃣ Reiniciar

```bash
sudo reboot
```

O que deve acontecer:

- Sistema reinicia (~30 s na VM, ~1-2 min no Pi real)
- Backend sobe via systemd em paralelo
- GNOME carrega
- Chromium abre em fullscreen mostrando o tótem do zoo demo

## 7️⃣ Configurar conteúdo pelo painel admin

### 7.1 Descobrir o IP da máquina

```bash
hostname -I
```

### 7.2 Acessar o painel

No navegador (pode ser de outro computador na mesma rede):

```
http://<IP-DA-MAQUINA>:8000/admin/login
```

Faça login com o email e a senha que você cadastrou no passo 4.

### 7.3 O que dá pra configurar

- ✅ Criar novas instituições (zoo, shopping, farmácia)
- ✅ Personalizar cores, logo e textos de cada instituição
- ✅ Cadastrar animais, eventos, lojas, produtos, FAQs
- ✅ Ativar módulos (mapa, IA, etc.)
- ✅ Ajustar quota diária de IA por instituição

Sem cadastrar conteúdo, o tótem continua mostrando apenas a instituição demo (Neural Crew Zoo).

## 🆘 Troubleshooting

### Chromium mostra "This site can't be reached"

Backend não está ouvindo na porta 8000. Abra um terminal (Ctrl da direita + Alt + F2) e rode:

```bash
sudo systemctl status totem-flexmedia
journalctl -u totem-flexmedia --no-pager -n 30
```

Se os logs mostrarem `Listening at: unix:/tmp/...`, confira o `gunicorn.conf.py`:

```bash
grep bind ~/totem_flexmedia/gunicorn.conf.py
```

Deve ser: `bind = os.environ.get("GUNICORN_BIND", "127.0.0.1:8000")`.

### Kiosk abre mas mostra página 404

A URL no script do kiosk está errada. Confira:

```bash
grep URL ~/.config/totem-kiosk.sh
```

Deve mostrar: `URL="http://localhost:8000/"` (sem `/totem`).

Se estiver errado, edite com `nano ~/.config/totem-kiosk.sh` e reinicie o serviço.

### Sair do kiosk para mexer no terminal

Pressione **Ctrl da direita + Alt + F2** para abrir um terminal texto. Faça login com `pi`.

Para voltar ao desktop gráfico: **Ctrl da direita + Alt + F1** (ou F7).

### Matar o Chromium em loop

```bash
pkill chromium
pkill -f totem-kiosk
```

### Ver logs do backend em tempo real

```bash
journalctl -u totem-flexmedia -f
```

### Reiniciar só o backend (sem reboot)

```bash
sudo systemctl restart totem-flexmedia
```

### Erro `vmwgfx Failed to send host log` (só VM)

Driver gráfico errado. Desligue a VM e vá em **Configurações → Tela**: troque para **VBoxSVGA** com 3D desativado e 128 MB de VRAM.

### Erro "Permissão negada" ao rodar `./install_totem.sh`

Falta bit de executável. Rode:

```bash
chmod +x install_totem.sh
```

### Erro `/bin/bash^M: interpretador incorreto`

Arquivo com line endings do Windows (CRLF). Corrija:

```bash
sed -i 's/\r$//' install_totem.sh
```

## 📚 Comandos úteis do dia a dia

| Ação | Comando |
|------|---------|
| Ver logs do backend ao vivo | `journalctl -u totem-flexmedia -f` |
| Reiniciar só o backend | `sudo systemctl restart totem-flexmedia` |
| Testar se está rodando | `curl http://localhost:8000/` |
| Matar kiosk pra sair | `pkill chromium && pkill -f totem-kiosk` |
| Ir pro terminal texto | Ctrl da direita + Alt + F2 |
| Voltar pro desktop | Ctrl da direita + Alt + F1 (ou F7) |
| IP da máquina | `hostname -I` |

## 🗂️ Estrutura principal após instalação

```
~/totem_flexmedia/
├── app/                # código Flask (rotas, models, helpers)
├── static/             # CSS, JS, imagens
├── templates/          # HTMLs (tótem + admin)
├── venv/               # virtualenv (não commitar)
├── .env                # segredos (chmod 600, NUNCA commitar)
├── instance/           # banco SQLite (criado por `flask init-db`)
├── gunicorn.conf.py    # config do Gunicorn (bind TCP 127.0.0.1:8000)
├── run.py              # entrypoint dev (python run.py)
├── wsgi.py             # entrypoint produção (Gunicorn)
└── install_totem.sh    # instalador automatizado

~/.config/
├── totem-kiosk.sh                    # watchdog do Chromium kiosk
└── autostart/totem-kiosk.desktop     # faz o kiosk abrir no login

/etc/systemd/system/
└── totem-flexmedia.service           # serviço do backend (auto-start)

/etc/gdm3/
└── daemon.conf                        # autologin do GNOME
```
