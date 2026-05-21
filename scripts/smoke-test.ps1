# NotAI - smoke test PowerShell (equivalente di scripts/smoke-test.sh per host Windows).
# Eseguire DOPO `docker compose -f compose.yml -f compose.dev.yml up -d`.

[CmdletBinding()]
param(
    [string]$ApiBase = "http://localhost:8000",
    [string]$MinioBase = "http://localhost:9000",
    [string]$QdrantBase = "http://localhost:6333",
    [string]$TemporalUi = "http://localhost:8088",
    [int]$TimeoutSeconds = 300
)

$ErrorActionPreference = "Stop"

function Wait-Endpoint {
    param([string]$Name, [string]$Url)
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $null = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            Write-Host "[ok] $Name pronto ($Url)" -ForegroundColor Green
            return
        } catch {
            Start-Sleep -Seconds 3
        }
    }
    Write-Host "[KO] $Name non pronto entro ${TimeoutSeconds}s ($Url)" -ForegroundColor Red
    exit 1
}

Write-Host "==> NotAI smoke test (timeout ${TimeoutSeconds}s)" -ForegroundColor Yellow

Wait-Endpoint -Name "api /health"   -Url "$ApiBase/health"
Wait-Endpoint -Name "api /readyz"   -Url "$ApiBase/readyz"
Wait-Endpoint -Name "minio live"    -Url "$MinioBase/minio/health/live"
Wait-Endpoint -Name "qdrant readyz" -Url "$QdrantBase/readyz"
Wait-Endpoint -Name "temporal-ui"   -Url $TemporalUi

$ready = (Invoke-WebRequest -Uri "$ApiBase/readyz" -UseBasicParsing).Content | ConvertFrom-Json
if ($ready.status -eq "ok") {
    Write-Host "[ok] /readyz globale = ok" -ForegroundColor Green
} else {
    Write-Host "[KO] /readyz globale = $($ready.status)" -ForegroundColor Red
    $ready | ConvertTo-Json -Depth 5
    exit 1
}

Write-Host "==> smoke test passato" -ForegroundColor Green
