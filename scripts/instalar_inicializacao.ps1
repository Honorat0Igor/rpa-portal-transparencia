<#
Faz o robô subir sozinho ao entrar no Windows: cria um atalho para
scripts\iniciar_local.ps1 na pasta Inicializar do usuário (não exige administrador).

Instalar:  powershell -ExecutionPolicy Bypass -File scripts\instalar_inicializacao.ps1
Remover:   powershell -ExecutionPolicy Bypass -File scripts\instalar_inicializacao.ps1 -Remover
#>
param([switch]$Remover)

$atalho = Join-Path ([Environment]::GetFolderPath("Startup")) "Robo Portal Transparencia.lnk"

if ($Remover) {
    Remove-Item $atalho -ErrorAction SilentlyContinue
    Write-Host "Inicialização automática removida"
    return
}

$script = Join-Path $PSScriptRoot "iniciar_local.ps1"
$lnk = (New-Object -ComObject WScript.Shell).CreateShortcut($atalho)
$lnk.TargetPath = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$lnk.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$script`""
$lnk.WorkingDirectory = Split-Path $PSScriptRoot -Parent
$lnk.WindowStyle = 7  # minimizado
$lnk.Description = "Sobe a API e o túnel do robô do Portal da Transparência"
$lnk.Save()
Write-Host "Atalho criado em: $atalho"
