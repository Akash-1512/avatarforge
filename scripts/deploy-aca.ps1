# contentforge — deploy the API to Azure Container Apps (public URL).
#
# This deploys the FastAPI app as a single public container app backed by managed
# Azure Postgres + Redis. The synchronous content paths (characters, styles, scene
# preview, director/storyboard, film compose, the quality loop) work immediately —
# they call Azure/fal directly and do not need the Celery worker. The legacy async
# talking-head pipeline (the /videos queue) needs the worker; deploy that separately
# (see the note at the bottom) only if you want it in the cloud demo.
#
# Prereqs (run once):
#   az upgrade
#   az extension add --name containerapp --upgrade
#   az provider register --namespace Microsoft.App
#   az provider register --namespace Microsoft.ContainerRegistry
#   az provider register --namespace Microsoft.OperationalInsights
#
# Review every value below before running. Costs money (managed Postgres/Redis +
# the container app). Scale-to-zero keeps the app cheap when idle.

$ErrorActionPreference = "Stop"

# ── config — edit these ─────────────────────────────────────────────
$RG       = "avatarforge-rg"
$LOCATION = "eastus2"
$ENVNAME  = "contentforge-env"
$APPNAME  = "contentforge-api"
$ACR      = "contentforgeacr$((Get-Random -Maximum 9999))"   # must be globally unique
$PG       = "contentforge-pg-$((Get-Random -Maximum 9999))"
$REDIS    = "contentforge-redis-$((Get-Random -Maximum 9999))"
$PGUSER   = "forge"
$PGPASS   = "$(([System.Guid]::NewGuid()).ToString('N'))Aa1!"  # random strong password

# secrets your app needs — pull from your existing .env (do NOT hardcode here)
$AZURE_OPENAI_ENDPOINT   = $env:AZURE_OPENAI_ENDPOINT
$AZURE_OPENAI_API_KEY    = $env:AZURE_OPENAI_API_KEY
$AZURE_SORA_DEPLOYMENT   = "sora-2"
$AZURE_SPEECH_KEY        = $env:AZURE_SPEECH_KEY
$AZURE_SPEECH_REGION     = "centralindia"
$FAL_API_KEY             = $env:FAL_API_KEY
$ELEVENLABS_API_KEY      = $env:ELEVENLABS_API_KEY

# ── 1. resource group + container apps environment ──────────────────
az group create --name $RG --location $LOCATION | Out-Null

az containerapp env create --name $ENVNAME --resource-group $RG --location $LOCATION | Out-Null

# ── 2. managed Postgres (flexible server) + database ────────────────
az postgres flexible-server create `
  --resource-group $RG --name $PG --location $LOCATION `
  --admin-user $PGUSER --admin-password $PGPASS `
  --tier Burstable --sku-name Standard_B1ms --storage-size 32 `
  --version 16 --yes | Out-Null
az postgres flexible-server db create -g $RG -s $PG -d contentforge | Out-Null
# allow Azure services to reach it
az postgres flexible-server firewall-rule create -g $RG -n $PG `
  --rule-name allow-azure --start-ip-address 0.0.0.0 --end-ip-address 0.0.0.0 | Out-Null
$PGHOST = az postgres flexible-server show -g $RG -n $PG --query fullyQualifiedDomainName -o tsv
$DATABASE_URL = "postgresql+asyncpg://$PGUSER`:$PGPASS@$PGHOST`:5432/contentforge"

# ── 3. managed Redis ────────────────────────────────────────────────
az redis create -g $RG -n $REDIS -l $LOCATION --sku Basic --vm-size c0 | Out-Null
$REDISHOST = az redis show -g $RG -n $REDIS --query hostName -o tsv
$REDISKEY  = az redis list-keys -g $RG -n $REDIS --query primaryKey -o tsv
$REDIS_URL = "rediss://:$REDISKEY@$REDISHOST`:6380/0"

# ── 4. build + push the image to ACR ────────────────────────────────
az acr create -g $RG -n $ACR --sku Basic --admin-enabled true | Out-Null
# build the API image from the backend/ context (where the Dockerfile lives)
az acr build --registry $ACR --image contentforge-api:v2.4.0 ./backend
$ACRSERVER = az acr show -n $ACR --query loginServer -o tsv
$ACRPASS   = az acr credential show -n $ACR --query "passwords[0].value" -o tsv

# ── 5. deploy the container app with secrets + ingress ──────────────
az containerapp create `
  --name $APPNAME --resource-group $RG --environment $ENVNAME `
  --image "$ACRSERVER/contentforge-api:v2.4.0" `
  --registry-server $ACRSERVER --registry-username $ACR --registry-password $ACRPASS `
  --target-port 8000 --ingress external `
  --min-replicas 0 --max-replicas 2 `
  --cpu 1.0 --memory 2.0Gi `
  --secrets `
    "db-url=$DATABASE_URL" "redis-url=$REDIS_URL" `
    "aoai-key=$AZURE_OPENAI_API_KEY" "speech-key=$AZURE_SPEECH_KEY" `
    "fal-key=$FAL_API_KEY" "eleven-key=$ELEVENLABS_API_KEY" `
  --env-vars `
    "ENVIRONMENT=prod" "APP_VERSION=2.4.0" `
    "DATABASE_URL=secretref:db-url" "REDIS_URL=secretref:redis-url" `
    "AZURE_OPENAI_ENDPOINT=$AZURE_OPENAI_ENDPOINT" "AZURE_OPENAI_API_KEY=secretref:aoai-key" `
    "AZURE_SORA_DEPLOYMENT=$AZURE_SORA_DEPLOYMENT" `
    "AZURE_SPEECH_KEY=secretref:speech-key" "AZURE_SPEECH_REGION=$AZURE_SPEECH_REGION" `
    "FAL_API_KEY=secretref:fal-key" "ELEVENLABS_API_KEY=secretref:eleven-key" | Out-Null

$FQDN = az containerapp show -g $RG -n $APPNAME --query properties.configuration.ingress.fqdn -o tsv
Write-Host ""
Write-Host "contentforge is live at: https://$FQDN"
Write-Host "  console:  https://$FQDN/"
Write-Host "  health:   https://$FQDN/api/v1/health"
Write-Host "  engines:  https://$FQDN/api/v1/scene/engines"
Write-Host ""
Write-Host "NOTE: run DB migrations once against the managed Postgres before first use:"
Write-Host "  set DATABASE_URL to the value above and run: alembic upgrade head"
Write-Host "  (or exec into the container app via 'az containerapp exec')"

# ── optional: the Celery worker (only needed for the legacy /videos queue) ──
# az containerapp create --name contentforge-worker -g $RG --environment $ENVNAME `
#   --image "$ACRSERVER/contentforge-api:v2.4.0" `
#   --registry-server $ACRSERVER --registry-username $ACR --registry-password $ACRPASS `
#   --min-replicas 1 --max-replicas 1 --cpu 1.0 --memory 2.0Gi `
#   --command "celery" "-A" "backend.workers.celery_app" "worker" "--loglevel=info" `
#   --secrets (... same as above ...) --env-vars (... same as above ...)
