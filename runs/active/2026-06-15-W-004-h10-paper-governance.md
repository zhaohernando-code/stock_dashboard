# Run ID

2026-06-15-W-004-h10-paper-governance

## Plan Path

`/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260615-h10-paper-governance-150154/plans/active/plan-20260615-h10-paper-governance.md`

## Hop ID

W-004

## Work Item ID

W-004

## Goal

Complete closeout for H10 paper governance by reviewing final scope, committing the live-facing source changes, running the runtime verification script from a clean committed worktree, publishing to the local runtime, verifying the real served V2 paper-tracking governance state, then archiving the plan/run records and merging/pushing per the plan-run-loop contract.

## Non-Goals

- Do not alter strategy parameters, governance thresholds, candidate IDs, fixed90 policy, or paper-ledger semantics in W-004.
- Do not create or backfill true-forward paper ledger rows.
- Do not rerun broad strategy search outside the reviewed W-004 verification script.
- Do not claim production trading or investment readiness.
- Do not skip runtime publish or served API verification for live-facing changes.

## Plan Evidence

W-004 deliverable: focused/default gate evidence, runtime publish evidence, served API verification, archived plan/run docs.

Acceptance: `bash scripts/verify-shortpick-v2-h10-paper-governance-runtime.sh`.

## Source Coverage Evidence

- SRC-001: complete reviewed-plan-generator + plan-run-loop execution with W-001/W-002/W-003 archived and W-004 active.
- SRC-002: final closeout must preserve fixed85 as primary future-observation candidate and fixed80 as capital shadow.
- SRC-003: runtime served state must expose governance readiness without historical paper-row backfill.
- SRC-004: runtime served state must preserve no delayed-buy governance.
- SRC-005: final artifacts must preserve qualification gates that require market outperformance and at least 30% annualized return.
- SRC-006: fixed90 must remain diagnostic-only and rejected from active paper configs.
- SRC-007: no parameter-search UI or broad strategy direction is added.
- SRC-008: served/runtime state must remain research-observation governance, not investment/production/auto-trading.
- SRC-009: MiMo and Codex escalation reviews are required before merge because this hop publishes live-facing schema/governance behavior.

## Production Path Fidelity Evidence

- PF-001: W-003 already ran the real generation script from runtime DB and produced the docs/archive governance artifact consumed by runtime.
- PF-002: W-002 schema/read-model gates already proved future row acceptance/rejection; W-004 does not create rows.
- PF-003: W-004 verifies the real served `/shortpick-lab-v2/paper-tracking/summary` payload after publish, proving the read model exposes governance state with zero rows. The controlled TestClient/read-model evidence remains covered by the default `pytest -q` step in `scripts/verify-shortpick-v2-h10-paper-governance-runtime.sh`, including `tests/test_shortpick_v2_read_model_api.py`.
- PF-004: W-004 runs the project runtime verification script, which executes default gates, requires a clean committed worktree, publishes runtime with refresh skipped, and verifies the served API.

## Files Expected To Change

- `plans/active/plan-20260615-h10-paper-governance.md`
- `plans/archive/plan-20260615-h10-paper-governance.md` after full-plan archive
- `runs/active/2026-06-15-W-004-h10-paper-governance.md`
- `runs/archive/2026-06-15-W-004-h10-paper-governance.md`
- Git metadata through commits, branch push, main fast-forward/update, and base-branch push

Temporary active state files expected during the run only:

- `runs/active/latest.json`
- `runs/active/2026-06-15-W-004-h10-paper-governance.state.json`
- `runs/active/plan-20260615-h10-paper-governance.lock`

## Implementation Steps

1. Run MiMo and Codex run-plan review for W-004 before committing or publishing.
2. Run final MiMo and Codex code/artifact review over the current W-001 through W-003 changes and W-004 run scope.
3. Stage and commit the implementation, durable artifacts, plan updates, and archived W-001/W-002/W-003 run records so the worktree can be clean for runtime verification.
4. Run `bash scripts/verify-shortpick-v2-h10-paper-governance-runtime.sh` from the clean committed worktree.
5. Record verification evidence, mark W-004 done, validate the plan, archive this run document, archive the completed plan, and commit closeout-only records.
6. Push the task branch, merge/update `main`, push `origin/main`, release the lock, and clean temporary active state files.

## Acceptance Criteria

The W-004 verification script exits 0 from a clean committed worktree, runtime publish succeeds, and the served paper-tracking summary returns zero true-forward rows plus H10 governance state with fixed85/fixed80 candidates and fixed90 diagnostic rejection.

## Acceptance Type

command_exit_0

## Acceptance Spec

`cmd:bash scripts/verify-shortpick-v2-h10-paper-governance-runtime.sh`

## Planned Evidence

- MiMo run-plan review: pending.
- Codex escalation run-plan review: pending.
- MiMo code/artifact review: pending.
- Codex escalation code/artifact review: pending.
- Pre-verification implementation commit: pending.
- Acceptance command output: pending.
- Runtime publish evidence: pending.
- Served API verification: pending.
- Plan validator: pending.
- Branch push/base merge/base push: pending.

## Actual Evidence

