"""
agent.py
--------
The bank transaction-triage agent's DECISION logic. It is deliberately
deterministic (driven by a versioned policy file, not a live LLM) so the eval
gate can score it reproducibly in CI. In production the same shape would wrap
the real multi-agent capstone; here the policy file plays the role of the
"prompt" that LLMOps versions and that a bad change can regress.

decide(txn, policy) -> {decision, reason, policy_version}
  decision is one of: approve | review | block
"""
from typing import Dict


def decide(txn: Dict, policy: Dict) -> Dict:
    amount = float(txn.get("amount_gbp", 0))
    country = str(txn.get("country", "")).upper()
    risk = str(txn.get("customer_risk", "low")).lower()
    hitl_approved = bool(txn.get("hitl_approved", False))

    block_over = float(policy.get("block_over_gbp", 10000))
    review_levels = [r.lower() for r in policy.get("review_risk_levels", ["high"])]
    sanctioned = [c.upper() for c in policy.get("sanctioned_countries", [])]

    # Rule 1: high-value transactions must be blocked unless a human approved them.
    if amount > block_over and not hitl_approved:
        return {"decision": "block",
                "reason": f"Amount £{amount:.0f} exceeds block threshold £{block_over:.0f} without HITL.",
                "policy_version": policy.get("version")}

    # Rule 2: sanctioned country -> human review.
    if country in sanctioned:
        return {"decision": "review",
                "reason": f"Country {country} is on the sanctioned list.",
                "policy_version": policy.get("version")}

    # Rule 3: high-risk customer -> human review.
    if risk in review_levels:
        return {"decision": "review",
                "reason": f"Customer risk '{risk}' requires review.",
                "policy_version": policy.get("version")}

    # Otherwise approve.
    return {"decision": "approve", "reason": "Within policy limits.",
            "policy_version": policy.get("version")}
