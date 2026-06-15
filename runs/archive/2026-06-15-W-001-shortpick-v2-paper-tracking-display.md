# Run: 2026-06-15-W-001-shortpick-v2-paper-tracking-display

## Run ID

2026-06-15-W-001-shortpick-v2-paper-tracking-display

## Plan path

/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260615-shortpick-v2-paper-tracking-display/plans/active/plan-20260615-shortpick-v2-paper-tracking-display.md

## Hop ID

W-001

## Work item ID

W-001

## Goal

Build the backend v2 paper-tracking display projection so the API supplies latest-trade, strategy, chart, table, replay-tag, inclusive coverage, true-forward separation, and additive compatibility data for the v2 frontend.

## Non-goals

- Do not implement frontend rendering in this run; W-002 owns that.
- Do not implement a true-forward paper-ledger writer.
- Do not run strategy search, parameter tuning, or fixed90 promotion.
- Do not add delayed buy, retry buy, or discretionary later entry.
- Do not publish runtime in this run; W-003 owns final-main publish and served verification.

## Plan evidence

W-001 task: Build the v2 paper-tracking display projection, including replay-tagged catch-up rows, inclusive window coverage metadata, additive API fields, and readable summaries while preserving H10 governance boundaries.

Deliverable: backend read model/schema/tests for latest trade, strategy explanation, chart/table data, replay tags, true-forward separation, inclusive coverage, and API compatibility.

Acceptance type: `test_pass`.

Acceptance spec: `cmd:PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_read_model_api.py tests/test_shortpick_v2_paper_tracking_contract.py`.

## Source coverage evidence

| Source ID | Source Requirement | W-001 Coverage |
|-----------|--------------------|----------------|
| SRC-002 | Stop presenting historical backtest/config data as the main paper-tracking display. | Read model will provide display-specific readable structures instead of requiring the frontend to expose raw contract/config fields. |
| SRC-003 | Match v1 structure: latest simulated trade, strategy explanation, charts, and table. | W-001 supplies backend fields for those sections; W-002 renders them. |
| SRC-004 | Add inclusive `signal_date >= 2026-05-08` data with `回放` tag. | W-001 supplies replay-tagged rows or readable gaps and coverage metadata for the inclusive window. |
| SRC-005 | Ban field-shaped/raw unreadable UI content. | W-001 provides Chinese-readable labels and display fields so W-002 does not rely on raw identifiers. |
| SRC-006 | Preserve H10 governance: replay rows are not true-forward, fixed90 diagnostic-only, no delayed buy. | W-001 separates replay/true-forward counts and keeps fixed90/delayed actions blocked. |
| SRC-009 | Keep API response compatible. | W-001 keeps existing fields stable and adds optional/additive display fields with tests. |
| SRC-010 | Schema/deployment-risk work requires Codex escalation evidence. | W-001 run-plan and code changes require Codex escalation review. |

## Production path fidelity evidence

| Path ID | User / Production Path | W-001 Validation |
|---------|------------------------|------------------|
| PF-001 | User opens the real served dashboard route. | Deferred to W-003 final-main runtime publish and browser/API verification; W-001 only prepares backend display data. |
| PF-002 | `/shortpick-lab-v2/paper-tracking` returns the data consumed by the v2 paper tab. | Add TestClient/read-model coverage for display shape, compatibility, replay tags, and row/gap counts; W-003 later covers served API. |
| PF-003 | Backend projection builds catch-up rows without refresh/model calls/ledger writes. | Add read-model tests that use deterministic fixtures for edge cases and assert no true-forward ledger row is synthesized. |
| PF-004 | Frontend converts backend fields into readable Chinese. | W-001 supplies readable fields; W-002 validates visible strings. |

## Files expected to change

- `src/ashare_evidence/shortpick_v2_read_model.py`
- `src/ashare_evidence/schemas/shortpick.py`
- `docs/contracts/registry/schemas/shortpick_v2_paper_tracking_ledger.schema.json` if response contract documentation needs additive field notes
- `docs/contracts/SHORTPICK_LAB_V2_PAPER_TRACKING_CONTRACT_2026-06-12.md` if the display projection semantics need durable documentation
- `tests/test_shortpick_v2_read_model_api.py`
- `tests/test_shortpick_v2_paper_tracking_contract.py`

## Implementation steps

1. Inspect current v2 read model and paper contract tests.
2. Add additive display projection fields for latest simulated trade, strategy explanation, chart rows, table rows, coverage metadata, and user-readable status labels.
3. Bind `latest_source_signal_date` and available source signal dates to the production read-model resolver path: use committed/runtime artifact resolution first, then the same backend read-model source resolver used by `/shortpick-lab-v2/paper-tracking`; fixtures may only cover edge cases and cannot define the production coverage universe.
4. Add replay-tagged row/gap projection for the inclusive `2026-05-08` to latest available source date window.
5. Preserve existing response envelope fields and summary/full endpoint behavior.
6. Add tests for replay/true-forward separation, fixed90/delayed-action boundaries, coverage metadata, display shape, and compatibility.

## Acceptance criteria

