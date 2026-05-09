param(
  [string]$SamplePstPath = "",
  [string]$SamplePstUrl = "https://raw.githubusercontent.com/SpongeData-cz/gopst/main/fixtures/simple.pst",
  [int]$TimeoutSeconds = 300,
  [switch]$KeepRunning
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$rootPath = (Resolve-Path $root).Path
$e2eRoot = Join-Path $root "tmp\e2e"
$e2ePath = Join-Path $rootPath "tmp\e2e"
$importsPath = Join-Path $e2ePath "imports"
$attachmentsPath = Join-Path $e2ePath "attachments"
$postgresPath = Join-Path $e2ePath "postgres"
$fixtureName = "SMALL_FIXTURE.PST"
$apiBase = "http://127.0.0.1:18000"
$webBase = "http://127.0.0.1:15173"
$projectName = "pst-db-e2e"
$model = if ($env:OLLAMA_MODEL) { $env:OLLAMA_MODEL } else { "embeddinggemma" }

Set-Location $root

$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) {
  throw "Docker was not found on PATH."
}

$cleanupEnv = @{
  COMPOSE_PROJECT_NAME = $env:COMPOSE_PROJECT_NAME
  POSTGRES_PORT = $env:POSTGRES_PORT
  TIKA_PORT = $env:TIKA_PORT
  OLLAMA_PORT = $env:OLLAMA_PORT
  API_PORT = $env:API_PORT
  WEB_PORT = $env:WEB_PORT
  POSTGRES_DATA_HOST = $env:POSTGRES_DATA_HOST
  IMPORTS_HOST = $env:IMPORTS_HOST
  ATTACHMENTS_HOST = $env:ATTACHMENTS_HOST
  OLLAMA_VOLUME = $env:OLLAMA_VOLUME
  OLLAMA_VOLUME_EXTERNAL = $env:OLLAMA_VOLUME_EXTERNAL
}
$env:COMPOSE_PROJECT_NAME = $projectName
$env:POSTGRES_PORT = "15432"
$env:TIKA_PORT = "19998"
$env:OLLAMA_PORT = "11435"
$env:API_PORT = "18000"
$env:WEB_PORT = "15173"
$env:POSTGRES_DATA_HOST = "./tmp/e2e/postgres"
$env:IMPORTS_HOST = "./tmp/e2e/imports"
$env:ATTACHMENTS_HOST = "./tmp/e2e/attachments"
$env:OLLAMA_VOLUME = "pst-db_ollama"
$env:OLLAMA_VOLUME_EXTERNAL = "true"
& $docker.Source volume inspect pst-db_ollama *> $null
if ($LASTEXITCODE -ne 0) {
  & $docker.Source volume create pst-db_ollama *> $null
}
& $docker.Source compose down --remove-orphans *> $null
foreach ($key in $cleanupEnv.Keys) {
  if ($null -eq $cleanupEnv[$key]) {
    Remove-Item -Path "Env:$key" -ErrorAction SilentlyContinue
  } else {
    Set-Item -Path "Env:$key" -Value $cleanupEnv[$key]
  }
}

