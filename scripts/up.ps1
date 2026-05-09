param(
  [switch]$PullEmbeddingModel
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

Set-Location $root

$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) {
  throw "Docker was not found on PATH. Install/start Rancher Desktop or Docker Desktop, then retry."
}

& $docker.Source info *> $null
if ($LASTEXITCODE -ne 0) {
  throw "Docker is installed but the daemon is not reachable. Start Rancher Desktop as Administrator, wait until it finishes initializing, then retry."
}

if (!(Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
}

New-Item -ItemType Directory -Force -Path "data/imports", "data/attachments", "data/postgres" | Out-Null

& $docker.Source compose up -d --build

if ($PullEmbeddingModel) {
  Write-Host "Pulling embedding model with Ollama..."
  $pulled = $false
  for ($i = 0; $i -lt 20; $i++) {
    & $docker.Source compose exec ollama ollama pull embeddinggemma
    if ($LASTEXITCODE -eq 0) {
      $pulled = $true
      break
    }
    Start-Sleep -Seconds 3
  }
  if (-not $pulled) {
    throw "Ollama did not become ready in time to pull embeddinggemma."
  }
}

Write-Host ""
Write-Host "PST search is starting."
Write-Host "Web UI:  http://localhost:5173"
Write-Host "API:     http://localhost:8000/docs"
Write-Host "Imports: $root\data\imports"
Write-Host ""
Write-Host "Copy PST files into data\\imports, then use the Import screen."
