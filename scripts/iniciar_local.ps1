<#
Sobe a API (Uvicorn, 1 worker) e o túnel do Cloudflare em segundo plano, sem
terminais abertos. Ao final mostra a URL pública (que muda a cada túnel novo)
e a copia para a área de transferência.

Uso:  powershell -ExecutionPolicy Bypass -File scripts\iniciar_local.ps1
Logs: logs\api.log, logs\tunel.log   |   URL atual: logs\url_atual.txt
#>
param([switch]$SemAviso)  # não mostra a janela final (útil em terminal)
$ErrorActionPreference = "Stop"
$raiz = Split-Path $PSScriptRoot -Parent
$logs = Join-Path $raiz "logs"
New-Item -ItemType Directory -Force $logs | Out-Null

function Test-Api {
    try { (Invoke-RestMethod "http://127.0.0.1:8000/health" -TimeoutSec 3).status -eq "ok" } catch { $false }
}

function Get-ProcessoSalvo([string]$arquivoPid) {
    if (-not (Test-Path $arquivoPid)) { return $null }
    Get-Process -Id ([int](Get-Content $arquivoPid)) -ErrorAction SilentlyContinue
}

# --- API --------------------------------------------------------------------
if (Test-Api) {
    Write-Host "API já está no ar"
} else {
    $env:PYTHONIOENCODING = "utf-8"  # log com acentos legíveis (lido em UTF-8 pelo demo)
    $api = Start-Process -FilePath (Join-Path $raiz ".venv\Scripts\python.exe") `
        -ArgumentList "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000" `
        -WorkingDirectory $raiz -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $logs "api.out.log") -RedirectStandardError (Join-Path $logs "api.log")
    $api.Id | Set-Content (Join-Path $logs "api.pid")
    $limite = (Get-Date).AddSeconds(90)
    while (-not (Test-Api)) {
        if ($api.HasExited -or (Get-Date) -gt $limite) { throw "A API não subiu; veja logs\api.log" }
        Start-Sleep 2
    }
    Write-Host "API no ar (PID $($api.Id))"
}

# --- Túnel ------------------------------------------------------------------
$arquivoUrl = Join-Path $logs "url_atual.txt"
$tunel = Get-ProcessoSalvo (Join-Path $logs "tunel.pid")
if ($tunel -and (Test-Path $arquivoUrl)) {
    $url = Get-Content $arquivoUrl
    Write-Host "Túnel já está no ar"
} else {
    $cloudflared = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
    if (-not $cloudflared) { $cloudflared = "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe" }
    $logTunel = Join-Path $logs "tunel.log"
    Remove-Item $logTunel -ErrorAction SilentlyContinue
    $tunel = Start-Process -FilePath $cloudflared `
        -ArgumentList "tunnel", "--no-autoupdate", "--url", "http://127.0.0.1:8000", "--logfile", "`"$logTunel`"" `
        -WindowStyle Hidden -PassThru
    $tunel.Id | Set-Content (Join-Path $logs "tunel.pid")
    $url = $null
    $limite = (Get-Date).AddSeconds(60)
    while (-not $url) {
        if ($tunel.HasExited -or (Get-Date) -gt $limite) { throw "O túnel não subiu; veja logs\tunel.log" }
        Start-Sleep 2
        if (Test-Path $logTunel) {
            $achado = Select-String -Path $logTunel -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" | Select-Object -First 1
            if ($achado) { $url = $achado.Matches[0].Value }
        }
    }
    $url | Set-Content $arquivoUrl
    Write-Host "Túnel no ar (PID $($tunel.Id))"
}

$endpoint = "$url/api/v1/consultas"
Set-Clipboard $endpoint
Write-Host "URL para o Activepieces (copiada): $endpoint"
if ($SemAviso) { return }
(New-Object -ComObject WScript.Shell).Popup(
    "Robô no ar.`n`nURL para o passo HTTP do Activepieces (já copiada):`n$endpoint`n`nSe ela mudou, cole no flow e clique em Publicar.",
    0, "Robô Portal da Transparência", 64) | Out-Null
