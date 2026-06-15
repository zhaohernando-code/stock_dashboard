# Run ID

2026-06-15-W-002-h10-paper-governance

## Plan Path

`/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260615-h10-paper-governance-150154/plans/active/plan-20260615-h10-paper-governance.md`

## Hop ID

W-002

## Work Item ID

W-002

## Goal

Update the Short Pick Lab V2 paper-tracking contract, schema, and read model so the W-001 H10 paper-governance artifact can expose fixed85/fixed80 as future true-forward observation candidates while the served projection still returns zero records until a real v2 paper ledger exists.

## Non-Goals

- Do not generate real H10 governance artifacts in this hop; that is W-003.
- Do not publish runtime or verify served routes in this hop; that is W-004.
- Do not create, backfill, or synthesize true-forward paper ledger rows.
- Do not promote fixed90 or allow delayed-entry actions.
- Do not add a frontend UI redesign; only type/schema changes are allowed if required for API response fidelity.

## Plan Evidence

W-002 deliverable: paper contract/schema/read-model/test updates with governance state and zero-row missing-ledger projection.

Acceptance: `PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_paper_tracking_contract.py tests/test_shortpick_v2_read_model_api.py`.

## Source Coverage Evidence

- SRC-001: this run continues the reviewed plan-run loop with W-001 archived and W-002 active.
- SRC-002: the read model must preserve fixed85 as primary future-observation candidate and fixed80 as capital shadow, sourced from the W-001 H10 governance artifact.
- SRC-003: missing-ledger projection must stay zero-row true-forward tracking and must not derive paper rows from historical replay.
- SRC-004: paper ledger schema/read-model row contract must still forbid delayed buy and allow only buy primary, buy fallback, or skip.
- SRC-005: W-002 must not recalculate qualification from historical replay; it must consume the already validated W-001 governance state so the market/30% gates remain governed by W-001.
- SRC-006: fixed90 must be rejected in schema, row validation, and governance projection as diagnostic-only.
- SRC-007: no parameter-search UI or broad strategy direction is added.
- SRC-008: API response remains `research_observation`; historical evidence is labeled as governance state, not paper performance.
- SRC-009: MiMo and Codex escalation run-plan/code reviews are required because W-002 touches schema contracts and live-facing API response shape.

## Production Path Fidelity Evidence

- PF-002: update the ledger schema and row validator so future true-forward ledger rows may use only fixed85/fixed80 plus allowed baseline controls, while fixed90 and delayed actions fail closed. Tests use fixture ledgers because no true-forward H10 ledger exists yet.
- PF-003: update the read model and API response schema so a present governance artifact plus missing ledger returns zero records with a visible `paper_governance` state. TestClient must prove response-model filtering does not drop that field.
- PF-004: W-002 prepares live-facing behavior; runtime publish and served verification are deferred to W-004 and remain mandatory before final closeout.

## Files Expected To Change

- `src/ashare_evidence/shortpick_v2_read_model.py`
- `src/ashare_evidence/schemas/shortpick.py`
- `docs/contracts/registry/schemas/shortpick_v2_paper_tracking_ledger.schema.json`
- `docs/contracts/SHORTPICK_LAB_V2_PAPER_TRACKING_CONTRACT_2026-06-12.md`
- `tests/test_shortpick_v2_paper_tracking_contract.py`
- `tests/test_shortpick_v2_read_model_api.py`
- `frontend/src/types/shortpick.ts`
- `plans/active/plan-20260615-h10-paper-governance.md`
- `runs/active/2026-06-15-W-002-h10-paper-governance.md`

## Implementation Steps