- Targeted W-001 pytest command passes.
- Existing v2 paper-tracking response fields remain present.
- New display fields are additive/optional.
- Replay display rows have visible replay classification fields and do not increment true-forward counts.
- Coverage metadata proves `coverage_start`, `coverage_end`, `latest_source_signal_date`, replay row count, gap count, inclusive start date, and row-or-gap accounting.
- Fixed90 and delayed-entry actions remain blocked.

## Acceptance Type and Acceptance Spec

Acceptance Type: `test_pass`

Acceptance Spec: `cmd:PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_read_model_api.py tests/test_shortpick_v2_paper_tracking_contract.py`

## Planned Evidence

- MiMo run-plan review: pending.
- Codex escalation run-plan review: pending.
- MiMo code review: pending.
- Codex escalation code review: pending.
- Targeted tests: pending.
- Plan validation: command already passed before W-001 run-plan review and will run again after W-001 plan update.

## Actual Evidence

- 2026-06-15T12:21:30Z: Plan status changed to executing and W-001 status changed to in_progress.
- 2026-06-15T12:45Z: Implemented additive `paper_display` projection, schema field, and API session binding for v2 paper tracking.
- 2026-06-15T12:50Z: Added replay-tagged display rows from `2026-05-08`, readable strategy/action labels, true-forward/replay separation, row-or-gap coverage accounting, source-gap rows, and safe replay-generation downgrade.
- 2026-06-15T12:55Z: Added `decision_sample_limit` parameterization to the v2 replay engine so W-001 display projection can cover more than the default 40 decision samples without false gaps.
- 2026-06-15T13:00Z: Applied MiMo code-review minor fixes: summary paths skip detail-row construction and replay cache writes remove expired entries.
- 2026-06-15T13:05Z: `PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_read_model_api.py tests/test_shortpick_v2_paper_tracking_contract.py` passed with 22 tests.
- 2026-06-15T12:55Z: `PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_replay.py tests/test_shortpick_v2_strategy_search.py` passed with 48 tests for replay signature compatibility.

## Risk and rollback notes

Primary rollback is to revert W-001 backend/schema/test changes before W-002 depends on them. The main risk is accidentally converting replay rows into paper rows; tests must assert true-forward counts remain separate and fixed90/delayed actions remain blocked.

## Gate plan

- `python3 /Users/hernando_zhao/.codex/skills/reviewed-plan-generator/scripts/validate_plan.py plans/active/plan-20260615-shortpick-v2-paper-tracking-display.md`
- MiMo W-001 run-plan review.
- Codex W-001 run-plan escalation review.
- MiMo W-001 code review.
- Codex W-001 code escalation review.
- `PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_read_model_api.py tests/test_shortpick_v2_paper_tracking_contract.py`

## MiMo plan-review result

Passed with no blocker or major findings. Two traceability minors were accepted and resolved in this run document: PF-001 is explicitly deferred to W-003, and plan validation timing is clarified in Planned Evidence.

## Codex escalation plan-review result

Passed with no blockers. Findings were accepted before implementation: W-001 will not change frontend TypeScript files; frontend type/build validation stays in W-002. W-001 now binds source-date coverage to the production read-model/artifact resolver path and requires tests to assert `coverage_end`, `latest_source_signal_date`, replay count, gap count, and full/summary compatibility.

## Implementation summary

Added the W-001 backend data contract for the new v2 paper-tracking display. The API now passes a DB session into the read model; the response schema includes additive `paper_display`; and the read model builds latest-trade, strategy-explanation, chart, table, coverage, and summary-card structures for the frontend. Full `/paper-tracking` can generate `回放` rows or readable source gaps from `2026-05-08` through the latest available signal date, while `/paper-tracking/summary` returns no detail rows and does not run replay generation. Replay rows remain display-only, true-forward counts remain separate, fixed90 remains excluded, and delayed buy remains forbidden. The replay engine keeps its default 40-sample behavior but accepts a caller-provided `decision_sample_limit` for this display projection.

## MiMo code-review result

Passed with no blocker or major findings. MiMo initially listed four minor items; two were accepted and fixed in W-001: avoid unnecessary detail-row work on summary paths, and purge expired replay-cache entries on cache writes. The remaining sync first-request compute/URL-normalization comments are recorded as non-blocking performance notes for W-003 served runtime verification.

## Codex escalation code-review result

Passed with no blocker or major findings. Codex escalation confirmed that the four named risks are closed: summary omits rows and avoids replay recompute, replay generation is cached and degrades instead of raising 500, caller-provided `decision_sample_limit` prevents the historical 40-sample truncation from creating false gaps, and `paper_display.table.rows` omits raw `config_id`, `action`, `source_state`, and decision-field data.

## Gate results

- `PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_read_model_api.py tests/test_shortpick_v2_paper_tracking_contract.py`: passed, 22 tests in 3.67s.
- `PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_replay.py tests/test_shortpick_v2_strategy_search.py`: passed, 48 tests in 0.90s.
- Line-width scan for `shortpick_v2_read_model.py`, `shortpick_v2_replay.py`, and `test_shortpick_v2_read_model_api.py`: passed, no lines over 120 columns.

## Plan update summary

Updated plan W-001 status from `in_progress` to `done`, added test/review evidence to the work item, appended revision history row 5, and recorded W-001 MiMo/Codex code-review outcomes in the external review log.

## Plan archive result

Not applicable until full-plan completion.

## Archive and merge result

Pending.
