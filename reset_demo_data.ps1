# Deletes the three demo databases. Each service re-creates and re-seeds its database on the next start.
# Stop the services first. Always reset all three together so the sample records stay consistent.
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
foreach ($f in "police-service\police.db", "judiciary-service\judiciary.db", "correctional-service\correctional.db") {
  $p = Join-Path $root $f
  if (Test-Path $p) { Remove-Item $p; Write-Host "deleted $f" }
}
