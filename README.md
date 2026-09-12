# Lab 10 — Container Apps Deploy · CI/CD · LLMOps (Capstone)

Take the agent to production: **containerise** it, push to **Azure Container Registry**,
deploy to **Azure Container Apps** with auto-scaling + health probes, and wire a
**GitHub Actions blue/green pipeline with an eval gate** that blocks bad deploys —
plus a rehearsed **02:00 SEV-1 rollback runbook**.

Scenario: a bank's transaction-triage agent must go live with a rollback runbook and
an eval gate. The app is a small FastAPI service whose decisions come from a
**versioned policy/prompt**; a bad policy change is what the eval gate must catch.

## Files

| Path | Role |
|------|------|
| `app/main.py` | FastAPI service: `/health` `/ready` `/decide` `/version` `/modelcard` |
| `app/agent.py` | The triage decision logic (approve / review / block) |
| `app/policies/policy_v1.json` | Good production policy (the "prompt") |
| `app/policies/policy_v2_bad.json` | Regressed policy — the 02:00 bad change |
| `Dockerfile` / `.dockerignore` | Container image (non-root, healthcheck) |
| `app/requirements.txt` | Container **runtime** deps (kept tiny) |
| `requirements-dev.txt` | Local/offline deps = runtime + `httpx` (needed by the gate/smoke test) |
| `eval/eval_gate.py` + `golden_set.json` | **The gate** that blocks bad deploys |
| `scripts/model_card.py` | LLMOps model-card automation |
| `scripts/smoke_test.py` | Post-deploy sanity check |
| `deploy/00_env.sh` | Shared variables (edit these) |
| `deploy/01_acr_build_push.sh` | **Lab 10-A** build + push to ACR |
| `deploy/02_deploy_containerapp.sh` + `containerapp.yaml` | **Lab 10-B** deploy + probes + autoscale |
| `deploy/03_bluegreen_promote.sh` | **Lab 10-C** blue/green + eval gate |
| `deploy/04_rollback.sh` | **SEV-1** rollback (the 02:00 action) |
| `load/locustfile.py` | **Load test** that drives the autoscaling rule |
| `.github/workflows/deploy.yml` | CI/CD pipeline |
| `.github/workflows/sev1_drill.yml` | Manual SEV-1 drill (deploy-bad / rollback) |

## Try it offline (no Docker, no Azure)

```bash
# create an isolated virtualenv (Python 3.12) and install deps
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt            # app deps + httpx (for the gate/smoke test)

# 1) run the agent locally
uvicorn main:app --app-dir app --port 8000     # then open http://localhost:8000/health

# 2) the eval gate on the GOOD policy -> PASS (exit 0)
python eval/eval_gate.py

# 3) the eval gate on the BAD policy -> FAIL (exit 1) — the deploy would be blocked
AGENT_POLICY=app/policies/policy_v2_bad.json python eval/eval_gate.py

# 4) smoke test + model card
python scripts/smoke_test.py
python scripts/model_card.py --app-version 1.4.0 --git-sha $(git rev-parse --short HEAD) \
  --policy app/policies/policy_v1.json --eval-passed 12 --eval-total 12
```

## Publish to GitHub (needed before CI/CD)

The `.github/workflows/deploy.yml` pipeline runs from your own repo, so publish the lab first.
GitHub rejects pushing files under `.github/workflows/` unless the `gh` token carries the
`workflow` scope — grant it, then push. Replace `<your-github-id>` with your account.

```bash
# 0) the lab folder ships with a git remote pointing at the trainer's repo.
#    remove it first, or step 1 silently keeps the old origin and you end up
#    pushing to someone else's account. verify with `git remote -v` afterwards.
git remote remove origin 2>/dev/null || true

# 1) create the repo on GitHub (public) under your account
gh repo create <your-github-id>/azure-ai-labs-10abc --public --source . --remote origin
#    (or create it in the GitHub UI, then:
#     git init -b main && git remote add origin \
#       https://github.com/<your-github-id>/azure-ai-labs-10abc.git)

# 2) point gh at the account that owns the repo
gh auth switch --user <your-github-id>

# 3) grant the token the 'workflow' scope (needed for .github/workflows/*)
#    interactive: opens a browser / device-code prompt
gh auth refresh -h github.com -u <your-github-id> -s workflow

# 4) commit and push the CI/CD workflow
git add .github/workflows/deploy.yml
git commit -m "ci: add Container Apps blue/green deploy workflow"
git push -u origin main
```

