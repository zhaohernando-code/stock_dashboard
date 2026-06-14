# Run ID

2026-06-14-W-001-shortpick-v2-strategy-search

## Plan path

`/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260614-shortpick-v2-strategy-backtest-6e3c42/plans/active/plan-20260614-shortpick-v2-strategy-search.md`

## Hop ID

W-001

## Work item ID

W-001

## Goal

Implement the reusable `试验田v2` strategy-search batch producer and CLI entrypoint, preserving existing v2 execution constraints and focused tests.

## Non-goals

- Do not run the full real-data runtime DB batch in this hop.
- Do not change frontend, API read models, runtime deployment, scheduler behavior, or paper-tracking promotion.
- Do not introduce delayed buy behavior or event/intraday strategies that lack confirmed source data.
- Do not change the strict v2 rule-selection gates.

## Plan evidence

- Plan status is `executing`.
- W-001 is `in_progress`.
- MiMo plan review was incorporated into the plan before execution.
- Existing v2 replay has reusable `build_shortpick_v2_replay_artifact_from_series(...)`.
- Existing rule selection requires a compatible replay artifact with the five current control configs present.

## Files expected to change

- `src/ashare_evidence/shortpick_v2_strategy_search.py`
- `src/ashare_evidence/cli.py`
- `tests/test_shortpick_v2_strategy_search.py`
- `plans/active/plan-20260614-shortpick-v2-strategy-search.md`
- `runs/active/2026-06-14-W-001-shortpick-v2-strategy-search.md`

## Implementation steps

1. Add a strategy-search module that loads/reuses v2 daily series once per batch.
2. Encode a bounded first batch of daily-bar-feasible candidate families and execution variants.
3. Include the existing five v2 configs as controls.
4. Produce the `shortpick_v2_replay_artifact` compatible envelope by delegating candidate-family batches to the existing `build_shortpick_v2_replay_artifact_from_series(...)` path and then performing a deterministic merge of compatible child `rule_matrix` and `results`; do not hand-build an independent envelope with divergent semantics.
5. Add CLI parser and handler for `shortpick-v2-strategy-search`.
6. Add focused tests covering parser registration, artifact shape, no delayed buy compatibility, existing controls, schema shape, and direct `build_shortpick_v2_rule_selection_artifact(...)` compatibility on the merged output.

## Acceptance criteria

Focused tests pass:

`PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_strategy_search.py tests/test_shortpick_v2_replay.py tests/test_shortpick_v2_rule_selection.py`

## Acceptance Type and Acceptance Spec

- Acceptance Type: `test_pass`
- Acceptance Spec: `cmd:PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_strategy_search.py tests/test_shortpick_v2_replay.py tests/test_shortpick_v2_rule_selection.py`

## Planned Evidence

- Focused pytest exit code 0.
- Plan validator exit code 0 after W-001 completion.
- MiMo code review has no blocking findings.

## Actual Evidence

- Implemented `src/ashare_evidence/shortpick_v2_strategy_search.py`.
- Added `shortpick-v2-strategy-search` CLI parser and handler in `src/ashare_evidence/cli.py`.
- Added `tests/test_shortpick_v2_strategy_search.py`.
- Focused pytest passed: `15 passed in 2.78s`.
- Plan validator passed after W-001 plan update.

## Risk and rollback notes

Main risk is accidentally changing v2 replay semantics while adding strategy-search orchestration. Keep account simulation reuse narrow and test control configs. Rollback is to remove the new module, CLI entry, tests, and W-001 plan/run updates before merge.

## Gate plan

- MiMo run-plan drift review before implementation.
- MiMo code-risk review after implementation.
- Focused pytest for strategy-search, replay, and rule-selection.
- Schema-v1 plan validation.

## MiMo plan-review result

Passed after resolving one major ambiguity. MiMo found no scope drift, but asked the run to specify whether W-001 reuses the existing replay artifact builder or hand-builds a new envelope. Resolution: W-001 will reuse `build_shortpick_v2_replay_artifact_from_series(...)` for candidate-family child artifacts and merge only compatible `rule_matrix`/`results`, with focused tests covering rule-selection compatibility.

## Codex escalation plan-review result

Not required; this hop avoids schema, migration, security, deployment, and runtime isolation changes.

## Implementation summary

Added a batched v2 strategy-search producer that builds candidate-family child replay artifacts through `build_shortpick_v2_replay_artifact_from_series(...)`, merges compatible `rule_matrix` and `results`, preserves the five original control config IDs, and emits a `shortpick_v2_replay_artifact` compatible with existing rule selection. Added CLI registration and tests for parser defaults, schema validation, control/prefixed config merge, no-delayed-entry evidence, and rule-selection compatibility.

## MiMo code-review result

PASS. Sharded MiMo review found no blocking or major implementation issues. It confirmed artifact compatibility, no-delayed-buy inheritance, five control config retention, CLI parameter wiring, and rule-selection compatibility tests. It noted a minor fallback/skip-specific test gap, accepted because the W-001 gate includes existing `tests/test_shortpick_v2_replay.py` fallback/skip regression coverage.

## Codex escalation code-review result

Not required unless MiMo flags an unresolved blocker.

## Gate results

- `PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_strategy_search.py tests/test_shortpick_v2_replay.py tests/test_shortpick_v2_rule_selection.py`: exit 0, `15 passed in 2.78s`.
- `python3 /Users/hernando_zhao/.codex/skills/reviewed-plan-generator/scripts/validate_plan.py plans/active/plan-20260614-shortpick-v2-strategy-search.md`: exit 0, `Plan is valid.`

## Plan update summary

Updated W-001 from `in_progress` to `done` with non-empty evidence and appended a revision-history entry. Top-level plan remains `executing` because W-002 through W-004 are still pending.

## Plan archive result

Not applicable for W-001; plan remains active until all work items complete.

## Archive and merge result

Archived to `runs/archive/2026-06-14-W-001-shortpick-v2-strategy-search.md`. Branch is not merged because full-plan execution continues with W-002.
