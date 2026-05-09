$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) {
  throw "Docker was not found on PATH."
}

& $docker.Source compose down

Write-Host "PST search services stopped. Imported data was preserved under data\\."
