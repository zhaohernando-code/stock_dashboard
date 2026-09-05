# Daily Strategy Foundation Audit

This is a measurement audit and one preregistered offline challenger experiment under guide `2026-09-05.1`.

## Confirmed engineering defects

- Learning candidates previously consumed training labels whose outcomes occurred after the first test date. Split metadata claimed a 20-day purge/embargo without enforcing one. Both memory and streaming fits now require the entire target cohort to be available before the test session, including stock/benchmark outcomes and the shared multi-horizon readiness gate. Minimum training dates are checked after exclusion.
- Missing 5/20-day targets previously fell back to a 10-day target. Only the actual requested horizon is now usable.
- Learning outputs disclose remaining label-readiness conditioning. These metrics are not unconditional account performance; legacy learning reports require revalidation.
- V3 user-facing labels now describe profitability as unproven. This changes no active stock selection or paper-account order policy.

## Baseline and measurement evidence

- Frozen snapshot SHA256: `9e64e35b4263f6eec34ff6b93f84f5d60d29291e3ebadea97839740f57cad0ef`.
- Original and Rank4-only replay reproduced exactly; Rank4 final NAV `867357.1805000004`. These are reused historical price-account diagnostics, not forward profit evidence.
- `price_lineage_audit.json`: 1,420,535 archival overlaps; only three prices differ by more than half a cent. No systemic price-adjustment scaling was found.
- The frozen replay has one known personal price-limit exception: 605499.SH, signal 2024-12-05, raw close 221 CNY. Exact replay preserves this historical defect for comparison; it does not certify full eligibility.
- Independent daily execution-audit kernel reserves shares and cash at the preceding decision and exactly reproduces the frozen challenger ledger, NAV and lot P&L after strategy selection was moved out of production source.
- Corporate-action cash/share accounting, full historical PIT eligibility, actual queue fills and truly unseen outcomes are not fully certified. Their absence cannot be converted into a claim that they caused the current loss.

## Research disposition

The rejected challenger's one durable conclusion is in `STRATEGY_RESEARCH_LEDGER.md`. Its pre-registration, raw bar extract, daily ledgers, cost scenarios and portable report are user-delivered local evidence, not production strategies. No failed weekly selection implementation or parameter grid is retained here.

The general-purpose audit kernel takes externally frozen decisions. It does not choose stocks, ranks, weekly dates or candidate parameters, and is not an automatic trading executor.

## Reproducible checks

```bash
python3 -m pytest -q tests/test_training_label_maturity.py tests/test_daily_order_replay.py tests/test_model_candidate_workbench.py tests/test_model_exploration_snapshot.py
PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage
```

The future-label counterexamples failed before the repair, then passed for both learning families and both runner paths. Baseline source inputs were read only. The attempted authenticated dividend fetch was rejected by automatic approval before execution; no credentials were sent by that attempt.
