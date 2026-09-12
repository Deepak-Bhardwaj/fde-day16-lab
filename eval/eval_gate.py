"""
eval_gate.py  (the deploy gate that BLOCKS bad deploys)
------------------------------------------------------
Runs the golden set against a running agent and decides PASS or FAIL. CI calls
this against the newly deployed GREEN revision BEFORE shifting production traffic
to it. If the score is below the threshold, the script exits non-zero and the
pipeline stops the promotion — so a bad prompt/policy change never reaches users.

Two modes:
  --url https://<green-revision-fqdn>   test a live deployment over HTTP
  (default)                              test the app in-process (no network)

Env:
  EVAL_THRESHOLD   pass rate required to promote (default 0.95)
  AGENT_POLICY     which policy the in-process app loads (to demo a bad one)

Exit code 0 = gate PASS (safe to promote). Non-zero = gate FAIL (block deploy).
"""
import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).parent
GOLDEN = HERE / "golden_set.json"


def _decide_in_process(txn):
    sys.path.insert(0, str((HERE.parent / "app").resolve()))
    from fastapi.testclient import TestClient
    import main  # app/main.py
    client = TestClient(main.app)
    r = client.post("/decide", json=txn)
    return r.json()


def _decide_over_http(base_url, txn):
    import urllib.request
    req = urllib.request.Request(base_url.rstrip("/") + "/decide",
                                 data=json.dumps(txn).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=None, help="base URL of a live deployment; omit for in-process")
    ap.add_argument("--threshold", type=float, default=float(os.getenv("EVAL_THRESHOLD", "0.95")))
    args = ap.parse_args()

    cases = json.loads(GOLDEN.read_text())
    passed, failures = 0, []

    for c in cases:
        got = (_decide_over_http(args.url, c["txn"]) if args.url
               else _decide_in_process(c["txn"]))
        actual = got.get("decision")
        if actual == c["expected"]:
            passed += 1
        else:
            failures.append((c["name"], c["expected"], actual))

    total = len(cases)
    rate = passed / total if total else 0.0
    print(f"EVAL GATE: {passed}/{total} passed  (rate={rate:.2%}, threshold={args.threshold:.0%})")
    for name, exp, act in failures:
        print(f"  FAIL {name}: expected '{exp}' but got '{act}'")

    if rate >= args.threshold:
        print("RESULT: PASS — safe to promote to production.")
        sys.exit(0)
    else:
        print("RESULT: FAIL — blocking the deploy. Do NOT shift traffic.")
        sys.exit(1)


if __name__ == "__main__":
    main()
