# Deploy avatarforge to a local kind cluster (AKS-shaped manifests).
# Prereqs: kind cluster running, kubectl in PATH, images built (.\make.ps1 build)
# Usage:   .\scripts\deploy-kind.ps1 [-ClusterName kind]
param([string]$ClusterName = "kind")
$ErrorActionPreference = "Stop"

Write-Host "`n[1/5] Loading local images into kind (sadtalker is ~8GB — first load takes minutes)..." -ForegroundColor Cyan
kind load docker-image avatarforge-api:latest --name $ClusterName
kind load docker-image avatarforge-worker:latest --name $ClusterName
kind load docker-image avatarforge-sadtalker:latest --name $ClusterName

Write-Host "`n[2/5] Applying manifests..." -ForegroundColor Cyan
kubectl apply -k k8s/

Write-Host "`n[3/5] Creating secrets from .env..." -ForegroundColor Cyan
$envVars = @{}
Get-Content .env | Where-Object { $_ -match "^\s*[^#].*=" } | ForEach-Object {
    $k, $v = $_ -split "=", 2; $envVars[$k.Trim()] = $v.Trim()
}
kubectl -n avatarforge delete secret avatarforge-secrets --ignore-not-found
kubectl -n avatarforge create secret generic avatarforge-secrets `
  --from-literal=AZURE_OPENAI_API_KEY=$($envVars["AZURE_OPENAI_API_KEY"]) `
  --from-literal=AZURE_SPEECH_KEY=$($envVars["AZURE_SPEECH_KEY"]) `
  --from-literal=OPENAI_API_KEY=$($envVars["OPENAI_API_KEY"])

Write-Host "`n[4/5] Waiting for rollouts..." -ForegroundColor Cyan
kubectl -n avatarforge rollout status deploy/postgres --timeout=120s
kubectl -n avatarforge rollout status deploy/redis --timeout=60s
kubectl -n avatarforge rollout status deploy/api --timeout=180s
kubectl -n avatarforge rollout status deploy/worker --timeout=180s

Write-Host "`n[5/5] Running migrations..." -ForegroundColor Cyan
kubectl -n avatarforge delete job migrate --ignore-not-found
kubectl apply -f k8s/50-migrate-job.yaml
kubectl -n avatarforge wait --for=condition=complete job/migrate --timeout=120s

Write-Host "`nDeployed. Access the API:" -ForegroundColor Green
Write-Host "  kubectl -n avatarforge port-forward svc/api 8080:8000"
Write-Host "  then: http://127.0.0.1:8080/docs"
kubectl -n avatarforge get pods