- Pre-commit focused checks passed: `bash -n scripts/run-shortpick-v2-h10-paper-governance.sh && bash -n scripts/verify-shortpick-v2-h10-paper-governance-runtime.sh && PYTHONPATH=src python3 -m pytest -q tests/test_shortpick_v2_h10_paper_governance.py tests/test_shortpick_v2_paper_tracking_contract.py tests/test_shortpick_v2_read_model_api.py && python3 /Users/hernando_zhao/.codex/skills/reviewed-plan-generator/scripts/validate_plan.py plans/active/plan-20260615-h10-paper-governance.md` produced `28 passed in 1.30s` and `Plan is valid.`
- First W-004 acceptance attempt from implementation commit `ca567fd` passed default pytest (`910 passed, 1 skipped, 173 deselected, 6 subtests passed in 27.99s`), policy audit (`status=pass`), frontend production build, and runtime sync, but failed waiting for backend health: `Timed out waiting for http://127.0.0.1:8000/health`.
- Runtime failure root cause: foreground runtime backend start failed with `ModuleNotFoundError: No module named 'jsonschema'` from `shortpick_v2_read_model.py`. Fix: added `jsonschema>=4.0,<5.0` to `pyproject.toml` and installed it into the local backend venv used by the LaunchAgent.

## Risk And Rollback Notes

Risk: runtime verification can fail because the local served API is down or still serving a stale runtime copy. Mitigation: the verification script publishes before served checks and fails instead of claiming closeout; repair runtime service only if needed and record the evidence.

Risk: committing before runtime verification can leave a bad commit if gates fail. Mitigation: keep the branch isolated, fix in follow-up commits before push/merge, and do not update main until verification passes.

Risk: closeout docs written after runtime verification create a clean-worktree mismatch. Mitigation: runtime-affecting source is committed before verification; post-verification commits are plan/run documentation only.

Rollback: keep `main` untouched until W-004 gates pass; if runtime verification fails, do not merge, record failure in this run document, and fix on the task branch.

## Gate Plan

- MiMo run-plan review before final commit/publish.
- Codex escalation run-plan review before final commit/publish.
- MiMo code/artifact review before final commit/publish.
- Codex escalation code/artifact review before final commit/publish.
- `bash scripts/verify-shortpick-v2-h10-paper-governance-runtime.sh` after the implementation commit.
- Schema-v1 plan validator after marking W-004 done and before plan archive.
- Final merge assertions before task branch push, main update, and base-branch push.

## MiMo Plan-Review Result

Initial review found no blocker. Major MA-01 accepted: PF-003 TestClient/read-model evidence needed to be explicit in the W-004 run plan because served curl verification proves PF-004 while default pytest carries the controlled API/read-model path. The run plan now records that `pytest -q` covers `tests/test_shortpick_v2_read_model_api.py`. Minor notes on broad default pytest, `git status --short`, and `curl` dependency are accepted as non-blocking project/runtime constraints; default pytest is required by project hooks and the script failure mode remains explicit enough for local closeout. Focused re-review passed with no remaining blocker, major, or minor.

## Codex Escalation Plan-Review Result

Initial review found no blocker. Major accepted and fixed: served API verification now requires `candidate_ids == {fixed85,fixed80}` and explicitly rejects fixed90 in candidate IDs instead of only checking a subset. Minor accepted and fixed: the script now refuses non-`skip` `ASHARE_PUBLISH_REFRESH_MODE` so W-004 publish evidence cannot be generated with a refresh mode outside the plan contract. Focused Codex re-review passed with no remaining blocker, major, or minor.

## Implementation Summary

Pending.

## MiMo Code-Review Result

Passed. MiMo sharded final code/artifact review found no blocker or major issue. It confirmed the implementation does not return fake rows or treat historical replay as paper tracking; fixed85/fixed80 are the only future-observation candidates; fixed90 remains diagnostic-only; no delayed buy/no backfill/research-only semantics are consistently enforced across schema, read model, artifact builder, scripts, and tests; and the runtime verification script checks clean committed tree, publish, and served API state. Non-blocking notes/minors were accepted without code changes: schema/read-model double coverage already rejects fixed90 rows, W-003 generation script does not need clean-tree enforcement, and one replay-route coverage gap is outside W-004 acceptance because paper-tracking served verification plus default pytest cover the governed path.

## Codex Escalation Code-Review Result

Passed. Codex subagent final diff review found no blocker, major, or minor issue. It confirmed missing-ledger projection returns zero records, real ledger rows are schema/config/action/evidence-basis validated, fixed85/fixed80 are the only candidates, fixed90 is diagnostic-only, no delayed-buy/no-backfill/research-only constraints are aligned, and runtime verification publishes from a clean committed tree before checking the served summary API.

## Gate Results

- Passed: pre-commit script syntax, focused pytest, and plan validator (`28 passed in 1.30s`; `Plan is valid.`)
- Failed then fixed: first `bash scripts/verify-shortpick-v2-h10-paper-governance-runtime.sh` attempt failed at backend health because runtime venv lacked `jsonschema`.
- Pending: rerun W-004 acceptance command after dependency declaration/fix commit.

## Plan Update Summary

Pending.

## Plan Archive Result

Pending.

## Archive And Merge Result

Pending.
