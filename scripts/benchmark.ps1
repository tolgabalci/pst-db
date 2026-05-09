param(
  [string]$ApiBase = "http://localhost:8000",
  [string]$Query = "contract project meeting attachment",
  [int]$Runs = 10
)

$ErrorActionPreference = "Stop"

$durations = @()
for ($i = 0; $i -lt $Runs; $i++) {
  $elapsed = Measure-Command {
    Invoke-RestMethod "$ApiBase/api/search?q=$([uri]::EscapeDataString($Query))&mode=all&limit=50&offset=0" | Out-Null
  }
  $durations += $elapsed.TotalMilliseconds
  Write-Host ("Run {0}: {1:N0} ms" -f ($i + 1), $elapsed.TotalMilliseconds)
}

$average = ($durations | Measure-Object -Average).Average
$max = ($durations | Measure-Object -Maximum).Maximum
Write-Host ("Average: {0:N0} ms" -f $average)
Write-Host ("Max:     {0:N0} ms" -f $max)

