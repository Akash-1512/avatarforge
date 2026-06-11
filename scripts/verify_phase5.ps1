# Phase 5 verification — async pipeline end to end with live progress.
# Prereqs: .\make.ps1 dev ; .\make.ps1 migrate ; checkpoints downloaded
# Usage:   .\scripts\verify_phase5.ps1 -PhotoPath .\face.jpg
param([Parameter(Mandatory=$true)][string]$PhotoPath)
$ErrorActionPreference = "Stop"

if (-not (Test-Path $PhotoPath)) { Write-Host "Photo not found: $PhotoPath" -ForegroundColor Red; exit 1 }
$base = "http://localhost:8000/api/v1"

Write-Host "`n[1/4] Submit async job (expect instant 202)..." -ForegroundColor Cyan
$form = @{
    image            = Get-Item $PhotoPath
    topic            = "Three reasons morning walks improve focus"
    tone             = "casual"
    duration_seconds = "20"
    voice            = "professional_female"
}
$sw = [System.Diagnostics.Stopwatch]::StartNew()
$sub = Invoke-RestMethod -Method Post -Uri "$base/videos/generate" -Form $form
$sw.Stop()
Write-Host "  202 in $($sw.ElapsedMilliseconds)ms  job_id: $($sub.job_id)"
Write-Host "  (Compare: Phase 4 blocked this same request for ~15 minutes)" -ForegroundColor DarkGray

Write-Host "`n[2/4] Watch live progress (polling status; SSE also available at $($sub.events_url))..." -ForegroundColor Cyan
$last = ""
do {
    Start-Sleep 3
    $job = Invoke-RestMethod "$base/jobs/$($sub.job_id)"
    $snap = "$($job.status)/$($job.current_stage)"
    if ($snap -ne $last) { Write-Host "  $(Get-Date -Format HH:mm:ss)  status=$($job.status)  stage=$($job.current_stage)"; $last = $snap }
} while ($job.status -notin @("completed", "failed"))

if ($job.status -eq "failed") {
    Write-Host "  FAILED at stage '$($job.current_stage)': $($job.error_message)" -ForegroundColor Red
    Write-Host "`n  Dead-letter queue:" -ForegroundColor Yellow
    (Invoke-RestMethod "$base/jobs-dlq").entries | Select-Object -First 3 | Format-List
    exit 1
}

Write-Host "`n[3/4] Job completed — timings:" -ForegroundColor Cyan
$job.stage_timings_ms.PSObject.Properties | ForEach-Object { Write-Host ("  {0,-8} {1,8} ms" -f $_.Name, $_.Value) }
Write-Host "  title: $($job.script_title)"

Write-Host "`n[4/4] Download + play video..." -ForegroundColor Cyan
$out = "$PWD\phase5_async_video.mp4"
Invoke-WebRequest "http://localhost:8000$($job.video_url)" -OutFile $out
Write-Host "  Saved: $out"
Start-Process $out

Write-Host "`nFlower task view: http://localhost:5555  |  Job rows:" -ForegroundColor Cyan
docker compose exec -T postgres psql -U avatarforge -d avatarforge -c "SELECT id, status, current_stage, script_title FROM video_jobs ORDER BY created_at DESC LIMIT 3;"
