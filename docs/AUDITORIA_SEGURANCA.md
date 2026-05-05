# Auditoria de segurança — branch `totem_tela_admin`

Data: 2026-04-29
Escopo: arquivos novos/modificados de segurança (twofa, helpers, audit, device,
admin_auth, devices, admin_platform, config, app/__init__).

Severidade: 🔴 Alta · 🟠 Média · 🟡 Baixa · 🟢 Observação
Status: ✅ corrigido · ⚠️ aceito como dívida

> **Atualização 2026-04-29:** todos os itens 🔴 e 🟠 endereçáveis em código
> foram corrigidos nesta sessão. Suite de 53 testes passa. Ver
> `app/crypto.py`, novo fluxo de pending TOTP setup, e comando
> `flask security-upgrade` para migração de dados existentes.

---

## 🔴 Alta — ✅ corrigidos

### 1. HMAC do heartbeat recebe o segredo em claro — defesa neutralizada
[app/routes/devices.py:68-99](app/routes/devices.py#L68-L99)

O endpoint exige `X-Totem-Secret` em texto puro **e** `X-Totem-Signature`. O
docstring afirma "Sem segredo trafegando" — mas o segredo trafega em todo
heartbeat. Quem capturar uma requisição (TLS quebrado, proxy mal configurado,
log do Nginx com headers, dump de memória) consegue forjar novas requisições à
vontade, derrotando completamente o HMAC.

A causa raiz é [app/models/device.py:57](app/models/device.py#L57): `api_key_hash` armazena hash werkzeug
(scrypt) — irreversível, então o servidor **não consegue** recomputar o HMAC.

Corrigir uma das duas pontas:

- **Recomendado:** trocar `api_key_hash` por `api_key_secret` cifrado simétrico
  (Fernet/AES-GCM com chave em `.env`) ou guardar o segredo apenas em HMAC-key
  derivada (não scrypt). Validar HMAC sobre `f"{api_key_id}.{timestamp}.{body}"`
  e remover o header `X-Totem-Secret`.
- Alternativa simples: dropar o HMAC e usar Bearer + TLS estrito + janela de
  timestamp. Mas então o argumento de design no docstring deixa de valer.

### 2. `SECRET_KEY` e `ADMIN_PASSWORD` com fallback inseguro
[config.py:10-14](config.py#L10-L14)

`SECRET_KEY` cai num literal previsível se a env não estiver setada — inclusive
em `ProductionConfig` (que herda). Sessões assinadas com chave conhecida são
falsificáveis. `ADMIN_PASSWORD = "flexmedia2024"` é literal e está na lista de
senhas fracas; usado pelo seed do super_admin.

Falhar duro em produção:
```python
if not os.environ.get("SECRET_KEY"):
    raise RuntimeError("SECRET_KEY ausente — defina no .env")
```

---

## 🟠 Média — ✅ corrigidos (com 1 ⚠️ aceito)

### 3. `totp_secret` armazenado em texto puro
[app/models/user.py:55](app/models/user.py#L55)

Vazamento de banco expõe os 2FA de todos os admins de uma vez. Ao menos cifrar
em repouso com chave separada de `SECRET_KEY` (KMS / variável dedicada). Os
códigos de backup já são hasheados — só falta o segredo TOTP.

### 4. SVG aceito em `save_upload`
[app/helpers.py:190](app/helpers.py#L190)

`ALLOWED_EXTENSIONS` inclui `svg`. SVG carrega `<script>` e atributos `on*`. No
admin a CSP (`script-src 'self'`) bloqueia execução, mas o asset é servido em
`/static/uploads/...` — se o usuário abrir o arquivo diretamente fora do
contexto admin, executa. Recomendo: remover `svg`, ou sanitizar com `bleach`/
`defusedxml`, ou servir uploads como `Content-Disposition: attachment`.

### 5. `super_admin` autenticado sem 2FA antes do redirect
[app/routes/admin_auth.py:143-161](app/routes/admin_auth.py#L143-L161)

Quando super_admin loga sem TOTP configurado, `login_user()` é chamado **antes**
do redirect para `totp_setup`. O `super_admin_required` cobre as outras rotas,
mas a sessão fica autenticada. Se o atacante interrompe a navegação após a
senha, ele pode tentar manipular a tela de setup com sessão válida. Mais limpo:
**não** chamar `login_user` neste caminho; tratar igual ao fluxo `_pending_2fa`
mas com flag `_pending_totp_setup`.

### 6. Comparação de CSRF token contra string vazia ainda é segura, porém
[app/helpers.py:46-47](app/helpers.py#L46-L47)

`secrets.compare_digest("", "")` retorna True. O guard `if not token` previne,
mas só pelo `not token`. Se um dia removerem essa linha, vira bypass. Reforçar
exigindo `len(token) >= 32` antes do compare.

### 7. `_enforce_admin_session_timeout` pode redirecionar para POST
[app/__init__.py:239](app/__init__.py#L239)

Sessão expira no meio de um POST → `redirect(url_for("auth.login", next=request.path))`
faz GET e o usuário perde o formulário. UX, não vulnerabilidade — mas usuários
costumam reenviar credenciais e dados. Aceitar e tratar conforme prioridade.

---

## 🟡 Baixa

### 8. `int(request.form.get(...))` sem try/except
[app/routes/admin_platform.py:79,135,148](app/routes/admin_platform.py#L79)

Entrada não numérica em `daily_ai_quota` ou `order_*` levanta ValueError → 500.
Não é falha de segurança, mas envenena logs e dificulta detecção de abuso.

### 9. `_maybe_int(0) or device.uptime_seconds` descarta zero legítimo
[app/routes/devices.py:117-120](app/routes/devices.py#L117-L120)

`uptime_seconds == 0` no payload mantém o valor antigo. Idem `cpu_temp_c=0.0`.
Trocar `or` por checagem `is not None`.

### 10. Login traz `failed_count` antes do `register_failed_login`
[app/routes/admin_auth.py:172](app/routes/admin_auth.py#L172)

`details={"failed_count": user.failed_login_count}` — quando `user` existe, o
contador já foi incrementado em :166. OK; só confirma o intencional.

### 11. CSP do totem público com `script-src 'unsafe-inline'`
[app/__init__.py:202](app/__init__.py#L202)

Tracked como dívida ("futuro: nonces"). XSS via conteúdo de instituição
(injetado em `name`, `tagline`, `ai_context`) é o vetor — Jinja escapa por
padrão, mas qualquer `|safe` futuro fica perigoso.

### 12. `validate_password_strength` divergência de doc
[app/helpers.py:210](app/helpers.py#L210) usa 12; CLAUDE.md diz "mín. 10
caracteres". Decidir e alinhar.

---

## 🟢 Pontos fortes observados

- Lockout progressivo + auditoria por tentativa.
- CSRF synchronizer token + `compare_digest`.
- Timing-safe check no login com hash dummy quando e-mail não existe.
- Sanitização de `?next=` em `_next_url_safe` (paths internos, sem `//`/CRLF).
- Backup codes hasheados (scrypt) e single-use.
- TOTP com janela `+/-1 step` apenas — não exagera tolerância.
- Headers: HSTS, X-Frame DENY, Referrer-Policy, Permissions-Policy, CSP
  diferenciado admin vs público, `Cache-Control: no-store` no admin.
- ProxyFix configurado — `remote_addr` e `_scheme` corretos atrás do Nginx.
- Idle timeout + IP binding na sessão admin.
- Tenant isolation em `client_admin_required` (compara `institution_id`).
- Rate-limit em login (20/min) e challenge 2FA (10/min).
- Soft-delete de usuários preserva trilha de auditoria.
- Auto-desativação bloqueada para o próprio super_admin.

---

## Plano sugerido (em ordem de impacto)

1. **#1 ✅** — heartbeat agora só usa HMAC. Segredo cifrado com Fernet em
   `device.api_key_secret_encrypted` ([app/crypto.py](app/crypto.py),
   [app/models/device.py](app/models/device.py)). Header `X-Totem-Secret`
   removido. Mensagem assinada inclui `api_key_id` para impedir reuso de
   assinatura entre totens.
2. **#2 ✅** — `ProductionConfig.validate_runtime` chamado pelo factory
   levanta `RuntimeError` se `SECRET_KEY` ou `FIELD_ENCRYPTION_KEY` faltarem
   ([config.py](config.py)). Fallback `flexmedia2024` removido do seed; sem
   `SUPERADMIN_PASSWORD`, gera senha forte aleatória e imprime no log uma vez
   ([app/seed.py](app/seed.py)).
3. **#3 ✅** — `User.totp_secret` virou property cifrada via Fernet
   ([app/models/user.py](app/models/user.py)). Migração in-place de valores
   legados base32 via `flask security-upgrade`.
4. **#4 ✅** — `svg` removido de `ALLOWED_EXTENSIONS`
   ([app/helpers.py](app/helpers.py)).
5. **#5 ✅** — super_admin sem TOTP fica em `_pending_totp_setup_user_id`,
   não recebe `login_user()` antes de confirmar ([app/routes/admin_auth.py](app/routes/admin_auth.py)).
6. **#6 ✅** — `validate_csrf_token` exige `len(token) >= 32` antes do
   `compare_digest`.
7. **#7 ⚠️** — UX do timeout em POST: aceito como dívida (raro; reenvio é
   explícito; não é vetor de segurança).
8. **#8 ✅** — `_safe_int` para parses defensivos em
   [admin_platform.py](app/routes/admin_platform.py).
9. **#9 ✅** — heartbeat preserva zero legítimo via `is not None`
   ([app/routes/devices.py](app/routes/devices.py)).
10. **#10 ✅** — esclarecido: `failed_count` registrado já reflete o pós-incremento.
11. **#11 ⚠️** — CSP do totem público com `'unsafe-inline'` em script-src:
    aceito como dívida (templates legados). Migrar para nonces no próximo
    refactor de UI.
12. **#12 ✅** — comentário do `validate_password_strength` agora alinha com
    `PASSWORD_MIN_LENGTH = 12`.

### Como aplicar em ambiente existente

```bash
# 1. Atualizar deps
pip install -r requirements.txt

# 2. Gerar a chave de cifragem de campos e adicionar ao .env
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Cole no .env como FIELD_ENCRYPTION_KEY=<valor>

# 3. Aplicar migração de schema + cifrar dados legados
flask security-upgrade

# 4. Para bancos com totens já provisionados em hash legado, a migração marca
#    status='needs_reprovision'. Reprovisione cada totem pela tela admin —
#    o segredo antigo nao tem como ser convertido em ciphertext sem o claro.
```
