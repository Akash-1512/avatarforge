# Phase 6 verification — observability + eval harness.
# Prereqs: .\make.ps1 dev (now includes the mlflow service)
$ErrorActionPreference = "Stop"
$base = "http://localhost:8000/api/v1"

Write-Host "`n[1/4] MLflow server health..." -ForegroundColor Cyan
$mlflow = Invoke-WebRequest "http://127.0.0.1:5000/health" -UseBasicParsing
Write-Host "  MLflow: HTTP $($mlflow.StatusCode)  UI: http://localhost:5000"

Write-Host "`n[2/4] Run eval harness (3 cases, judge on -> ~6 real LLM calls, ~`$0.003)..." -ForegroundColor Cyan
docker compose run --rm --no-deps api python -m backend.evals.runner --limit 3
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Regression gate FAILED — inspect the aggregate table above" -ForegroundColor Red
} else {
    Write-Host "  Regression gate PASSED" -ForegroundColor Green
}

Write-Host "`n[3/4] Operational metrics from audit tables..." -ForegroundColor Cyan
Invoke-RestMethod "$base/metrics/summary" | ConvertTo-Json -Depth 5

Write-Host "`n[4/4] Where to look:" -ForegroundColor Cyan
Write-Host "  MLflow UI:       http://localhost:5000  (experiments: avatarforge, avatarforge-evals)"
Write-Host "  - 'avatarforge' fills with parent+stage runs every time a video job completes"
Write-Host "  - 'avatarforge-evals' has one run per eval execution with the full report JSON"
Write-Host "  Langfuse (optional): set LANGFUSE_PUBLIC_KEY/SECRET_KEY in .env (free: cloud.langfuse.com)"
