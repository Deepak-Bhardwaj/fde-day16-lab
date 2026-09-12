#!/usr/bin/env bash
# LAB 10-B — deploy to Azure Container Apps with auto-scaling + health probes.
# First run creates the environment and the app; probes/scale come from the YAML.
set -euo pipefail
cd "$(dirname "$0")/.."
source deploy/00_env.sh

# Container Apps extension + provider (idempotent)
az extension add --name containerapp --upgrade -o none
#az provider register --namespace Microsoft.App -o none
#az provider register --namespace Microsoft.OperationalInsights -o none

# Container Apps environment (once)
az containerapp env show --name "$ACA_ENV" --resource-group "$RG" -o none 2>/dev/null || \
  az containerapp env create --name "$ACA_ENV" --resource-group "$RG" --location "$LOCATION" -o none

# ACR admin creds so the app can pull the image (simple path for the lab;
# in production use a managed identity + AcrPull role instead).
ACR_USER=$(az acr credential show --name "$ACR" --query username -o tsv)
ACR_PASS=$(az acr credential show --name "$ACR" --query 'passwords[0].value' -o tsv)

if ! az containerapp show --name "$APP" --resource-group "$RG" -o none 2>/dev/null; then
  echo "Creating Container App $APP (revision suffix v-$TAG)..."
  az containerapp create \
    --name "$APP" --resource-group "$RG" --environment "$ACA_ENV" \
    --image "$IMAGE" \
    --registry-server "${ACR}.azurecr.io" --registry-username "$ACR_USER" --registry-password "$ACR_PASS" \
    --target-port 8000 --ingress external \
    --revisions-mode multiple \
    --revision-suffix "v-${TAG}" \
    --min-replicas 1 --max-replicas 10 \
    --scale-rule-name http-concurrency --scale-rule-type http --scale-rule-http-concurrency 50 \
    --env-vars APP_VERSION="$TAG" GIT_SHA="$TAG" AGENT_POLICY="policies/policy_v1.json" \
    -o table
fi

# Apply/patch the full template (adds the liveness/readiness/startup probes).
echo "Applying probes + scale from deploy/containerapp.yaml ..."
IMAGE="$IMAGE" TAG="$TAG" envsubst '$IMAGE $TAG' < deploy/containerapp.yaml > /tmp/containerapp.rendered.yaml
sed -i "s#<IMAGE>#${IMAGE}#g; s#<TAG>#${TAG}#g" /tmp/containerapp.rendered.yaml
az containerapp update --name "$APP" --resource-group "$RG" --yaml /tmp/containerapp.rendered.yaml -o table

FQDN=$(az containerapp show --name "$APP" --resource-group "$RG" --query properties.configuration.ingress.fqdn -o tsv)
echo "App URL: https://${FQDN}"
echo "Health : https://${FQDN}/health"