> If the push is rejected with *"refusing to allow an OAuth App to create or update workflow …
> without `workflow` scope"*, step 3 was skipped — run it and push again.

**CI/CD is opt-in for Azure.** On every push the `eval-precheck` job runs the eval gate. The
`build-deploy-promote` job only runs when the repo **variable** `AZURE_ENABLED == 'true'` and the
three OIDC secrets (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`) are set —
otherwise it's skipped and the pipeline stays green. See `Lab10_Azure_Setup_Steps.docx` §6.2 for
exactly where to add the secrets and the `AZURE_ENABLED` variable.

**What to configure on the repo** (Settings ▸ Secrets and variables ▸ Actions):

- **Secrets tab:** `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` (from your app
  registration and `az account show`).
- **Variables tab:** `AZURE_ENABLED=true` to turn the deploy job on, **plus your resource names**
  — CI reads these, not the git-ignored `.env`:
  ```bash
  gh variable set RG         --body "<your-rg>"          # existing learner resource group
  gh variable set ACR        --body "<your-acr>"         # globally-unique registry, lowercase
  gh variable set APP        --body "<your-app>"         # Container App name
  gh variable set IMAGE_REPO --body "<your-image-repo>"  # repo inside ACR
  gh variable set ACA_ENV    --body "<your-aca-env>"     # Container Apps environment
  ```
  If a Variable is unset the workflow falls back to demo defaults (`rg-lab10-agent`, etc.), which
  won't match your resources — so set all five.
- **One-time Azure side:** create the app registration's **federated credential** and grant it
  **Contributor** on your RG. Exact commands are in the troubleshooting steps just below.

### Troubleshooting the CI Azure login (§6.2)

Two failures show up in the Actions tab, in this order:

- **`AADSTS70025: … has no configured federated identity credentials`** — the `lab10-gha`
  app registration (your `AZURE_CLIENT_ID`) has **no federated credential**, so Azure has nothing
  to trust when GitHub presents its OIDC token. Adding the three secrets is not enough — you must
  also create the credential, once:
  ```bash
  APP_OBJ=$(az ad app list --display-name lab10-gha --query '[0].id' -o tsv)
  az ad app federated-credential create --id "$APP_OBJ" --parameters '{
    "name": "gha-main",
    "issuer": "https://token.actions.githubusercontent.com",
    "subject": "repo:<your-github-id>/azure-ai-labs-10abc:ref:refs/heads/main",
    "audiences": ["api://AzureADTokenExchange"]
  }'
  ```
  The `subject` must match **exactly** what GitHub sends: `repo:<owner>/<repo>:ref:refs/heads/<branch>`.
  A `pull_request`- or environment-triggered run needs its own credential with a different subject.
  Allow ~1 minute to propagate before re-running.

- **Login OK, then `(AuthorizationFailed) … over scope …/resourceGroups/…`** — two causes, usually
  together:
  1. **The service principal has no role on your resources.** Grant Contributor on your RG (covers
     ACR push for the lab):
     ```bash
     APPID=$(az ad app list --display-name lab10-gha --query '[0].appId' -o tsv)
     az role assignment create --assignee "$APPID" --role Contributor \
       --scope /subscriptions/<sub-id>/resourceGroups/<your-rg>
     ```
  2. **CI does not read your `.env`** (it's git-ignored) — the workflow's `env:` block pulls
     learner values from repo **Variables** (`${{ vars.RG }}`, etc.), falling back to example
     defaults (`rg-lab10-agent`, `bank-triage-agent`, `cae-lab10`) only if a Variable is unset. If
     your assigned resources differ — the auto-provisioned learner RGs look like `rg-azuser1234_…` —
     set the Variables under **Settings ▸ Secrets and variables ▸ Actions ▸ Variables**, or via CLI:
     ```bash
     gh variable set RG --body "<your-rg>"
     gh variable set ACR --body "<your-acr>"
     gh variable set APP --body "<your-app>"
     gh variable set IMAGE_REPO --body "<your-image-repo>"
     gh variable set ACA_ENV --body "<your-aca-env>"
     ```
     Make sure the Contributor role assignment above is on **that** RG. The RG named in the error is
     the one CI actually used.

  Verify both:
  ```bash
  az ad app federated-credential list --id "$APP_OBJ" -o table
  az role assignment list --assignee "$APPID" --scope /subscriptions/<sub-id>/resourceGroups/<your-rg> -o table
  ```

### Running the SEV-1 rollback drill from CI

The `sev1-rollback-drill` workflow rehearses the 02:00 incident from the Actions tab (or CLI) —
no local shell needed. It's **manual only** (never runs on push) and reuses the same OIDC login and
repo Variables as the deploy pipeline.

```bash
# 1) simulate a bad change reaching prod — deploys the BAD policy, SKIPPING the eval gate
gh workflow run sev1-rollback-drill --ref main -f action=deploy-bad
#    now /version shows policy v2-bad and a £25k transaction is wrongly APPROVED

