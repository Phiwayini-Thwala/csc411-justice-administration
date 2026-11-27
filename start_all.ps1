# Starts the three services, each in its own PowerShell window, then opens the portal.
# Run from the repository root:   powershell -ExecutionPolicy Bypass -File .\start_all.ps1
# First time only:  pip install -r police-service\requirements.txt -r judiciary-service\requirements.txt -r correctional-service\requirements.txt
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $env:JWT_SECRET) { $env:JWT_SECRET = "dev-only-shared-secret-change-me-32chars" }   # same value in all three
$services = @(
  @{ name = "police-service";       port = 8001 },
  @{ name = "judiciary-service";    port = 8002 },
  @{ name = "correctional-service"; port = 8003 }
)
foreach ($s in $services) {
  $dir = Join-Path $root $s.name
  Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "`$env:JWT_SECRET='$($env:JWT_SECRET)'; Set-Location '$dir'; python -m uvicorn main:app --port $($s.port) --reload"
}
Start-Sleep -Seconds 4
Start-Process (Join-Path $root "frontend\index.html")
Write-Host "Police       http://localhost:8001/ui"
Write-Host "Judiciary    http://localhost:8002/ui"
Write-Host "Correctional http://localhost:8003/ui"
