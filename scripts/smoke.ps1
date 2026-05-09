param(
  [string]$ApiBase = "http://localhost:8000",
  [string]$WebBase = "http://localhost:5173"
)

$ErrorActionPreference = "Stop"

function Wait-RestMethod {
  param(
    [string]$Uri,
    [int]$TimeoutSeconds = 60
  )
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    try {
      return Invoke-RestMethod $Uri
    } catch {
      Start-Sleep -Seconds 2
    }
  } while ((Get-Date) -lt $deadline)
  return Invoke-RestMethod $Uri
}

function Wait-WebRequest {
  param(
    [string]$Uri,
    [int]$TimeoutSeconds = 60
  )
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    try {
      return Invoke-WebRequest $Uri -UseBasicParsing
    } catch {
      Start-Sleep -Seconds 2
    }
  } while ((Get-Date) -lt $deadline)
  return Invoke-WebRequest $Uri -UseBasicParsing
}

Write-Host "Checking API health..."
$health = Wait-RestMethod "$ApiBase/api/health"
Write-Host "API status: $($health.status), model: $($health.ollama_model)"

Write-Host "Checking web UI..."
$web = Wait-WebRequest $WebBase
if ($web.StatusCode -ne 200) {
  throw "Web UI returned status $($web.StatusCode)"
}

Write-Host "Scanning import folder..."
$scan = Invoke-RestMethod "$ApiBase/api/imports/scan" -Method Post
Write-Host "Found $($scan.files.Count) PST file(s)."

$scanGet = Invoke-RestMethod "$ApiBase/api/imports/scan"
if ($scanGet.files.Count -ne $scan.files.Count) {
  throw "GET and POST import scans returned different file counts."
}

Write-Host "Running empty search..."
$search = Invoke-RestMethod "$ApiBase/api/search?q=&mode=all&limit=5&offset=0"
Write-Host "Search endpoint returned $($search.total) total result(s)."

Write-Host "Smoke check completed."
