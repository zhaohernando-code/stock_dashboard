# Run: 2026-06-18-W-001 Shortpick v2 Paper Loading Closeout

## Run ID

2026-06-18-W-001-shortpick-v2-paper-loading-closeout

## Plan path

`/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260618-shortpick-v2-paper-loading-fix/plans/active/plan-20260618-shortpick-v2-paper-loading-closeout.md`

## Hop ID

W-001 through W-004

## Work item ID

W-001, W-003, W-004

## Goal

Close the user-visible Shortpick v2 paper tracking loading defect by removing skip-only true-forward account-curve recomputation, adding regression coverage, adding runtime full API latency verification, publishing runtime, and merging cleanly.

## Non-goals

- Do not change trading strategy rules or v2 paper ledger write policy.
- Do not redesign frontend loading unless the backend/runtime fix fails the served route check.
- Do not implement a long-term cache for future true-forward buy rows in this run.

## Plan evidence

Plan schema validation passed after MiMo plan review. MiMo found no blocking issues. Accepted fixes: quantify full API threshold, make investigation/review precede implementation, and include the user's full URL parameters.

## Source coverage evidence

- SRC-001: W-001/W-003 will directly fix and validate the loading issue.
- SRC-002: Investigation record exists under `docs/investigations`.
- SRC-003: User has already approved continuing without approval blockers; plan status moved to executing only after MiMo review.
- SRC-004: W-004 requires publish and served route/API verification.
- SRC-005: W-003 adds the runtime full API latency gate missing from prior closeout.

## Production path fidelity evidence

- PF-001: publish and served route/API validation will exercise the real user path.
- PF-002: runtime verification script will call the real runtime API.
- PF-003: pytest uses controlled simulation only for the branch-level skip-only invariant; runtime gates cover product path.

## Files expected to change

- `src/ashare_evidence/shortpick_v2_read_model.py`
- `tests/test_shortpick_v2_paper_ledger.py`
- `scripts/verify-shortpick-v2-paper-ledger-runtime.sh`
- `docs/investigations/SHORTPICK_V2_PAPER_LOADING_CLOSEOUT_2026-06-18.md`
- `plans/active/plan-20260618-shortpick-v2-paper-loading-closeout.md`
- this run record, later archived under `runs/archive/`

## Implementation steps

1. Patch read model so skip-only true-forward rows do not invoke session-level account curve recomputation.
2. Add a regression test that fails if skip-only ledger calls `_paper_display_account_curves_from_session`.
3. Add full API latency threshold to runtime verification script.
4. Run targeted tests and runtime verification.
5. Run MiMo code review.
6. Publish runtime and validate served API/page path.
7. Archive run, update plan evidence, commit, push, merge to main, push main, cleanup worktree.

## Acceptance criteria

- `python3 -m pytest -q tests/test_shortpick_v2_paper_ledger.py tests/test_shortpick_v2_read_model_api.py` passes.
- `bash scripts/verify-shortpick-v2-paper-ledger-runtime.sh` passes after publish and reports full API latency within threshold.
- Runtime full `/shortpick-lab-v2/paper-tracking` returns quickly enough to avoid a 10 second loading failure.
- Served route for v2 paper tracking is verified.

## Acceptance Type and Acceptance Spec

Primary acceptance follows the plan's W-001 and W-003 test/command gates plus W-004 manual closeout.

## Planned Evidence

Record command exits, key timing summaries, MiMo review disposition, publish output summary, and git closeout state.

## Actual Evidence

- Plan validation: `python3 .../validate_plan.py plans/active/plan-20260618-shortpick-v2-paper-loading-closeout.md` passed.
- MiMo plan review: no blocking findings; accepted and resolved threshold/dependency/URL feedback.
- Targeted pytest: `python3 -m pytest -q tests/test_shortpick_v2_paper_ledger.py tests/test_shortpick_v2_read_model_api.py` -> `35 passed in 9.20s`.
- MiMo code review round 1: no blocking; one major requiring with-buy test coverage.
- MiMo code rereview: `APPROVE`, no blocking/major; confirmed with-buy branch test resolves prior major.
- Publish: `ASHARE_PUBLISH_REFRESH_MODE=skip bash scripts/publish-local-runtime.sh` -> deploy verification `19 passed, 0 failed`; v2 paper cache prewarm `0.178s`.
- Runtime verifier: `bash scripts/verify-shortpick-v2-paper-ledger-runtime.sh` -> `status=ok`, `full_api_seconds=0.543`, `record_count=4`.
- Direct API timing: full `/shortpick-lab-v2/paper-tracking` -> `0.657190s`, `records=4`, `rows=60`, `curves=2`, `account_curve_scope=回放账户曲线，真实前向暂无买入`.
- Browser served route: local runtime root route with v2 query rendered `纸面追踪运行中`, `显示 60 / 60 条`, and 2026-06-16 rows in `1.825s`.
- Public route: authenticated canonical URL returned auth `302` instead of the previous 5173 proxy failure.
- Full default pytest: `961 passed, 173 deselected, 6 subtests passed in 34.47s`.
- Policy audit: `status=pass`.

## Risk and rollback notes

Rollback is a normal git revert of this branch's commit. The code path preserves existing behavior when true-forward rows contain buys.

## Gate plan

- Targeted pytest for v2 paper ledger/read model.
- Runtime verification script.
- Publish local runtime with refresh skipped.
- Runtime API timing and served route check.

## MiMo plan-review result

Passed with no blocking findings. Major findings were resolved before execution.

## Codex escalation plan-review result

Not required; plan does not touch migrations, credentials, security boundaries, or irreversible governance state.

## Implementation summary

Patched v2 paper tracking read model so skip-only true-forward rows reuse replay account curves and avoid session-level repricing. Added regression tests for both skip-only no-reprice and with-buy reprice paths. Added runtime full API timing threshold to `scripts/verify-shortpick-v2-paper-ledger-runtime.sh`.

## MiMo code-review result

Passed after rereview. Round 1 major for missing with-buy branch test was resolved by adding `test_shortpick_v2_paper_tracking_buy_ledger_reprices_account_curves`; rereview reported no blocking or major findings.

## Codex escalation code-review result

Not required unless MiMo code review is inconclusive or blocking.

## Gate results

Targeted pytest passed: `35 passed in 9.20s`. Publish passed with deploy verification `19 passed, 0 failed`. Runtime full API verifier passed at `0.543s` under the 10s threshold. Browser reload showed v2 paper content in `1.825s`. Full default pytest and policy audit passed.

## Plan update summary

Plan work items W-001 through W-004 marked done. Plan status moved to archived after evidence was recorded.

## Plan archive result

Plan moved from `plans/active/` to `plans/archive/` in the closeout commit.

## Archive and merge result

Run record moved to `runs/archive/` in the closeout commit. Branch push, main merge, origin/main push, and task worktree cleanup are completed after this archive commit.
