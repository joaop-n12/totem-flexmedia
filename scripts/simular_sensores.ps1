# Simulador de sensores do Totem FlexMedia — uso em dev (laptop/VM).
#
# Como usar:
#   1. cd c:\Users\depao\OneDrive\Documentos\totem_flexmedia_new
#   2. python run.py     (em outra janela)
#   3. . .\scripts\simular_sensores.ps1
#   4. Chame as funcoes: Aproximar, Afastar, ForaAlcance, etc.
#
# Tudo via POST /api/sensors/mock (HC-SR04) e /api/local/wake (DHT).
# Loopback-only + X-Wake-Secret — mesma autenticacao do daemon de sensores.

$script:BaseUrl = "http://127.0.0.1:5000"
$script:WakeSecret = $null

# Le TOTEM_WAKE_SECRET do .env do projeto. Cai para variavel de ambiente
# se nao achar o arquivo (cenario CI/script chamado de outro diretorio).
function Carregar-Secret {
    $envFile = Join-Path (Split-Path -Parent $PSScriptRoot) ".env"
    if (Test-Path $envFile) {
        $line = Select-String -Path $envFile -Pattern '^TOTEM_WAKE_SECRET=' | Select-Object -First 1
        if ($line) {
            $script:WakeSecret = ($line.Line -split '=', 2)[1].Trim('"', "'")
        }
    }
    if (-not $script:WakeSecret) { $script:WakeSecret = $env:TOTEM_WAKE_SECRET }
    if (-not $script:WakeSecret) {
        Write-Host "TOTEM_WAKE_SECRET nao encontrado no .env nem no ambiente." -ForegroundColor Red
        Write-Host "Defina no .env: TOTEM_WAKE_SECRET=algumacoisa" -ForegroundColor Yellow
    }
}
Carregar-Secret

# ── HC-SR04 (distancia / proximidade) ─────────────────────────────────────

