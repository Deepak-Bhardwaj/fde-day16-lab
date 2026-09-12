import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "app"))
from agent import decide

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--golden", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--policy", required=True)
    ap.add_argument("--max-regression", type=float, default=0.02)
    args = ap.parse_args()

    policy = json.loads(Path(args.policy).read_text())
    golden_cases = [json.loads(line) for line in Path(args.golden).read_text().splitlines() if line.strip()]
    
    passed = sum(1 for case in golden_cases if decide(case["txn"], policy)["decision"] == case["expected_decision"])
    total = len(golden_cases)
    current_pass_rate = passed / total if total > 0 else 0.0
    
    baseline_pass_rate = json.loads(Path(args.baseline).read_text()).get("pass_rate", 1.0)
    regression = baseline_pass_rate - current_pass_rate
    
    print(f"Eval Results: {passed}/{total} passed ({current_pass_rate:.2%}) | Baseline: {baseline_pass_rate:.2%} | Regression: {regression:.2%}")
    
    if regression > args.max_regression:
        print("❌ EVAL GATE FAILED: Regression exceeds threshold. Blocking deploy.")
        sys.exit(1)
    print("✅ EVAL GATE PASSED: Quality is within acceptable limits.")
    sys.exit(0)

if __name__ == "__main__":
    main()