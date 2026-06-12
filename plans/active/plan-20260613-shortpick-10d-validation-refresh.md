---
schema_version: 1
plan_id: "plan-20260613-shortpick-10d-validation-refresh"
title: "Shortpick 10d Validation Refresh"
status: "executing"
created_at: "2026-06-13"
source_request: "Fix why paper-tracking 10-day charts stop at 2026-05-25 while 2026-05-26 rows exist."
target_repo: "/Users/hernando_zhao/codex/projects/stock_dashboard"
owner: "user"
review_rounds: 2
---

# Plan: Shortpick 10d Validation Refresh

## Compaction-Resistant Summary

Goal: make Short Pick Lab paper-tracking 10-day effect charts advance when matured 10-day validation data exists.
Scope: backend validation refresh selection/termination, focused tests, runtime publish and served API verification.
Out of scope: changing strategy parameters, chart semantics, paper-tracking advice language, or live trading behavior.
Dependency: `shortpick-lab-validate-recent` must continue to support `--existing-market-data-only`.
Risk: daily refresh can be slowed if validation selection becomes unbounded; keep bounded and deterministic.
Risk: direct DB mutation is not acceptable; verification may run refresh commands but code must preserve read/write contracts.
Approval state: approved by user on 2026-06-13; executing W-001.

## Goal

Resolve the stale 10-day paper-tracking chart issue by ensuring recent validation refresh revisits matured pending 10-day snapshots after market bars arrive, so the `/shortpick-lab/paper-tracking` API exposes completed `mechanical_10d` exit tracks and the chart can update from the API data.

## Problem / Rationale

The runtime database shows 2026-05-26 paper-tracking rows exist, but their 10-day validation snapshots remain `pending_forward_window`. Their payload was last computed with `available_forward_bars=8` and `required_forward_bars=10`, while market bars now extend beyond the needed window. The paper-tracking endpoint and frontend are read-only projections: they only display completed validation exit tracks already stored in `shortpick_validation_snapshots`. The likely defect is in `validate_recent_shortpick_runs`: the bounded pending-run selection can stop after old non-progressing pending rows before later matured runs are recalculated.

## Scope

### In Scope

- Diagnose and adjust recent shortpick validation refresh selection and loop termination so stale pending snapshots that can now mature are not stranded behind older no-progress pending rows.
- Preserve bounded runtime behavior for daily scheduled refresh.
- Add or update focused tests that reproduce the stranded pending scenario and prove the fix.
- Run fast regression and policy audit gates required by the project.
- Publish to the local runtime and verify the served runtime API or database state shows the 2026-05-26 10-day snapshot can complete.

### Out of Scope

- Changing frozen paper strategy roles, thresholds, formulas, horizons, or policy config versions.
- Changing frontend chart semantics to include pending rows as if they were completed results.
- Running real investment actions or changing simulation/paper portfolio behavior.
- Moving runtime integration tests into default pytest.

## Assumptions and Dependencies

- The authoritative current runtime database is `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db`.
- The user has requested the reviewed-plan and plan-run workflow; implementation waits for an approved schema-v1 plan.
- `shortpick-lab-validate-recent --existing-market-data-only` may update validation snapshots but must not fetch new market data.
- If a live-facing code change is made, the source must be published to `~/codex/runtime/projects/ashare-dashboard` before claiming completion.

## Work Items

| ID | Status | Order | Depends On | Task | Deliverable | Acceptance Type | Acceptance Spec | Evidence |
|----|--------|-------|------------|------|-------------|-----------------|-----------------|----------|
| W-001 | done | 1 | - | Fix recent validation refresh selection/termination and add focused regression coverage for old no-progress pending rows plus later matured pending rows. | Backend refresh logic plus regression test | test_pass | cmd:python3 -m pytest -q -m runtime_integration tests/test_shortpick_lab_validation.py | Implemented SQL-level processed-run exclusion and bounded catch-up; MiMo code review found no blocking/major issues; `python3 -m pytest -q -m runtime_integration tests/test_shortpick_lab_validation.py` passed, 17 passed in 1.87s. |
| W-002 | done | 2 | W-001 | Run the default fast regression suite. | Default pytest gate result | test_pass | cmd:python3 -m pytest -q | MiMo run-plan review found no blocking/major issues; latest rerun after the W-004 runtime settings fix passed with 809 passed, 172 deselected, 6 subtests passed in 25.00s. |
| W-003 | done | 3 | W-002 | Run the parameter/formula governance policy audit. | Policy audit gate result | command_exit_0 | cmd:PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage | MiMo run-plan review found no blocking/major issues; latest rerun after the W-004 runtime settings fix exited 0 with status `pass` and no direct_config_read, formula_side_effects, missing_config_lineage, or new_unclassified failures. |
| W-004 | in_progress | 4 | W-003 | Publish verified source to the local runtime. | Runtime source updated under `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard` | command_exit_0 | cmd:ASHARE_PUBLISH_REFRESH_MODE=skip bash scripts/publish-local-runtime.sh | Publish exposed a runtime settings cold-path timeout in `/settings/runtime`; added a bounded AKShare readiness probe for settings display and reran gates. |
| W-005 | pending | 5 | W-004 | Run runtime validation refresh and assert the 2026-05-26 10-day paper-tracking snapshots are completed in runtime data. | Runtime validation evidence for 2026-05-26 10-day completion | command_exit_0 | cmd:bash scripts/verify-shortpick-10d-runtime-refresh.sh |  |