1. Add an optional H10 paper-governance artifact resolver to the V2 paper-tracking read model, using a docs/archive candidate path plus an env override.
2. Validate the governance artifact with the W-001 semantic validator before projecting it.
3. When the governance artifact is present and the true-forward ledger is missing, expose `paper_governance`, fixed85/fixed80 `selected_configs`, zero `records`, and a zero-count `summary`; keep evidence basis `true_forward_tracking`.
4. Keep old blocked-selection behavior when no governance artifact exists, so legacy tests and missing-governance runtime fail closed rather than inventing H10 state.
5. Update ledger schema and row validation to allow fixed85/fixed80 future rows, reject fixed90, and preserve the no-delayed-entry action set.
6. Add/adjust tests for H10 governance projection, API response-model retention of `paper_governance`, allowed fixed85/fixed80 ledger rows, fixed90 rejection, delayed-action rejection, and legacy no-governance blocked behavior.
7. Update the contract document to record H10 governance readiness as future-observation only with no historical backfill.

## Acceptance Criteria

The W-002 focused pytest command exits 0 and proves the contract/schema/read-model/API response can expose governed H10 readiness with zero true-forward records while rejecting fixed90, delayed entries, and ungoverned historical row synthesis.

## Acceptance Type

test_pass

## Acceptance Spec

`cmd:PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_paper_tracking_contract.py tests/test_shortpick_v2_read_model_api.py`

## Planned Evidence

- MiMo run-plan review: passed.
- Codex escalation run-plan review: passed.
- Focused pytest output: passed.
- MiMo code review: passed.
- Codex escalation code review: passed.

## Actual Evidence

- Implemented optional H10 paper-governance artifact resolution and validation in the V2 paper-tracking read model.
- Missing-ledger projection now exposes H10 fixed85/fixed80 as future-observation governance metadata with `records=[]`, `summary.record_count=0`, `true_forward_tracking`, and no historical paper-performance claim.
- Existing-ledger read path now validates the ledger artifact with the public JSON Schema before semantic row checks, while preserving fixed90 and delayed-entry fail-closed checks.
- Pydantic and TypeScript response contracts now preserve `paper_governance`.
- Ledger schema now allows fixed85/fixed80 active future rows, excludes fixed90, and requires `row_contract.ledger_policy = future_true_forward_only_no_historical_backfill`.
- Paper contract documents the H10 future-observation-only marker and fixed90 diagnostic-only boundary.
- Focused W-002 gate: `PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_paper_tracking_contract.py tests/test_shortpick_v2_read_model_api.py` => `17 passed in 1.43s`.
- Combined W-001/W-002 gate: `bash -n scripts/run-shortpick-v2-h10-paper-governance.sh && bash -n scripts/verify-shortpick-v2-h10-paper-governance-runtime.sh && PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_h10_paper_governance.py tests/test_shortpick_v2_paper_tracking_contract.py tests/test_shortpick_v2_read_model_api.py` => `28 passed in 1.39s`.
- Related ruff gate: `python3 -m ruff check src/ashare_evidence/shortpick_v2_h10_paper_governance.py src/ashare_evidence/shortpick_v2_read_model.py src/ashare_evidence/schemas/shortpick.py tests/test_shortpick_v2_h10_paper_governance.py tests/test_shortpick_v2_paper_tracking_contract.py tests/test_shortpick_v2_read_model_api.py src/ashare_evidence/cli.py` => passed.

## Risk And Rollback Notes

Risk: adding governance projection could accidentally convert historical replay evidence into paper rows. Mitigation: the missing-ledger path must always return zero records and a true-forward-only row contract; governance state is metadata only.

Risk: API response model could drop `paper_governance` unless the Pydantic schema is updated. Mitigation: TestClient coverage must assert the served JSON includes it.

Risk: allowing H10 config IDs in the ledger schema could accidentally allow fixed90. Mitigation: fixed90 remains diagnostic-only and must have explicit schema/read-model rejection tests.

Rollback: revert W-002 read model/schema/contract/test/type changes and leave W-001 artifact contract intact.

## Gate Plan

- MiMo run-plan review before edits.
- Codex escalation run-plan review before edits.
- Focused pytest after implementation.
- MiMo code review after implementation.
- Codex escalation code review after implementation.

## MiMo Plan-Review Result

