param(
    [switch]$NoBuild
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location -LiteralPath $repoRoot

if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is required to run the ProdMind demo."
}
docker compose version | Out-Null

Write-Host "Starting the ProdMind demo stack..."
if ($NoBuild) {
    docker compose up -d
} else {
    docker compose up -d --build
}
if ($LASTEXITCODE -ne 0) { throw "docker compose up failed." }

function Wait-ProdMindHttp {
    param(
        [string]$Name,
        [string]$Url,
        [int]$Attempts = 90
    )
    for ($attempt = 1; $attempt -le $Attempts; $attempt++) {
        try {
            Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 3 | Out-Null
            Write-Host "Ready: $Name"
            return
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    docker compose ps
    docker compose logs --tail=80 prodmind-server demo-user-service
    throw "Timed out waiting for $Name at $Url"
}

$apiPort = if ($env:PRODMIND_API_PORT) { $env:PRODMIND_API_PORT } else { "8088" }
Wait-ProdMindHttp -Name "ProdMind API" -Url "http://localhost:$apiPort/health"
Wait-ProdMindHttp -Name "customer demo" -Url "http://localhost:8090/actuator/health"
Wait-ProdMindHttp -Name "Prometheus" -Url "http://localhost:9090/-/ready"

Write-Host ""
Write-Host "ProdMind is ready."
Write-Host "Customer demo:   http://localhost:8090"
Write-Host "Multi-service:   http://localhost:8090/multiservice.html"
Write-Host "Engineer viewer: http://localhost:$apiPort/engineer"
Write-Host "API docs:        http://localhost:$apiPort/docs"
Write-Host ""
Write-Host "Local project: demo"
Write-Host "Engineer key:  demo-engineer-key"
Write-Host ""
Write-Host "Stop without deleting data: .\scripts\demo-down.ps1"
Write-Host "Stop and reset demo data:   .\scripts\demo-down.ps1 -Volumes"
