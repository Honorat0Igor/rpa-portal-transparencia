<#
Demonstração para gravação: dispara os 5 cenários do desafio pelo webhook do
Activepieces (fluxo completo: robô -> Google Drive -> Google Sheets) e acompanha
o robô ao vivo pelo log. Não exibe a URL do webhook nem chaves na tela.

Uso:  powershell -ExecutionPolicy Bypass -File scripts\demo.ps1
      -Sequencial  envia uma consulta por vez, esperando cada uma terminar
                   (o padrão envia todas juntas)
#>
param([switch]$Sequencial, [int]$TimeoutS = 300)
$ErrorActionPreference = "Stop"
$raiz = Split-Path $PSScriptRoot -Parent
$log = Join-Path $raiz "logs\api.log"

function Escrever([string]$texto, [string]$cor = "Gray") { Write-Host $texto -ForegroundColor $cor }

# --- Verificações antes de gravar --------------------------------------------
$linhaWebhook = Get-Content (Join-Path $raiz ".env") | Where-Object { $_ -match "^\s*ACTIVEPIECES_WEBHOOK_URL\s*=" }
$webhook = if ($linhaWebhook) { ($linhaWebhook -split "=", 2)[1].Trim() }
if (-not $webhook) { throw "Defina ACTIVEPIECES_WEBHOOK_URL no .env" }
if (-not (Test-Path $log)) { throw "Log não encontrado; suba o robô com scripts\iniciar_local.ps1" }
try { Invoke-RestMethod "http://127.0.0.1:8000/health" -TimeoutSec 5 | Out-Null }
catch { throw "A API não está no ar; rode scripts\iniciar_local.ps1" }
$tunel = Get-Content (Join-Path $raiz "logs\url_atual.txt") -ErrorAction SilentlyContinue
try { Invoke-RestMethod "$tunel/health" -TimeoutSec 15 | Out-Null }
catch { throw "O túnel não responde; rode scripts\parar_local.ps1 e scripts\iniciar_local.ps1" }

# NIS usado no cenário "NIS existente": defina DEMO_NIS no .env (não versionado).
$linhaNis = Get-Content (Join-Path $raiz ".env") | Where-Object { $_ -match "^\s*DEMO_NIS\s*=" }
$nisDemo = if ($linhaNis) { ($linhaNis -split "=", 2)[1].Trim() }
if (-not $nisDemo) { throw "Defina DEMO_NIS no .env (um NIS válido para o cenário de sucesso)" }

$cenarios = @(
    @{ rotulo = "Nome existente";              termo = "MARIA DA SILVA";       filtro = $false },
    @{ rotulo = "Nome inexistente";            termo = "NOME XYZ INEXISTENTE"; filtro = $false },
    @{ rotulo = "NIS existente (API oficial)"; termo = $nisDemo;              filtro = $false },
    @{ rotulo = "CPF inexistente";             termo = "52998224725";          filtro = $false },
    @{ rotulo = "Sobrenome + filtro social";   termo = "SILVA";                filtro = $true }
)

# --- Funções -----------------------------------------------------------------
$script:lidas = @(Get-Content $log -Encoding UTF8).Count  # só interessam linhas novas
$script:finalizadas = 0
$script:recebidas = 0

function Enviar($c) {
    $corpo = @{ termo = $c.termo; filtro_beneficiario_programa_social = $c.filtro } | ConvertTo-Json -Compress
    Invoke-RestMethod -Method Post -Uri $webhook -ContentType "application/json; charset=utf-8" `
        -Body ([Text.Encoding]::UTF8.GetBytes($corpo)) | Out-Null
    Escrever ("  [enviado] {0,-28} {1}" -f $c.rotulo, $c.termo) Green
}

function Acompanhar([int]$ate, [int]$timeoutS) {
    # Mostra as linhas novas do log até $ate consultas finalizadas
    $inicio = Get-Date
    while ($script:finalizadas -lt $ate) {
        $decorrido = ((Get-Date) - $inicio).TotalSeconds
        if ($script:recebidas -eq 0 -and $decorrido -gt 45) {
            Escrever ""
            Escrever "Nenhuma consulta chegou ao robô em 45s." Red
            Escrever "Confira no Activepieces se o passo HTTP usa a URL atual do túnel e se o flow foi publicado:" Red
            Escrever "  $tunel/api/v1/consultas" Yellow
            exit 1
        }
        if ($decorrido -gt $timeoutS) { return $false }
        Start-Sleep -Milliseconds 800
        $todas = @(Get-Content $log -Encoding UTF8)
        if ($todas.Count -le $script:lidas) { continue }
        foreach ($linha in $todas[$script:lidas..($todas.Count - 1)] | Where-Object { $_ }) {
            if ($linha -notmatch "^\S+ (\d\d:\d\d:\d\d),\d+ \| \w+\s+\| [\w.]+ \| (.*)$") { continue }
            $hora, $msg = $Matches[1], $Matches[2]
            if ($msg -match "\] Consulta (NOME|CPF|NIS) ") { $script:recebidas++ }
            $cor = switch -Regex ($msg) {
                "Finalizada: sucesso" { "Green"; $script:finalizadas++; break }
                "Finalizada: erro"    { "Yellow"; $script:finalizadas++; break }
                "CAPTCHA"             { "Magenta"; break }
                "falhou"              { "DarkYellow"; break }
                default               { "Gray" }
            }
            Escrever "  $hora  $msg" $cor
        }
        $script:lidas = $todas.Count
    }
    return $true
}

# --- Demonstração ------------------------------------------------------------
Clear-Host
Escrever "=================================================================" DarkCyan
Escrever "  Robô Portal da Transparência  |  Python + Playwright + FastAPI" Cyan
Escrever "  Hiperautomação: Activepieces -> Google Drive -> Google Sheets" Cyan
Escrever "=================================================================" DarkCyan
Escrever ""

$completo = $true
if ($Sequencial) {
    Escrever "Enviando $($cenarios.Count) consultas pelo webhook, uma por vez..." White
    $n = 0
    foreach ($c in $cenarios) {
        Escrever ""
        Enviar $c
        $n++
        if (-not (Acompanhar $n $TimeoutS)) { $completo = $false; break }
    }
} else {
    Escrever "Disparando $($cenarios.Count) consultas pelo webhook (simultâneas)..." White
    foreach ($c in $cenarios) { Enviar $c; Start-Sleep -Milliseconds 700 }
    Escrever ""
    Escrever "Acompanhando o robô ao vivo..." White
    $completo = Acompanhar $cenarios.Count $TimeoutS
}

Escrever ""
if ($completo) {
    Escrever "Concluído: $($script:finalizadas) consultas processadas." Cyan
    Escrever "Confira os JSONs no Google Drive e as linhas na planilha." Cyan
} else {
    Escrever "Tempo de acompanhamento esgotado ($($script:finalizadas)/$($cenarios.Count) finalizadas)." Yellow
}
