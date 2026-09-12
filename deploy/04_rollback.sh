#!/usr/bin/env bash
# SEV-1 ROLLBACK — the 02:00 action. Shift 100% traffic back to the last
# known-good revision. Fast, reversible, no rebuild.
#
#   ./deploy/04_rollback.sh                 # roll back to the previous active revision
#   ./deploy/04_rollback.sh <revision-name> # roll back to a specific known-good revision
set -euo pipefail
cd "$(dirname "$0")/.."
source deploy/00_env.sh

active_by_age() {
  az containerapp revision list --name "$APP" --resource-group "$RG" \
    --query "reverse(sort_by([?properties.active],&properties.createdTime))[$1].name" -o tsv
}

CURRENT=$(active_by_age 0)                 # the (bad) revision serving now
TARGET="${1:-$(active_by_age 1)}"          # previous known-good, or an explicit arg

if [ -z "$TARGET" ] || [ "$TARGET" == "$CURRENT" ]; then
  echo "ERROR: could not determine a safe rollback target. Pass one explicitly:"
  echo "  az containerapp revision list --name $APP -g $RG -o table"
  exit 2
fi

echo "Rolling back: 100% traffic  $CURRENT  ->  $TARGET"
az containerapp ingress traffic set --name "$APP" --resource-group "$RG" \
  --revision-weight "${TARGET}=100" "${CURRENT}=0" -o table

# Verify the good policy is now serving.
FQDN=$(az containerapp show --name "$APP" --resource-group "$RG" \
  --query properties.configuration.ingress.fqdn -o tsv)
echo "Verifying https://${FQDN}/version ..."
curl -s "https://${FQDN}/version" || true
echo

# Optional: park the bad revision so it cannot receive traffic again by accident.
echo "Deactivating the bad revision $CURRENT (optional, reversible)."
az containerapp revision deactivate --name "$APP" --resource-group "$RG" --revision "$CURRENT" -o none || true

echo "Rollback complete. Record the timeline in the runbook and open a postmortem."
