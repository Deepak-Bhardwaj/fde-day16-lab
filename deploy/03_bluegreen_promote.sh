#!/usr/bin/env bash
# LAB 10-C — blue/green promote with an EVAL GATE.
# 1) Deploy the new image as a GREEN revision at 0% traffic (users stay on BLUE).
# 2) Smoke-test + run the eval gate against GREEN's own URL, in isolation.
# 3) Only if the gate PASSES, shift 100% traffic BLUE -> GREEN.
# If the gate fails, the script exits non-zero and traffic never moves.
set -euo pipefail
cd "$(dirname "$0")/.."
source deploy/00_env.sh

active_by_age() {  # $1 = index (0 = newest active revision)
  az containerapp revision list --name "$APP" --resource-group "$RG" \
    --query "reverse(sort_by([?properties.active],&properties.createdTime))[$1].name" -o tsv
}

# BLUE = the revision currently serving, captured BEFORE we create green.
BLUE=$(active_by_age 0)
if [ -z "$BLUE" ]; then
  echo "ERROR: no active revision found for $APP in $RG. Run deploy/02 first." >&2
  exit 2
fi
echo "BLUE (current): $BLUE"

# GREEN revision name: git sha for traceability + a per-run stamp so that
# re-deploying the SAME sha still produces a DISTINCT revision to test.
# Without the stamp, green == blue and the whole promote is a silent no-op.
SUFFIX="v-${TAG}-$(date +%H%M%S)"
GREEN="${APP}--${SUFFIX}"
if [ "$GREEN" == "$BLUE" ]; then
  echo "ERROR: computed GREEN ($GREEN) equals BLUE — refusing a no-op promote." >&2
  exit 3
fi

# Pin routing to BLUE by NAME *before* green exists. This converts the app off
# any 'latestRevision' routing, so the new green revision cannot auto-capture
# traffic the moment it is created — it starts life at an implicit 0%.
az containerapp ingress traffic set --name "$APP" --resource-group "$RG" \
  --revision-weight "${BLUE}=100" -o none

# Env vars for the new revision. AGENT_POLICY can be overridden (the SEV-1 drill
# deploys the BAD policy this way); unset leaves the image's baked-in default.
ENV_VARS="APP_VERSION=$TAG GIT_SHA=$TAG"
if [ -n "${AGENT_POLICY:-}" ]; then
  ENV_VARS="$ENV_VARS AGENT_POLICY=$AGENT_POLICY"
  echo "AGENT_POLICY override for this revision: $AGENT_POLICY"
fi

# Create GREEN revision from the new image.
echo "Deploying GREEN revision $GREEN at 0% traffic..."
az containerapp update --name "$APP" --resource-group "$RG" \
  --image "$IMAGE" --revision-suffix "$SUFFIX" \
  --set-env-vars $ENV_VARS -o none

# Belt-and-suspenders: assert the split explicitly by name (BLUE 100 / GREEN 0).
az containerapp ingress traffic set --name "$APP" --resource-group "$RG" \
  --revision-weight "${BLUE}=100" "${GREEN}=0" -o table

# GREEN's direct URL (revision-scoped FQDN) so we can test it in isolation.
GREEN_FQDN=$(az containerapp revision show --name "$APP" --resource-group "$RG" \
  --revision "$GREEN" --query properties.fqdn -o tsv)
echo "GREEN URL: https://${GREEN_FQDN}"

# Wait for GREEN to come up (it is a brand-new revision that must boot + pass
# its readiness probe before it will answer). Poll /health up to ~60s.
echo "Waiting for GREEN to become ready..."
for i in $(seq 1 20); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "https://${GREEN_FQDN}/health" || true)
  if [ "$code" == "200" ]; then echo "  GREEN healthy after ${i} tries"; break; fi
  if [ "$i" == "20" ]; then
    echo "ERROR: GREEN did not become healthy in time (last code=$code). Traffic NOT shifted." >&2
    exit 4
  fi
  sleep 3
done

if [ "${SKIP_EVAL_GATE:-}" = "1" ] || [ "${SKIP_EVAL_GATE:-}" = "true" ]; then
  echo "############################################################"
  echo "# WARNING: SKIP_EVAL_GATE set — promoting WITHOUT validation."
  echo "# This is the SEV-1 DRILL path (a bad change reaching prod)."
  echo "# NEVER set SKIP_EVAL_GATE in a real deploy."
  echo "############################################################"
else
  echo "== Smoke test GREEN =="
  python scripts/smoke_test.py --url "https://${GREEN_FQDN}"

  echo "== EVAL GATE against GREEN =="
  python eval/eval_gate.py --url "https://${GREEN_FQDN}"   # exits non-zero -> set -e stops here
  echo "Gate PASSED — shifting 100% traffic to GREEN."
fi

az containerapp ingress traffic set --name "$APP" --resource-group "$RG" \
  --revision-weight "${GREEN}=100" "${BLUE}=0" -o table

echo "Promoted $GREEN to production. Previous revision $BLUE kept at 0% for instant rollback."
