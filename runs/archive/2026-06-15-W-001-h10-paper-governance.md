# Run ID

2026-06-15-W-001-h10-paper-governance

## Plan Path

`/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260615-h10-paper-governance-150154/plans/active/plan-20260615-h10-paper-governance.md`

## Hop ID

W-001

## Work Item ID

W-001

## Goal

Add the H10 paper-governance artifact contract, builder, validator, CLI entrypoints, and repeatable generation/verification scripts, while preserving prior no-promotion/risk-flag disposition and requiring parameter-significance evidence.

## Non-Goals

- Do not update the V2 paper-tracking read model in this hop; that is W-002.
- Do not generate real runtime evidence in this hop; that is W-003.
- Do not publish runtime or verify served routes in this hop; that is W-004.
- Do not create or backfill true-forward paper ledger rows.
- Do not promote fixed90 or introduce delayed-buy semantics.

## Plan Evidence

W-001 deliverable: `src/ashare_evidence/shortpick_v2_h10_paper_governance.py`, schema, CLI parser/main handlers, `scripts/run-shortpick-v2-h10-paper-governance.sh`, `scripts/verify-shortpick-v2-h10-paper-governance-runtime.sh`, focused tests.

Acceptance: `bash -n scripts/run-shortpick-v2-h10-paper-governance.sh && bash -n scripts/verify-shortpick-v2-h10-paper-governance-runtime.sh && PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_h10_paper_governance.py tests/test_shortpick_v2_h10_artifact_validation.py`.

## Source Coverage Evidence

- SRC-001: this run uses reviewed plan/run loop state and external run-plan review.
- SRC-002: artifact contract must identify fixed85 primary and fixed80 capital shadow, record the prior durable no-promotion decision, and give only a future true-forward observation disposition.
- SRC-003: artifact contract and scripts must preserve future-only paper ledger policy.
- SRC-004: artifact contract must preserve no delayed-buy action policy.
- SRC-005: validator must check market excess and annualized return floor for future-observation candidates, and must fail if source robustness `not_ready_for_paper_tracking` or high-risk flags are omitted instead of explicitly disposed.
- SRC-006: validator must mark fixed90 diagnostic-only and block it from paper-ledger promotion.
- SRC-008: artifact must keep `research_observation`, avoid investment/production claims, and reject any historical paper-performance or historical-row backfill claim.
- SRC-009: this run gets MiMo and Codex escalation review because schema contracts and governance state are touched.

## Production Path Fidelity Evidence

- PF-001 is directly covered by the CLI and W-003 runner script added in this hop; the runner must regenerate/consume rank-ablation, parameter-significance, robustness, and execution artifacts before writing governance output.
- PF-002/PF-003 are prepared by schema/test helpers in this hop, but read-model behavior is W-002.
- PF-004 is prepared by the runtime verification script in this hop, but executed after commit in W-004.

## Files Expected To Change

- `src/ashare_evidence/shortpick_v2_h10_paper_governance.py`
- `src/ashare_evidence/cli.py`
- `docs/contracts/registry/schemas/shortpick_v2_h10_paper_governance_artifact.schema.json`
- `scripts/run-shortpick-v2-h10-paper-governance.sh`
- `scripts/verify-shortpick-v2-h10-paper-governance-runtime.sh`
- `tests/test_shortpick_v2_h10_paper_governance.py`
- `tests/test_shortpick_v2_h10_artifact_validation.py`
- `plans/active/plan-20260615-h10-paper-governance.md`
- `runs/active/2026-06-15-W-001-h10-paper-governance.md`

## Implementation Steps

1. Add a schema-backed governance artifact builder and validator that consumes H10 rank-ablation, parameter-significance, robustness, and execution artifacts.
2. Register `shortpick-v2-h10-paper-governance` and `shortpick-v2-h10-paper-governance-validate` CLI commands.
3. Add tests for pass/fail governance gates: fixed85/fixed80 eligibility, fixed90 diagnostic-only, no backfill, no delayed buy, market excess, annualized-return floor, missing parameter-significance input, omitted `not_ready_for_paper_tracking` disposition, omitted high-risk flag disposition, and historical paper-performance claims.
4. Add generation and runtime-verification scripts required by W-003/W-004 acceptance.
5. Run script syntax gates and the W-001 focused pytest gate.

## Acceptance Criteria

The W-001 script syntax and focused pytest commands exit 0 and prove the governance artifact/CLI/validator/script contracts.

## Acceptance Type

test_pass

## Acceptance Spec

`cmd:bash -n scripts/run-shortpick-v2-h10-paper-governance.sh && bash -n scripts/verify-shortpick-v2-h10-paper-governance-runtime.sh && PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_h10_paper_governance.py tests/test_shortpick_v2_h10_artifact_validation.py`

## Planned Evidence

- MiMo run-plan review: passed after W-001 plan/run tightening.
- Codex escalation run-plan review: initial review failed; re-review passed after accepted fixes for no-promotion/risk-flag disposition, parameter-significance coverage, and script syntax gates.
- Focused pytest output: passed.
- Ruff output for touched Python files: passed.
- MiMo code review: passed.
- Codex escalation code review: initial major findings accepted and fixed; re-review passed.

## Actual Evidence