# 2) roll back to the last good revision (traffic shift, seconds)
gh workflow run sev1-rollback-drill --ref main -f action=rollback
#    optional explicit target:  -f action=rollback -f revision=<revision-name>
```

Or in the UI: **Actions ▸ sev1-rollback-drill ▸ Run workflow ▸ choose `action`**. Watch with
`gh run watch`. **Run `deploy-bad` before `rollback`** — rollback needs a previous good revision to
fall back to; running `deploy-bad` twice without a rollback in between makes the "previous" revision
another bad one (pass `-f revision=` to be safe). This is the same eval-gate-skipping path teaching
that *the gate is the only thing between a bad policy and production*.

## On Azure

**First, set your own values.** Copy the template to `.env` and edit it — do **not** edit
`deploy/00_env.sh`. `.env` is git-ignored, so your resource-group name and other values stay
out of the repo. Set `RG` to the **existing** resource group already created under your learner
account (`az group list -o table`); `00_env.sh` loads `.env` automatically.

```bash
cp .env.example .env
# then edit .env — at minimum set RG (your existing learner RG) and ACR (globally unique, lowercase)
$EDITOR .env
```

```bash
source deploy/00_env.sh                # loads .env, then falls back to defaults for anything unset
TAG=$(git rev-parse --short HEAD)
./deploy/01_acr_build_push.sh          # Lab 10-A
./deploy/02_deploy_containerapp.sh     # Lab 10-B
./deploy/03_bluegreen_promote.sh       # Lab 10-C (eval gate decides)
./deploy/04_rollback.sh                # SEV-1 rollback drill
```

See `Lab10_Azure_Setup_Steps.docx` (setup), `Lab10_Outcomes_Interpretation.docx`
(how to read what happens), and `Lab10_Rollback_Runbook.xlsx` (the 02:00 runbook).

## Load-test the autoscaling (Locust)

[`load/locustfile.py`](load/locustfile.py) drives concurrent traffic at `POST /decide` to trip the
Container Apps HTTP-concurrency scale rule (50 req/replica, min 1 / max 10 — see
[`deploy/containerapp.yaml`](deploy/containerapp.yaml)) so students can **watch replicas scale out
under load and back in when it stops**.

```bash
pip install -r requirements-dev.txt      # installs locust

# A) smoke the scenario against the LOCAL app (offline; no autoscaling to see)
uvicorn main:app --app-dir app --port 8000        # in another terminal
locust -f load/locustfile.py --host http://localhost:8000 \
  --headless -u 50 -r 25 -t 30s

# B) drive the DEPLOYED app to SEE autoscaling
APP_FQDN=$(az containerapp show -n "$APP" -g "$RG" \
  --query properties.configuration.ingress.fqdn -o tsv)
locust -f load/locustfile.py --host "https://$APP_FQDN" --headless -u 300 -r 30 -t 5m
```

Leave off `--headless` to open the **web UI at http://localhost:8089** and set users / spawn-rate
live. While run **B** ramps, watch replicas climb in a second terminal:

```bash
watch -n 5 'az containerapp replica list -n "$APP" -g "$RG" \
  --query "length(@)" -o tsv'          # replica count: 1 -> several -> back to 1
```

Read the Locust stats table for throughput (req/s) and p50/p95/p99 latency; failures should stay
at 0%. Scale-in lags scale-out by a few minutes (Container Apps cool-down) — expected.
