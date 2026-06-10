# Phase 2 verification — run after: .\make.ps1 dev
# Tests the live script endpoint, then failure injection for the fallback path.

$base = "http://localhost:8000/api/v1"

Write-Host "`n[1/4] Health check..." -ForegroundColor Cyan
Invoke-RestMethod "$base/health" | ConvertTo-Json -Compress

Write-Host "`n[2/4] Generate a real script (uses your configured provider)..." -ForegroundColor Cyan
$body = @{ topic = "Why daily walking improves focus"; tone = "casual"; duration_seconds = 45 } | ConvertTo-Json
try {
    $r = Invoke-RestMethod -Method Post -Uri "$base/script/generate" -ContentType "application/json" -Body $body
    Write-Host "  Title:    $($r.title)"
    Write-Host "  Provider: $($r.provider_used)  Model: $($r.model)  Latency: $($r.latency_ms)ms"
    Write-Host "  Segments: $($r.segments.Count)  Tokens: $($r.usage.total_tokens)  Cost: `$$($r.usage.estimated_cost_usd)"
    Write-Host "  First line: $($r.segments[0].text)"
} catch {
    Write-Host "  FAILED: $($_.ErrorDetails.Message)" -ForegroundColor Red
    Write-Host "  (No valid API key in .env? Add AZURE_OPENAI_* or OPENAI_API_KEY and restart: .\make.ps1 down; .\make.ps1 dev)" -ForegroundColor Yellow
}

Write-Host "`n[3/4] Validation guard (expect 422)..." -ForegroundColor Cyan
try {
    Invoke-RestMethod -Method Post -Uri "$base/script/generate" -ContentType "application/json" -Body '{"topic":"ab"}'
} catch {
    Write-Host "  Got $($_.Exception.Response.StatusCode.value__) as expected"
}

Write-Host "`n[4/4] Token usage audit rows in Postgres..." -ForegroundColor Cyan
docker compose exec -T postgres psql -U avatarforge -d avatarforge -c "SELECT provider, model, total_tokens, estimated_cost_usd, latency_ms, success FROM token_usage ORDER BY id DESC LIMIT 5;"

Write-Host "`nFallback test (manual): put a wrong AZURE_OPENAI_API_KEY in .env, restart, rerun [2] —" -ForegroundColor Yellow
Write-Host "provider_used should flip to 'openai' and logs will show provider_failed_falling_back." -ForegroundColor Yellow
