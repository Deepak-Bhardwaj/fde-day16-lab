#!/usr/bin/env bash
# Shared variables for all deploy scripts.  source ./00_env.sh
# Per-learner values come from a .env file at the repo root (git-ignored) or the
# environment; the assignments below are only fallback defaults. See .env.example.

# Load .env from the repo root if present — values there override the defaults below.
_ENV_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "$_ENV_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$_ENV_DIR/.env"
  set +a
fi

# Existing resource group under the learner account — do NOT create it.
# Set RG in .env (or: export RG=<your-assigned-rg>).  List: az group list -o table
export RG="${RG:-rg-lab10-agent}"
export LOCATION="${LOCATION:-eastus}"
export ACR="${ACR:-acrlab10vrl}"                       # -> ${ACR}.azurecr.io (globally unique, lowercase)
export ACA_ENV="${ACA_ENV:-cae-lab10}"                 # Container Apps environment
export APP="${APP:-bank-triage-agent}"                 # the Container App name
export IMAGE_REPO="${IMAGE_REPO:-bank-triage-agent}"   # repo inside ACR
export APP_INSIGHTS="${APP_INSIGHTS:-appi-lab10}"      # reuse an existing one if you have it

# Image tag is usually the git sha in CI; default to 'local' for manual runs.
export TAG="${TAG:-local}"
export IMAGE="${ACR}.azurecr.io/${IMAGE_REPO}:${TAG}"

echo "Env loaded: RG=$RG APP=$APP IMAGE=$IMAGE"
