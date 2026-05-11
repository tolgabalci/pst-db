param(
  [string]$Model = $(if ($env:OLLAMA_MODEL) { $env:OLLAMA_MODEL } else { "embeddinggemma" }),
  [int]$OllamaPort = $(if ($env:OLLAMA_PORT) { [int]$env:OLLAMA_PORT } else { 11434 }),
  [string]$Since = "",
  [int]$Tail = 500,
  [switch]$RequireGpu,
  [switch]$FailOnEmbeddingContextErrors,
  [switch]$SkipProbe
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) {
  throw "Docker was not found on PATH."
}

if (-not $SkipProbe) {
  $ollamaBase = "http://127.0.0.1:$OllamaPort"
  $body = @{ model = $Model; input = @("embedding runtime diagnostic") } | ConvertTo-Json -Depth 5
  try {
    Invoke-RestMethod "$ollamaBase/api/embed" -Method Post -ContentType "application/json" -Body $body | Out-Null
  } catch {
    Write-Warning "Unable to run Ollama embedding probe at $ollamaBase. Existing loaded-model state will be checked. Error: $($_.Exception.Message)"
  }
}

$psOutput = & $docker.Source compose exec -T ollama ollama ps
if ($LASTEXITCODE -ne 0) {
  throw "Unable to run 'ollama ps' inside the Ollama container."
}

$modelBase = $Model.Split(":")[0]
$modelPattern = "^\s*$([regex]::Escape($modelBase))(:latest)?\s{2,}"
$modelLine = @($psOutput | Where-Object { $_ -match $modelPattern } | Select-Object -First 1)
$processor = $null
if ($modelLine.Count -gt 0) {
  $fields = @([regex]::Split($modelLine[0].Trim(), "\s{2,}") | Where-Object { $_ })
  if ($fields.Count -ge 4) {
    $processor = $fields[3]
  }
}

$logArgs = @("compose", "logs", "--tail=$Tail")
if ($Since) {
  $logArgs += @("--since", $Since)
}
$logArgs += "ollama"
$logs = @(& $docker.Source @logArgs 2>&1)
if ($LASTEXITCODE -ne 0) {
  throw "Unable to read Ollama container logs."
}

$contextErrors = @($logs | Where-Object { $_ -match "(?i)(llm embedding error:.*input length exceeds.*context length|input length exceeds the context length)" })
$gpuEvidence = @($logs | Where-Object { $_ -match "(?i)(loaded CUDA backend|found \d+ CUDA devices|offloaded (?!0/)\d+/\d+ layers to GPU|device=CUDA|library=CUDA)" })
$cpuEvidence = @($logs | Where-Object { $_ -match "(?i)(no compatible GPUs|no GPU detected|library=CPU|processor\s+.*CPU|offloaded 0/\d+ layers to GPU)" })

if ($processor) {
  Write-Host "Ollama model processor: $processor"
} else {
  Write-Warning "Model '$Model' was not listed by 'ollama ps'. The model may not be loaded."
}

$nvidiaSmi = Get-Command nvidia-smi -ErrorAction SilentlyContinue
if ($nvidiaSmi) {
  $gpuSnapshot = & $nvidiaSmi.Source --query-gpu=name,utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits 2>$null
  if ($LASTEXITCODE -eq 0 -and $gpuSnapshot) {
    Write-Host "nvidia-smi snapshot: $gpuSnapshot"
  }
}

if ($gpuEvidence.Count -gt 0) {
  Write-Host "GPU log evidence: $($gpuEvidence.Count) line(s)."
  $gpuEvidence | Select-Object -First 5 | ForEach-Object { Write-Host "  $_" }
}
if ($cpuEvidence.Count -gt 0) {
  Write-Warning "CPU/no-GPU log evidence: $($cpuEvidence.Count) line(s)."
  $cpuEvidence | Select-Object -First 5 | ForEach-Object { Write-Warning "  $_" }
}
if ($contextErrors.Count -gt 0) {
  Write-Warning "Embedding context-length errors: $($contextErrors.Count) line(s)."
  $contextErrors | Select-Object -First 10 | ForEach-Object { Write-Warning "  $_" }
}

$usesGpu = $processor -and ($processor -match "\bGPU\b")
if ($RequireGpu -and -not $usesGpu) {
  throw "Ollama is not reporting GPU execution for '$Model'. Processor='$processor'."
}
if ($FailOnEmbeddingContextErrors -and $contextErrors.Count -gt 0) {
  throw "Ollama embedding context-length errors were detected in the checked log window."
}

Write-Host "Embedding runtime check completed."
