"""
model_card.py  (LLMOps — model card automation)
-----------------------------------------------
Generates a model card as JSON (and Markdown) from the current version info,
the active policy/prompt, and the latest eval results. CI runs this on every
release so each deployed image ships with an accurate, auto-generated card —
no hand-written docs that drift.

Usage:
    python scripts/model_card.py --app-version 1.4.0 --git-sha a1b2c3d \\
        --policy app/policies/policy_v1.json --eval-passed 12 --eval-total 12
Writes: app/model_card.json  and  app/model_card.md
"""
import argparse, json, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--app-version", default="0.0.0")
    ap.add_argument("--git-sha", default="unknown")
    ap.add_argument("--policy", default="app/policies/policy_v1.json")
    ap.add_argument("--eval-passed", type=int, default=0)
    ap.add_argument("--eval-total", type=int, default=0)
    args = ap.parse_args()

    policy = json.loads((ROOT / args.policy).read_text())
    rate = (args.eval_passed / args.eval_total) if args.eval_total else 0.0

    card = {
        "model_name": "bank-transaction-triage-agent",
        "app_version": args.app_version,
        "git_sha": args.git_sha,
        "generated_utc": datetime.datetime.utcnow().isoformat() + "Z",
        "intended_use": "Triage bank transactions into approve / review / block.",
        "policy": {
            "version": policy.get("version"),
            "block_over_gbp": policy.get("block_over_gbp"),
            "review_risk_levels": policy.get("review_risk_levels"),
            "sanctioned_countries": policy.get("sanctioned_countries"),
            "description": policy.get("description"),
        },
        "evaluation": {
            "golden_set_passed": args.eval_passed,
            "golden_set_total": args.eval_total,
            "pass_rate": round(rate, 4),
        },
        "limitations": [
            "Deterministic policy demo — not a substitute for full AML screening.",
            "Thresholds are illustrative; calibrate to real risk appetite.",
        ],
        "owner": "Payments Platform Team",
        "rollback": "Shift Container Apps traffic to the previous known-good revision (see runbook).",
    }

    (ROOT / "app" / "model_card.json").write_text(json.dumps(card, indent=2))

    md = [
        f"# Model Card — {card['model_name']}",
        "",
        f"- **App version:** {card['app_version']}  ",
        f"- **Git SHA:** {card['git_sha']}  ",
        f"- **Generated:** {card['generated_utc']}  ",
        f"- **Policy version:** {card['policy']['version']}",
        "",
        "## Intended use",
        card["intended_use"],
        "",
        "## Policy",
        f"- Block over: £{card['policy']['block_over_gbp']}",
        f"- Review risk levels: {card['policy']['review_risk_levels']}",
        f"- Sanctioned countries: {card['policy']['sanctioned_countries']}",
        "",
        "## Evaluation",
        f"- Golden set: {card['evaluation']['golden_set_passed']}/{card['evaluation']['golden_set_total']} "
        f"({card['evaluation']['pass_rate']:.0%})",
        "",
        "## Limitations",
        *[f"- {x}" for x in card["limitations"]],
        "",
        "## Rollback",
        card["rollback"],
    ]
    (ROOT / "app" / "model_card.md").write_text("\n".join(md))
    print(f"Wrote app/model_card.json and app/model_card.md "
          f"(policy {card['policy']['version']}, eval {args.eval_passed}/{args.eval_total})")


if __name__ == "__main__":
    main()
