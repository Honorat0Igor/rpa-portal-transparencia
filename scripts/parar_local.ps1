<#
Encerra a API e o túnel iniciados por scripts\iniciar_local.ps1.
Uso:  powershell -ExecutionPolicy Bypass -File scripts\parar_local.ps1
#>
$logs = Join-Path (Split-Path $PSScriptRoot -Parent) "logs"

foreach ($nome in "tunel", "api") {
    $arquivoPid = Join-Path $logs "$nome.pid"
    if (-not (Test-Path $arquivoPid)) { continue }
    $processo = Get-Process -Id ([int](Get-Content $arquivoPid)) -ErrorAction SilentlyContinue
    if ($processo) {
        Stop-Process -Id $processo.Id -Force -Confirm:$false
        Write-Host "Encerrado: $nome (PID $($processo.Id))"
    }
    Remove-Item $arquivoPid
}
Remove-Item (Join-Path $logs "url_atual.txt") -ErrorAction SilentlyContinue
