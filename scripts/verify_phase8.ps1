# Phase 8 / v1.0.0 final smoke — every layer except the long render.
$ErrorActionPreference = "Stop"
$base = "http://localhost:8000/api/v1"

Write-Host "`n[1/5] OpenAPI spec + docs..." -ForegroundColor Cyan
$spec = Invoke-RestMethod "http://localhost:8000/openapi.json"
Write-Host "  title: $($spec.info.title)  version: $($spec.info.version)  paths: $($spec.paths.PSObject.Properties.Count)"

Write-Host "`n[2/5] Script generation (real LLM)..." -ForegroundColor Cyan
$s = Invoke-RestMethod -Method Post -Uri "$base/script/generate" -ContentType "application/json" `
  -Body (@{topic="The v1 release smoke test"; duration_seconds=20} | ConvertTo-Json)
Write-Host "  '$($s.title)' — $($s.segments.Count) segments, $($s.latency_ms)ms, `$$($s.usage.estimated_cost_usd)"

Write-Host "`n[3/5] TTS (real Azure Speech)..." -ForegroundColor Cyan
$t = Invoke-RestMethod -Method Post -Uri "$base/tts/synthesize" -ContentType "application/json" `
  -Body (@{text=$s.segments[0].text} | ConvertTo-Json)
Write-Host "  $($t.audio_duration_sec)s of speech, $($t.latency_ms)ms, $($t.provider_used)"

Write-Host "`n[4/5] Engine + metrics + DLQ endpoints..." -ForegroundColor Cyan
$h = Invoke-RestMethod "$base/avatar/health"
Write-Host "  sadtalker: $($h.status), checkpoints: $($h.checkpoints_present)"
$m = Invoke-RestMethod "$base/metrics/summary"
Write-Host "  lifetime LLM spend: `$$($m.total_cost_usd)  fallback rate: $($m.llm_fallback_rate)"
$d = Invoke-RestMethod "$base/jobs-dlq"
Write-Host "  DLQ entries: $($d.entries.Count)"

Write-Host "`n[5/5] Release checklist:" -ForegroundColor Cyan
Write-Host "  [ ] git status clean on main"
Write-Host "  [ ] git tag -a v1.0.0 -m 'avatarforge v1.0.0'"
Write-Host "  [ ] git push origin v1.0.0"
Write-Host "  [ ] gh release create v1.0.0 --title 'avatarforge v1.0.0' --notes-file docs/RELEASE_NOTES.md"
