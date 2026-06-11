# Phase 3 verification — run after: .\make.ps1 dev
$base = "http://localhost:8000/api/v1"

Write-Host "`n[1/5] Voice presets..." -ForegroundColor Cyan
(Invoke-RestMethod "$base/tts/voices").PSObject.Properties | ForEach-Object { Write-Host "  $($_.Name): $($_.Value.description)" }

Write-Host "`n[2/5] Synthesize real speech (Azure Speech F0 — free)..." -ForegroundColor Cyan
$body = @{
    text = "Hello! This is avatarforge speaking. If you can hear me clearly, phase three is working perfectly."
    voice = "professional_female"
    speaking_rate = 1.0
} | ConvertTo-Json
try {
    $r = Invoke-RestMethod -Method Post -Uri "$base/tts/synthesize" -ContentType "application/json" -Body $body
    Write-Host "  Provider: $($r.provider_used)  Voice: $($r.model)"
    Write-Host "  Duration: $($r.audio_duration_sec)s  Latency: $($r.latency_ms)ms  Cost: `$$($r.estimated_cost_usd)"
    Write-Host "  Format:   $($r.format)"

    Write-Host "`n[3/5] Download + open the audio..." -ForegroundColor Cyan
    $out = "$PWD\phase3_voice_test.wav"
    Invoke-WebRequest "http://localhost:8000$($r.audio_url)" -OutFile $out
    Write-Host "  Saved: $out"
    Start-Process $out   # opens in default player — LISTEN to it
} catch {
    Write-Host "  FAILED: $($_.ErrorDetails.Message)" -ForegroundColor Red
    Write-Host "  Check AZURE_SPEECH_KEY / AZURE_SPEECH_REGION in .env" -ForegroundColor Yellow
}

Write-Host "`n[4/5] Validation guards (expect 422 x2)..." -ForegroundColor Cyan
foreach ($bad in '{"text":""}', '{"text":"hi","voice":"robot"}') {
    try { Invoke-RestMethod -Method Post -Uri "$base/tts/synthesize" -ContentType "application/json" -Body $bad }
    catch { Write-Host "  Got $($_.Exception.Response.StatusCode.value__) as expected" }
}

Write-Host "`n[5/5] TTS usage audit rows..." -ForegroundColor Cyan
docker compose exec -T postgres psql -U avatarforge -d avatarforge -c "SELECT provider, voice_preset, characters, audio_duration_sec, latency_ms, success FROM tts_usage ORDER BY id DESC LIMIT 5;"

Write-Host "`nffprobe check (optional): ffprobe -i phase3_voice_test.wav  -> expect 16000 Hz, 1 channels, s16" -ForegroundColor Yellow
