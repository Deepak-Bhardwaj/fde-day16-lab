#!/usr/bin/env bash
# LAB 10-A — build the image and push it to Azure Container Registry.
# Uses `az acr build` so the image is built in the cloud (no local Docker needed).
set -euo pipefail
cd "$(dirname "$0")/.."
source deploy/00_env.sh

# Use the existing resource group provisioned under the learner account.
# We do NOT create it — just verify it exists (fail fast with a clear message).
az group show --name "$RG" -o none 2>/dev/null || {
  echo "ERROR: resource group '$RG' not found under the current subscription." >&2
  echo "       Set RG in deploy/00_env.sh to your assigned learner resource group" >&2
  echo "       (list them with:  az group list -o table)." >&2
  exit 1
}

# Create the registry once (idempotent). Basic tier is fine for the lab.
az acr show --name "$ACR" -o none 2>/dev/null || \
  az acr create --name "$ACR" --resource-group "$RG" --sku Basic --admin-enabled true -o none

echo "Building $IMAGE in ACR (cloud build)..."
az acr build --registry "$ACR" --image "${IMAGE_REPO}:${TAG}" --file Dockerfile . -o table

echo "Pushed: $IMAGE"
echo "Tip: also tag a moving 'latest' if you want:  az acr import / az acr build --image ${IMAGE_REPO}:latest"