Passed. MiMo found no blocking or major issues. It confirmed W-002 preserves no historical paper-row backfill, no delayed buy, no fixed90 promotion, no broad parameter UI, and uses W-001 governance as metadata rather than recalculating qualification or creating paper rows. It also confirmed the planned tests cover ledger schema, read model, TestClient response-model retention of `paper_governance`, fixed90 rejection, delayed-action rejection, zero records, and legacy fail-closed behavior.

## Codex Escalation Plan-Review Result

Passed. Codex escalation found no blocking or material drift. It confirmed W-002 remains aligned with the approved plan, exposes H10 governance state as metadata with zero records when no true-forward ledger exists, and correctly defers real generation, runtime publish, and served verification to W-003/W-004. It also judged the focused pytest acceptance command appropriate for this hop.

## Implementation Summary

Updated `shortpick_v2_read_model` to consume an optional validated H10 paper-governance artifact, project fixed85/fixed80 as future-observation selected configs with zero missing-ledger records, and reject fixed90/delayed-entry ledger inputs. Updated API response schemas/types, ledger JSON Schema, paper-tracking contract docs, and read-model/API/contract tests. After Codex escalation found schema-contract drift in the accepted ledger fixture, added JSON Schema validation to the read model, required `ledger_policy`, converted the fixture to a schema-valid contract artifact, and added read-model delayed-entry rejection coverage.

## MiMo Code-Review Result

Passed. Initial MiMo read-model shard found no blocker or major issues and noted only that response-model preservation needed confirmation. Later MiMo Read-based schema shards were inconclusive because the external Read path exited with 143 or produced pseudo-tool calls, so a no-tool evidence review was run after the Codex fixes. Final MiMo evidence review reported no blocker, major, or minor issues and concluded W-002 is ready to merge: `paper_governance` is preserved, fixed85/fixed80 are future-observation only, fixed90/delayed actions fail closed, zero-record missing-ledger behavior is tested, and gates passed.

## Codex Escalation Code-Review Result

Passed after fixes. The native Codex explorer initially reported two major issues and one minor issue: the read model accepted schema-invalid ledger fixtures without JSON Schema validation, `row_contract.ledger_policy` was optional, and delayed-entry rejection lacked a read-model/API-path test. All were accepted and fixed. Codex re-review reported: remaining blocker none, remaining major none, remaining minor none.

## Gate Results

- `PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_paper_tracking_contract.py tests/test_shortpick_v2_read_model_api.py` => `17 passed in 1.43s`.
- `bash -n scripts/run-shortpick-v2-h10-paper-governance.sh && bash -n scripts/verify-shortpick-v2-h10-paper-governance-runtime.sh && PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_h10_paper_governance.py tests/test_shortpick_v2_paper_tracking_contract.py tests/test_shortpick_v2_read_model_api.py` => `28 passed in 1.39s`.
- `python3 -m ruff check src/ashare_evidence/shortpick_v2_h10_paper_governance.py src/ashare_evidence/shortpick_v2_read_model.py src/ashare_evidence/schemas/shortpick.py tests/test_shortpick_v2_h10_paper_governance.py tests/test_shortpick_v2_paper_tracking_contract.py tests/test_shortpick_v2_read_model_api.py src/ashare_evidence/cli.py` => passed.
- `python3 -m json.tool docs/contracts/registry/schemas/shortpick_v2_paper_tracking_ledger.schema.json >/dev/null` => passed.

## Plan Update Summary

Updated `plans/active/plan-20260615-h10-paper-governance.md`: W-002 status is `done`, evidence records the W-002 focused gate, combined W-001/W-002 gate, ruff pass, MiMo final PASS, and Codex escalation PASS after fixes. Revision history and external review log were extended for W-002.

## Plan Archive Result

Not applicable for W-002. The full plan remains executing with W-003 and W-004 pending.

## Archive And Merge Result

W-002 run document archived to `runs/archive/2026-06-15-W-002-h10-paper-governance.md`. Full-plan execution continues to W-003; merge/push remains deferred until the full plan closeout.
