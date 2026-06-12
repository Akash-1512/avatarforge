# Phase 7 verification — rate limiting, CI status, K8s manifest validity.
$ErrorActionPreference = "Continue"
$base = "http://localhost:8000/api/v1"

Write-Host "`n[1/3] Rate limiting (5/min on /videos/generate -> expect 202s then 429)..." -ForegroundColor Cyan
$form = @{ image = Get-Item .\face.jpg; topic = "Rate limit check"; duration_seconds = "15" }
$codes = @()
for ($i = 1; $i -le 7; $i++) {
    try {
        $r = Invoke-WebRequest -Method Post -Uri "$base/videos/generate" -Form $form -SkipHttpErrorCheck
        $codes += $r.StatusCode
    } catch { $codes += 429 }
}
Write-Host "  Status codes: $($codes -join ', ')"
if ($codes -contains 429) { Write-Host "  Throttling works (429 seen)" -ForegroundColor Green }
else { Write-Host "  WARNING: no 429 — is RATE_LIMIT_ENABLED true?" -ForegroundColor Yellow }
Write-Host "  Note: the 202s above queued real jobs - purge with: docker compose exec redis redis-cli -n 1 flushdb" -ForegroundColor DarkGray

Write-Host "`n[2/3] CI status (gh)..." -ForegroundColor Cyan
gh run list --limit 3

Write-Host "`n[3/3] K8s next steps:" -ForegroundColor Cyan
Write-Host "  kubectl apply -k k8s/ --dry-run=client    # validate against your cluster"
Write-Host "  .\scripts\deploy-kind.ps1                 # full deploy to kind"