- Implemented `src/ashare_evidence/shortpick_v2_h10_paper_governance.py` with a schema-backed artifact builder/validator that consumes rank-ablation, parameter-significance, robustness, and execution-decomposition artifacts.
- Added `docs/contracts/registry/schemas/shortpick_v2_h10_paper_governance_artifact.schema.json`.
- Registered CLI commands `shortpick-v2-h10-paper-governance` and `shortpick-v2-h10-paper-governance-validate` in `src/ashare_evidence/cli.py`.
- Added `scripts/run-shortpick-v2-h10-paper-governance.sh` and `scripts/verify-shortpick-v2-h10-paper-governance-runtime.sh`; both pass `bash -n`.
- Added focused tests in `tests/test_shortpick_v2_h10_paper_governance.py`; W-001 gate passed with `20 passed in 0.84s`.
- Added negative coverage for fixed90 inserted into `candidate_configs`, below-floor summary annualized return with stale qualification flags, negative market excess with stale flags, fixed90 diagnostic promotion, missing parameter-significance source, omitted prior no-promotion/risk disposition, and historical paper-performance claims.
- `python3 -m ruff check src/ashare_evidence/shortpick_v2_h10_paper_governance.py tests/test_shortpick_v2_h10_paper_governance.py src/ashare_evidence/cli.py` passed.

## Risk And Rollback Notes

Risk: artifact semantics can accidentally imply true-forward paper rows. Mitigation: validator and tests must keep historical governance evidence separate from paper ledger evidence, preserve source no-promotion/risk-flag evidence, and require a forward-observation-only disposition.

Rollback: revert W-001 files and plan/run state before W-002 if the artifact contract proves incoherent.

## Gate Plan

- MiMo run-plan review before edits.
- Codex escalation run-plan review before edits.
- Focused pytest after implementation.
- MiMo code review after implementation.
- Codex escalation code review after implementation.

## MiMo Plan-Review Result

Passed. MiMo reported no blocking or major issues after the W-001 revision. It confirmed the plan and run doc now preserve prior no-promotion, `not_ready_for_paper_tracking`, high-risk flags, future true-forward-only semantics, parameter-significance as a required input, and `bash -n` plus focused pytest gates.

## Codex Escalation Plan-Review Result

Initial review failed. Findings accepted:

- Blocking: W-001 could bypass existing `not_ready_for_paper_tracking` and prior no-promotion boundaries if it only checked return gates.
- Material: W-001 missed parameter-significance source coverage.
- Material: W-001 acceptance did not prove generated scripts are syntactically valid.

Re-review passed. Codex escalation answered `PASS` after checking the revised plan/run docs against the three W-001 focus areas.

## Implementation Summary

W-001 added the paper-governance artifact family, JSON schema, Python builder/validator, CLI entrypoints, generation script, runtime verification script, and focused tests. The artifact preserves the prior no-promotion and `not_ready_for_paper_tracking` robustness boundary, carries high-risk flags forward, blocks fixed90 from paper candidates, requires parameter-significance evidence, keeps the ledger future true-forward only, and refuses historical paper-performance claims.

After Codex escalation found two material validation gaps, the artifact validator and schema were tightened so `candidate_configs` must be exactly fixed85 then fixed80, `diagnostic_configs` must contain only fixed90, and annualized/market-excess gates are checked from `summary` and cross-checked against `qualification_checks`.

## MiMo Code-Review Result

Passed. Initial focused/sharded MiMo reviews found no blocking issues in the core module, schema, CLI, tests, or scripts after retrying script review on `mimo-v2.5`. After the Codex blocker fixes, MiMo re-reviewed the governance module/schema/tests and reported PASS: fixed90 and extra candidates are blocked at schema/builder/validator layers; 30% annualized and market-excess gates are checked from summary and cross-validated with qualification flags; tampering tests cover fixed90-as-candidate, below-floor summary with stale flags, and negative market excess with stale flags.

## Codex Escalation Code-Review Result

Initial review failed with two material findings:

- Fixed90 and extra paper-candidate configs were not fully blocked because the semantic validator only checked that fixed85/fixed80 were present, and the schema allowed extra `candidate_configs`.
- Annualized-return and market-excess qualification could be self-certified by leaving `qualification_checks.passed=true` while editing `summary` below the floor.

Both findings were accepted and fixed by requiring the exact fixed85/fixed80 candidate sequence, exact fixed90 diagnostic set, direct summary return-floor validation, and summary/qualification consistency checks. Codex escalation re-review then reported PASS and did not find remaining blocking or material issues.

## Gate Results

- `bash -n scripts/run-shortpick-v2-h10-paper-governance.sh && bash -n scripts/verify-shortpick-v2-h10-paper-governance-runtime.sh && PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_h10_paper_governance.py tests/test_shortpick_v2_h10_artifact_validation.py`: exit 0, `20 passed in 0.84s`.
- `python3 -m ruff check src/ashare_evidence/shortpick_v2_h10_paper_governance.py tests/test_shortpick_v2_h10_paper_governance.py src/ashare_evidence/cli.py`: exit 0, `All checks passed!`.
- MiMo code review: PASS.
- Codex escalation code review: PASS after accepted fixes.

## Plan Update Summary

Plan W-001 status changed from `in_progress` to `done`; evidence now records W-001 gate results, ruff, MiMo PASS, and Codex escalation PASS. W-002 remains pending and is the next eligible hop.

## Plan Archive Result

Not applicable for W-001. The plan remains active because W-002, W-003, and W-004 are still pending.

## Archive And Merge Result

Pending. Full-plan execution continues to W-002 before final branch push, merge, base-branch push, plan archive, and temporary state cleanup.
