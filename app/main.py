"""
main.py
-------
The containerised agent service (FastAPI). This is what gets Dockerised, pushed
to Azure Container Registry, and deployed to Azure Container Apps.

Endpoints:
  GET  /health     liveness probe   -> 200 while the process is alive
  GET  /ready      readiness probe  -> 200 only when a valid policy is loaded
  POST /decide     the agent decision for one transaction
  GET  /version    app + policy version + git sha (for traceability)
  GET  /modelcard  the auto-generated model card (LLMOps)

Config via environment variables:
  APP_VERSION        e.g. 1.4.0            (set by CI from the release tag)
  GIT_SHA            e.g. a1b2c3d          (set by CI)
  AGENT_POLICY       path to the policy JSON (default policies/policy_v1.json)
                     -> this is the 'prompt version' LLMOps controls
"""
import json
import os
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel, Field

from agent import decide

HERE = Path(__file__).parent
DEFAULT_POLICY = HERE / "policies" / "policy_v1.json"

app = FastAPI(title="Bank Transaction Triage Agent", version=os.getenv("APP_VERSION", "0.0.0"))

# Load the policy once at startup. If it is missing/invalid, /ready reports NOT ready.
_POLICY = None
_POLICY_ERROR = None


def _load_policy():
    global _POLICY, _POLICY_ERROR
    path = Path(os.getenv("AGENT_POLICY", str(DEFAULT_POLICY)))
    try:
        _POLICY = json.loads(path.read_text())
        _POLICY_ERROR = None
    except Exception as e:  # noqa: BLE001
        _POLICY = None
        _POLICY_ERROR = f"{type(e).__name__}: {e}"


_load_policy()


class Txn(BaseModel):
    amount_gbp: float = Field(..., ge=0)
    country: str = "GB"
    customer_risk: str = "low"
    hitl_approved: bool = False


@app.get("/health")
def health():
    """Liveness: is the process up? Always 200 unless the process is dead."""
    return {"status": "alive"}


@app.get("/ready")
def ready():
    """Readiness: only serve traffic when a valid policy is loaded."""
    if _POLICY is None:
        return _json({"status": "not-ready", "error": _POLICY_ERROR}, 503)
    return {"status": "ready", "policy_version": _POLICY.get("version")}


@app.post("/decide")
def decide_endpoint(txn: Txn):
    if _POLICY is None:
        return _json({"error": "policy not loaded", "detail": _POLICY_ERROR}, 503)
    return decide(txn.model_dump(), _POLICY)


@app.get("/version")
def version():
    return {
        "app_version": os.getenv("APP_VERSION", "0.0.0"),
        "git_sha": os.getenv("GIT_SHA", "unknown"),
        "policy_version": (_POLICY or {}).get("version", "none"),
        "policy_path": os.getenv("AGENT_POLICY", str(DEFAULT_POLICY)),
    }


@app.get("/modelcard")
def modelcard():
    mc = HERE / "model_card.json"
    if mc.exists():
        return json.loads(mc.read_text())
    return {"note": "model_card.json not generated yet; run scripts/model_card.py"}


def _json(payload, status):
    from fastapi.responses import JSONResponse
    return JSONResponse(payload, status_code=status)