function Distancia {
    param([Parameter(Mandatory)] $cm)
    # cm pode ser numero ou $null (fora de alcance)
    $body = if ($null -eq $cm) { '{"distance_cm": null}' } else { "{`"distance_cm`": $cm}" }
    try {
        $resp = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/sensors/mock" `
            -Headers @{ "X-Wake-Secret" = $WakeSecret; "Content-Type" = "application/json" } `
            -Body $body
        $s = $resp.session
        $dCm = if ($null -eq $s.distance_cm) { '—' } else { "$($s.distance_cm) cm" }
        Write-Host "[$($s.state.ToUpper())] distancia=$dCm" -ForegroundColor Cyan
    } catch {
        Write-Host "Falhou: $_" -ForegroundColor Red
    }
}

# Atalhos didaticos — cada um exibe o que esta acontecendo.

function Aproximar {
    Write-Host "→ Visitante a 50 cm (dentro de ENGAGE_DISTANCE_CM=80)" -ForegroundColor Green
    Distancia 50
    Write-Host "  Esperado: state=active, overlay some, audio toca."
}

function Afastar {
    Write-Host "→ Visitante a 250 cm (alem de LEAVE_DISTANCE_CM=150)" -ForegroundColor Yellow
    Distancia 250
    Write-Host "  Esperado: state continua active por LEAVE_DELAY_S (30s); depois vai a idle."
}

function ForaAlcance {
    Write-Host "→ HC-SR04 sem reflexao (null)" -ForegroundColor Yellow
    Distancia $null
    Write-Host "  Mesmo efeito de afastamento: grace 30s e vai a idle."
}

# Cenario que reproduz o bug que corrigimos.
function Presenca-Constante {
    param([int]$Segundos = 100, [int]$Cm = 50)
    Write-Host "→ Visitante PARADO a $Cm cm por $Segundos segundos" -ForegroundColor Green
    Write-Host "  Antes do fix: caia em IDLE apos ACTIVE_TIMEOUT_S (60s)."
    Write-Host "  Depois do fix: permanece ACTIVE o tempo todo." -ForegroundColor DarkGray
    $iter = [Math]::Ceiling($Segundos / 5)
    for ($i = 1; $i -le $iter; $i++) {
        Distancia $Cm
        Start-Sleep -Seconds 5
    }
    Write-Host "Fim. Estado final:"
    Estado
}

# ── DHT11/DHT22 (temperatura + umidade) ───────────────────────────────────
# Usa /api/local/wake com type=environment. NAO muda o state da maquina,
# so atualiza a telemetria exibida no overlay.

function Ambiente {
    param(
        [Parameter(Mandatory)][double]$TempC,
        [Parameter(Mandatory)][double]$HumidPct
    )
    $body = "{`"type`": `"environment`", `"temp_c`": $TempC, `"humidity_pct`": $HumidPct, `"source`": `"dht22`"}"
    try {
        $resp = Invoke-RestMethod -Method Post -Uri "$BaseUrl/api/local/wake" `
            -Headers @{ "X-Wake-Secret" = $WakeSecret; "Content-Type" = "application/json" } `
            -Body $body
        $s = $resp.session
        Write-Host "[$($s.state.ToUpper())] temp=$($s.temp_c)°C  umid=$($s.humidity_pct)%" -ForegroundColor Cyan
    } catch {
        Write-Host "Falhou: $_" -ForegroundColor Red
    }
}

# ── Utilitarios ───────────────────────────────────────────────────────────

function Estado {
    try {
        $s = Invoke-RestMethod "$BaseUrl/api/session/state"
        $dCm = if ($null -eq $s.distance_cm) { '—' } else { "$($s.distance_cm) cm" }
        $temp = if ($null -eq $s.temp_c) { '—' } else { "$($s.temp_c)°C" }
        $hum  = if ($null -eq $s.humidity_pct) { '—' } else { "$($s.humidity_pct)%" }
        Write-Host "[$($s.state.ToUpper())] distancia=$dCm  temp=$temp  umid=$hum" -ForegroundColor Cyan
    } catch {
        Write-Host "Servidor nao respondeu — python run.py esta rodando em $BaseUrl ?" -ForegroundColor Red
    }
}

# Forca volta para IDLE sem reiniciar o Flask: afasta + espera grace + 1s.
function Reset {
    Write-Host "→ Forcando IDLE (afastamento + grace de 31s)" -ForegroundColor Magenta
    Distancia 250
    Write-Host "  Aguardando LEAVE_DELAY_S..."
    Start-Sleep -Seconds 31
    Estado
}

# Cenario completo: do zero ao bug-fix em 1 comando.
function Demo {
    Write-Host "═══ DEMO COMPLETA ═══" -ForegroundColor Magenta
    Estado
    Write-Host ""
    Aproximar
    Start-Sleep -Seconds 2
    Estado
    Write-Host ""
    Presenca-Constante -Segundos 70 -Cm 50
    Write-Host ""
    Afastar
    Write-Host "  Aguardando grace period..."
    Start-Sleep -Seconds 31
    Estado
}

Write-Host ""
Write-Host "Simulador carregado. Funcoes disponiveis:" -ForegroundColor Green
Write-Host "  Aproximar             — visitante chega (state: active, audio toca)"
Write-Host "  Afastar               — visitante sai (state: idle apos 30s)"
Write-Host "  ForaAlcance           — sensor sem reflexao (idle apos 30s)"
Write-Host "  Presenca-Constante    — fica parado 100s; valida o fix do IDLE espurio"
Write-Host "  Ambiente <temp> <hum> — DHT11/DHT22 mock (so telemetria)"
Write-Host "  Distancia <cm>        — leitura crua (numero ou `$null)"
Write-Host "  Estado                — snapshot atual da maquina de estados"
Write-Host "  Reset                 — forca volta para idle sem restart"
Write-Host "  Demo                  — cenario completo de ponta a ponta"
Write-Host ""
