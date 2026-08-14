param(
    [switch]$Volumes
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location -LiteralPath $repoRoot

if ($Volumes) {
    docker compose down --remove-orphans --volumes
} else {
    docker compose down --remove-orphans
}
if ($LASTEXITCODE -ne 0) { throw "docker compose down failed." }

if ($Volumes) {
    Write-Host "ProdMind demo stopped and local demo volumes removed."
} else {
    Write-Host "ProdMind demo stopped; local demo volumes were preserved."
}
