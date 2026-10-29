<#
Publica a API no Google Cloud Run (São Paulo).

Pré-requisitos: projeto GCP com faturamento ativo e `gcloud auth login` feito.
Uso:  .\scripts\deploy_cloudrun.ps1 -Projeto meu-projeto-id

As chaves API_KEY e PORTAL_API_KEY são lidas do .env local e gravadas no
Secret Manager; elas nunca vão para a imagem nem para a linha de comando.
#>
param(
    [Parameter(Mandatory)][string]$Projeto,
    [string]$Regiao = "southamerica-east1",
    [string]$Servico = "robo-portal-transparencia"
)
$ErrorActionPreference = "Stop"

$gcloud = (Get-Command gcloud -ErrorAction SilentlyContinue).Source
if (-not $gcloud) { $gcloud = "$env:LOCALAPPDATA\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd" }

function Invoke-Gcloud {
    & $gcloud @args
    if ($LASTEXITCODE -ne 0) { throw "gcloud falhou: $args" }
}

function Get-ValorEnv([string]$nome) {
    $linha = Get-Content (Join-Path $PSScriptRoot "..\.env") | Where-Object { $_ -match "^\s*$nome\s*=" } | Select-Object -First 1
    if (-not $linha) { return $null }
    return ($linha -split "=", 2)[1].Trim()
}

function Set-Segredo([string]$nome, [string]$valor) {
    # Arquivo temporário sem quebra de linha: o pipe do PowerShell 5.1 acrescentaria CRLF ao segredo
    $tmp = New-TemporaryFile
    try {
        [IO.File]::WriteAllText($tmp.FullName, $valor)
        & $gcloud secrets describe $nome --project $Projeto 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Invoke-Gcloud secrets versions add $nome --data-file $tmp.FullName --project $Projeto
        } else {
            Invoke-Gcloud secrets create $nome --data-file $tmp.FullName --replication-policy automatic --project $Projeto
        }
    } finally {
        Remove-Item $tmp.FullName -Force
    }
}

Write-Host "==> Projeto $Projeto / região $Regiao"
Invoke-Gcloud config set project $Projeto

Write-Host "==> Ativando APIs (Cloud Run, Cloud Build, Artifact Registry, Secret Manager)"
Invoke-Gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com

Write-Host "==> Gravando segredos a partir do .env"
$apiKey = Get-ValorEnv "API_KEY"
if (-not $apiKey -or $apiKey -eq "troque-por-uma-chave-forte") { throw "Defina uma API_KEY forte no .env antes do deploy" }
Set-Segredo "robo-api-key" $apiKey
$segredos = "API_KEY=robo-api-key:latest"
$portalKey = Get-ValorEnv "PORTAL_API_KEY"
if ($portalKey) {
    Set-Segredo "robo-portal-api-key" $portalKey
    $segredos += ",PORTAL_API_KEY=robo-portal-api-key:latest"
}

Write-Host "==> Permissões da conta de serviço padrão (ler segredos e compilar a imagem)"
$numero = & $gcloud projects describe $Projeto --format "value(projectNumber)"
$contaServico = "serviceAccount:$numero-compute@developer.gserviceaccount.com"
foreach ($papel in "roles/secretmanager.secretAccessor", "roles/run.builder") {
    Invoke-Gcloud projects add-iam-policy-binding $Projeto --member $contaServico --role $papel --condition None --quiet | Out-Null
}

Write-Host "==> Build + deploy (leva alguns minutos na primeira vez)"
# 1 instância = 1 Chromium e uma única fila (o semáforo só funciona dentro do processo).
# SAVE_OUTPUT_FILES=false: o disco do Cloud Run é memória; a persistência é o Google Drive.
Invoke-Gcloud run deploy $Servico --source . --region $Regiao `
    --memory 2Gi --cpu 2 --timeout 300 --concurrency 8 `
    --min-instances 0 --max-instances 1 --cpu-boost `
    --set-env-vars "HEADLESS=true,MAX_CONCURRENT_BOTS=2,SAVE_OUTPUT_FILES=false" `
    --set-secrets $segredos `
    --allow-unauthenticated --quiet

$url = & $gcloud run services describe $Servico --region $Regiao --format "value(status.url)"
Write-Host ""
Write-Host "API publicada: $url"
Write-Host "Swagger:       $url/docs"
Write-Host "No Activepieces, use: $url/api/v1/consultas"
