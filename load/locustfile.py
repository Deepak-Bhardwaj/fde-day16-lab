"""
Locust load test for the bank triage agent (Lab 10).

GOAL: drive enough concurrent load on POST /decide to trip the Container Apps
HTTP-concurrency autoscaling rule (deploy/containerapp.yaml: 50 concurrent
requests per replica, min 1 / max 10) so students can watch replicas scale
OUT under load and back IN when it stops.

Works against the local app (offline-first smoke) or the deployed Container App
(where autoscaling is real). See §5.3 of Lab10_Azure_Setup_Steps.docx / the
README for full instructions. Quick start:

  pip install -r requirements-dev.txt

  # web UI (pick users/spawn-rate in the browser at http://localhost:8089)
  locust -f load/locustfile.py --host http://localhost:8000

  # headless ramp against the DEPLOYED app -> triggers autoscaling
  locust -f load/locustfile.py --host "https://<app-fqdn>" \
    --headless -u 300 -r 30 -t 5m
"""
import random

from locust import HttpUser, task, between

# A realistic spread of transactions so the policy exercises every branch
# (approve / block / review) instead of a single trivial path. Amounts and
# flags are chosen against policy_v1: block_over_gbp=10000, review high-risk
# and sanctioned countries (XX/ZZ).
TXNS = [
    {"amount_gbp": 42.50,    "country": "GB", "customer_risk": "low",  "hitl_approved": False},  # approve
    {"amount_gbp": 950.00,   "country": "GB", "customer_risk": "low",  "hitl_approved": False},  # approve
    {"amount_gbp": 8500.00,  "country": "GB", "customer_risk": "low",  "hitl_approved": False},  # approve
    {"amount_gbp": 25000.00, "country": "GB", "customer_risk": "low",  "hitl_approved": False},  # block (over threshold)
    {"amount_gbp": 25000.00, "country": "GB", "customer_risk": "low",  "hitl_approved": True},   # approve (HITL override)
    {"amount_gbp": 300.00,   "country": "GB", "customer_risk": "high", "hitl_approved": False},  # review (risk)
    {"amount_gbp": 500.00,   "country": "XX", "customer_risk": "low",  "hitl_approved": False},  # review (sanctioned)
]


class TriageUser(HttpUser):
    # Short think time so a few hundred simulated users produce real
    # concurrency (which is what the scale rule measures).
    wait_time = between(0.1, 0.5)

    @task(20)
    def decide(self):
        """The main load: score a transaction. ~95% of requests."""
        payload = random.choice(TXNS)
        with self.client.post("/decide", json=payload, catch_response=True) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}")
            elif '"decision"' not in resp.text:
                resp.failure("no decision in response")

    @task(1)
    def health(self):
        """A light liveness check, mimicking probe/monitoring traffic."""
        self.client.get("/health")