## Acceptance Criteria & Validation Gates

### Overall Acceptance Criteria

- The code change causes `shortpick-lab-validate-recent` to reconsider pending 10-day snapshots that have become mature, even when older pending rows do not complete.
- The paper-tracking read model remains read-only and continues to chart only completed exit tracks.
- The runtime source is published after code verification.
- A runtime verification command demonstrates that the stale 2026-05-26 10-day paper-tracking validation no longer remains stranded when the validation refresh is run against available data.
- Final closeout explicitly states whether the work is merged to `main` and pushed to `origin/main`.

### Validation Gates

- `python3 -m pytest -q -m runtime_integration tests/test_shortpick_lab_validation.py`
- `python3 -m pytest -q`
- `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage`
- `ASHARE_PUBLISH_REFRESH_MODE=skip bash scripts/publish-local-runtime.sh`
- `bash scripts/verify-shortpick-10d-runtime-refresh.sh`

## Risks and Mitigations

- Risk: widening validation selection could slow the scheduled refresh. Mitigation: keep explicit caps and select likely-mature pending rows deterministically instead of unbounded scanning.
- Risk: tests could mock too much and miss the selection bug. Mitigation: include a regression that requires the loop to continue past old no-progress pending rows to later pending rows.
- Risk: runtime DB writes during verification could change evidence unexpectedly. Mitigation: only run intended refresh/publish commands and record before/after status.
- Risk: a fix that changes chart behavior would mask data freshness. Mitigation: do not change frontend chart filtering in this plan.

## Open Questions

- None currently; implementation may surface whether the final runtime verification should use CLI-only DB evidence or the served API if the local backend is already running.

## Revision History

- 2026-06-13: Drafted plan from read-only diagnosis of stale 10-day paper-tracking validation.
- 2026-06-13: Accepted MiMo review findings by merging behavioral fix and regression acceptance, splitting gates/publish/runtime verification into separate work items, and adding a concrete runtime verification command.
- 2026-06-13: Marked plan reviewed after MiMo confirmed prior findings were closed and no blocking or major issues remained.
- 2026-06-13: User approved execution; status changed from reviewed to executing and W-001 changed from pending to in_progress.
- 2026-06-13: Corrected W-001 acceptance command to include `-m runtime_integration` because project pytest defaults deselect that test file.
- 2026-06-13: W-001 changed from in_progress to done after implementation, MiMo code review, and focused validation tests passed.
- 2026-06-13: W-002 changed from pending to in_progress to run the default fast regression suite.
- 2026-06-13: W-002 changed from in_progress to done after default fast pytest passed.
- 2026-06-13: W-003 changed from pending to in_progress to run policy audit.
- 2026-06-13: W-003 changed from in_progress to done after policy audit passed.
- 2026-06-13: W-004 changed from pending to in_progress to publish verified source to runtime.
- 2026-06-13: W-004 publish attempts exposed `/settings/runtime` timeout from AKShare cold import; added bounded settings-only readiness probe and refreshed W-002/W-003 gate evidence.

## External Review Log

| Round | Reviewer | Finding | Severity | Disposition | Reason | Affected IDs |
|-------|----------|---------|----------|-------------|--------|--------------|
| 1 | MiMo | W-003 did not include concrete runtime verification despite overall acceptance requiring proof that 2026-05-26 10-day snapshots are no longer stranded. | blocking | accepted | Added W-005 with an explicit runtime verification command. | W-005 |
| 1 | MiMo | W-003 mixed pytest, policy audit, publish, and runtime verification into one work item. | major | accepted | Split gates, publish, and runtime verification into W-002 through W-005. | W-002, W-003, W-004, W-005 |
| 1 | MiMo | W-001 acceptance only checked that the function name existed and did not prove behavior. | major | accepted | Combined the backend fix with focused regression acceptance in W-001. | W-001 |
| 2 | MiMo | Prior findings closed; W-001 through W-005 are executable and cover the end-to-end objective. | note | resolved | No blocking or major issues remained in the revised plan. | W-001, W-002, W-003, W-004, W-005 |

## User Review Notes

- User approved execution with: "批准，按这个计划执行".
