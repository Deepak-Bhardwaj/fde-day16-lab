# Model Card — bank-transaction-triage-agent

- **App version:** 1.4.0  
- **Git SHA:** testsha  
- **Generated:** 2026-07-10T09:25:14.476267Z  
- **Policy version:** v1

## Intended use
Triage bank transactions into approve / review / block.

## Policy
- Block over: £10000
- Review risk levels: ['high']
- Sanctioned countries: ['XX', 'ZZ']

## Evaluation
- Golden set: 12/12 (100%)

## Limitations
- Deterministic policy demo — not a substitute for full AML screening.
- Thresholds are illustrative; calibrate to real risk appetite.

## Rollback
Shift Container Apps traffic to the previous known-good revision (see runbook).