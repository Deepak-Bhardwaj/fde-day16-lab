"""
smoke_test.py  (post-deploy sanity check)
-----------------------------------------
A tiny health/behaviour check CI runs against a deployed revision URL right after
deploy, before the eval gate. Confirms the service is up, ready, and answers a
known transaction correctly.

    python scripts/smoke_test.py --url https://<revision-fqdn>
    python scripts/smoke_test.py            # in-process (offline)
Exit 0 = healthy, non-zero = fail.
"""
import argparse, json, sys
from pathlib import Path


def _client(url):
    if url:
        import urllib.request
        def call(method, path, body=None):
            data = json.dumps(body).encode() if body is not None else None
            req = urllib.request.Request(url.rstrip("/") + path, data=data,
                                         headers={"Content-Type": "application/json"},
                                         method=method)
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status, json.loads(r.read())
        return call
    sys.path.insert(0, str((Path(__file__).resolve().parent.parent / "app")))
    from fastapi.testclient import TestClient
    import main
    tc = TestClient(main.app)
    def call(method, path, body=None):
        r = tc.request(method, path, json=body)
        return r.status_code, r.json()
    return call


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=None)
    args = ap.parse_args()
    call = _client(args.url)

    checks = []
    s, b = call("GET", "/health"); checks.append(("health 200", s == 200))
    s, b = call("GET", "/ready");  checks.append(("ready 200", s == 200))
    s, b = call("POST", "/decide", {"amount_gbp": 25000, "country": "GB", "customer_risk": "low"})
    checks.append(("25k blocks", b.get("decision") == "block"))
    s, b = call("GET", "/version"); checks.append(("version has policy", "policy_version" in b))

    ok = all(p for _, p in checks)
    for name, passed in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    print("SMOKE:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