if (Test-Path $e2eRoot) {
  $resolved = (Resolve-Path $e2eRoot).Path
  $tmpRoot = Join-Path $rootPath "tmp"
  if (-not $resolved.StartsWith($tmpRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to remove unexpected E2E directory: $resolved"
  }
  Remove-Item -LiteralPath $resolved -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $importsPath, $attachmentsPath, $postgresPath | Out-Null
$fixturePath = Join-Path $importsPath $fixtureName
if ($SamplePstPath) {
  Copy-Item -LiteralPath $SamplePstPath -Destination $fixturePath -Force
} else {
  Invoke-WebRequest $SamplePstUrl -OutFile $fixturePath
}

$previousEnv = @{
  COMPOSE_PROJECT_NAME = $env:COMPOSE_PROJECT_NAME
  POSTGRES_PORT = $env:POSTGRES_PORT
  TIKA_PORT = $env:TIKA_PORT
  OLLAMA_PORT = $env:OLLAMA_PORT
  API_PORT = $env:API_PORT
  WEB_PORT = $env:WEB_PORT
  POSTGRES_DATA_HOST = $env:POSTGRES_DATA_HOST
  IMPORTS_HOST = $env:IMPORTS_HOST
  ATTACHMENTS_HOST = $env:ATTACHMENTS_HOST
  OLLAMA_VOLUME = $env:OLLAMA_VOLUME
  OLLAMA_VOLUME_EXTERNAL = $env:OLLAMA_VOLUME_EXTERNAL
}

try {
  $env:COMPOSE_PROJECT_NAME = $projectName
  $env:POSTGRES_PORT = "15432"
  $env:TIKA_PORT = "19998"
  $env:OLLAMA_PORT = "11435"
  $env:API_PORT = "18000"
  $env:WEB_PORT = "15173"
  $env:POSTGRES_DATA_HOST = "./tmp/e2e/postgres"
  $env:IMPORTS_HOST = "./tmp/e2e/imports"
  $env:ATTACHMENTS_HOST = "./tmp/e2e/attachments"
  $env:OLLAMA_VOLUME = "pst-db_ollama"
  $env:OLLAMA_VOLUME_EXTERNAL = "true"

  & $docker.Source compose up -d --build
  if ($LASTEXITCODE -ne 0) {
    throw "docker compose up failed."
  }

  $modelList = ""
  $ollamaReady = $false
  $modelAvailable = $false
  for ($i = 0; $i -lt 30; $i++) {
    $modelList = & $docker.Source compose exec -T ollama ollama list 2>$null
    if ($LASTEXITCODE -eq 0) {
      $ollamaReady = $true
      if ($modelList -match [regex]::Escape($model)) {
        $modelAvailable = $true
        break
      }
    }
    Start-Sleep -Seconds 2
  }
  if (-not $ollamaReady -or -not $modelAvailable) {
    & $docker.Source compose exec -T ollama ollama pull $model
    if ($LASTEXITCODE -ne 0) {
      throw "Unable to pull Ollama model $model."
    }
  }

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    try {
      $health = Invoke-RestMethod "$apiBase/api/health"
      if ($health.status -eq "ok") {
        break
      }
    } catch {
      Start-Sleep -Seconds 2
    }
  } while ((Get-Date) -lt $deadline)

  if ((Get-Date) -ge $deadline) {
    Write-Host "API logs:"
    & $docker.Source compose logs --tail=100 api
    Write-Host "Postgres logs:"
    & $docker.Source compose logs --tail=100 postgres
    throw "API did not become healthy within $TimeoutSeconds seconds."
  }

  $web = Invoke-WebRequest $webBase -UseBasicParsing
  if ($web.StatusCode -ne 200) {
    throw "Web UI returned status $($web.StatusCode)."
  }

  $scanPost = Invoke-RestMethod "$apiBase/api/imports/scan" -Method Post
  $scanGet = Invoke-RestMethod "$apiBase/api/imports/scan"
  foreach ($scan in @($scanPost, $scanGet)) {
    if (-not ($scan.files | Where-Object { $_.filename -ceq $fixtureName })) {
      throw "Scan endpoint did not return $fixtureName."
    }
  }

  $job = Invoke-RestMethod "$apiBase/api/imports" `
    -Method Post `
    -ContentType "application/json" `
    -Body (@{ source_path = $fixtureName } | ConvertTo-Json)

  do {
    Start-Sleep -Seconds 2
    $jobDetail = Invoke-RestMethod "$apiBase/api/imports/$($job.id)"
    $status = $jobDetail.job.status
    Write-Host "Import status: $status, processed=$($jobDetail.job.processed_count), inserted=$($jobDetail.job.inserted_count), semantic=$($jobDetail.job.semantic_indexed_count)"
    if ($status -eq "completed") {
      break
    }
    if ($status -eq "failed") {
      throw "Import failed: $($jobDetail.job.last_error)"
    }
  } while ((Get-Date) -lt $deadline)

  if ($status -ne "completed") {
    throw "Import did not complete within $TimeoutSeconds seconds."
  }
  if ($jobDetail.job.inserted_count -lt 1) {
    throw "Import completed without inserting an email."
  }
  if ($jobDetail.job.semantic_indexed_count -lt 1) {
    throw "Import completed without semantic indexing."
  }

  $keyword = Invoke-RestMethod "$apiBase/api/search?q=Aspose.Email&mode=keyword&limit=10&offset=0"
  if ($keyword.total -lt 1) {
    throw "Keyword search did not find the sample PST email."
  }

  $semantic = Invoke-RestMethod "$apiBase/api/search?q=end%20user%20license%20agreement&mode=semantic&limit=10&offset=0"
  if ($semantic.total -lt 1) {
    throw "Semantic search did not find the sample PST email."
  }

  $author = Invoke-RestMethod "$apiBase/api/search?q=&mode=all&author=from%40domain.com&limit=10&offset=0"
  if ($author.total -lt 1) {
    throw "Author filter did not find from@domain.com."
  }

  $emailId = $keyword.results[0].id
  $detail = Invoke-RestMethod "$apiBase/api/emails/$emailId"
  if ($detail.subject -notmatch "Aspose.Email") {
    throw "Email detail did not return the imported sample message."
  }

  Invoke-RestMethod "$apiBase/api/emails/$emailId/favorite" `
    -Method Patch `
    -ContentType "application/json" `
    -Body (@{ is_favorite = $true } | ConvertTo-Json) | Out-Null
  $noteText = "E2E sample searchable note"
  Invoke-RestMethod "$apiBase/api/emails/$emailId/note" `
    -Method Put `
    -ContentType "application/json" `
    -Body (@{ note = $noteText } | ConvertTo-Json) | Out-Null
  $updated = Invoke-RestMethod "$apiBase/api/emails/$emailId"
  if (-not $updated.is_favorite -or $updated.note -ne $noteText) {
    throw "Favorite/note annotations did not persist."
  }

  $noteSearch = Invoke-RestMethod "$apiBase/api/search?q=E2E%20sample%20searchable%20note&mode=keyword&limit=10&offset=0"
  if (-not ($noteSearch.results | Where-Object { $_.id -eq $emailId })) {
    throw "Saved note was not included in keyword search."
  }

  Write-Host "Small PST E2E completed successfully."
} finally {
  if (-not $KeepRunning) {
    & $docker.Source compose down
  }

  foreach ($key in $previousEnv.Keys) {
    if ($null -eq $previousEnv[$key]) {
      Remove-Item -Path "Env:$key" -ErrorAction SilentlyContinue
    } else {
      Set-Item -Path "Env:$key" -Value $previousEnv[$key]
    }
  }
}
