# Run ID

2026-06-13-operations-http-performance-W-001

## Plan path

/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260613-stabilize-operations-http-performance-c090a7/plans/active/plan-20260613-operations-http-performance.md

## Hop ID

W-001

## Work item ID

W-001

## Goal

Split `GET /dashboard/operations/details?section=portfolios` from the full operations dashboard build so the portfolios detail endpoint avoids unrelated cold work while preserving the existing route and frontend-visible payload shape.

## Non-goals

- Do not change stock strategy semantics, paper tracking semantics, auth policy, database schema, or refresh behavior.
- Do not change the public URL, query parameters, or response envelope for `section=portfolios`.
- Do not implement release verifier reuse, performance probe scripting, or publish verification in this hop.

## Plan evidence

The approved plan identifies the current slow path: `section=portfolios` calls the full operations dashboard builder even though the route returns only compact portfolios detail.

## Files expected to change

- `src/ashare_evidence/operations.py`
- `tests/test_dashboard_operations_views.py`
- `tests/test_frontend_projections.py` or `tests/test_operations.py` only if existing coverage needs a focused assertion
- `plans/active/plan-20260613-operations-http-performance.md`
- `runs/archive/2026-06-13-operations-http-performance-W-001.md` after closeout

## Implementation steps

1. Inspect the existing full operations dashboard portfolio construction and compact detail response shape.
2. Add a lightweight portfolios detail builder that reuses the same portfolio payload helpers without building unrelated operations sections.
3. Keep `build_operations_detail(..., section="portfolios")` as the route-compatible entrypoint.
4. Add or adjust focused tests that would fail if the endpoint falls back to unrelated section builders or drops expected payload fields.
5. Run the W-001 acceptance gate.

## Acceptance criteria

- `section=portfolios` no longer depends on building unrelated operations dashboard sections.
- The returned portfolios detail envelope remains compatible with existing frontend projections.
- Focused operations/frontend tests pass.

## Acceptance Type

test_pass

## Acceptance Spec

cmd:python3 -m pytest -q tests/test_dashboard_operations_views.py tests/test_frontend_projections.py tests/test_operations.py

## Planned Evidence

- MiMo plan-review result for this run plan.
- Focused test command and exit code.
- Concise implementation summary naming the lightweight builder and compatibility tests.

## Actual Evidence

- Implemented `_build_operations_portfolios_detail` and shared `_load_operations_portfolios`.
- Added regression coverage that patches `build_operations_dashboard` to raise while `section=portfolios` still returns the same compact portfolio list as the full dashboard.
- Acceptance gate passed: `python3 -m pytest -q tests/test_dashboard_operations_views.py tests/test_frontend_projections.py tests/test_operations.py` exited 0 with `17 passed, 12 deselected, 6 subtests passed in 5.22s`.

## Risk and rollback notes

Primary risk is response-shape drift for frontend consumers. Rollback is reverting the lightweight builder path to the prior full dashboard call.

## Gate plan

Run `python3 -m pytest -q tests/test_dashboard_operations_views.py tests/test_frontend_projections.py tests/test_operations.py`.

## MiMo plan-review result

Passed. MiMo found no blocking or material drift from W-001. Minor notes were to record this review result and confirm during code review that reused helpers do not call unrelated section builders.

## Codex escalation plan-review result

Not required for W-001. This hop does not touch deployment behavior, credentials, schema, hooks, security boundaries, or irreversible governance state.

## Implementation summary

`build_operations_detail(section="portfolios")` now calls `_build_operations_portfolios_detail` instead of `build_operations_dashboard`. The lightweight path loads active symbols, market history, benchmark data, replay hit rate, and paper portfolios needed by `_portfolio_payload`, then returns the existing compact portfolios detail envelope.

## MiMo code-review result

Passed. MiMo found no blocking or material issues. Minor note: `_recommendation_replay_hit_rate` remains a future optimization candidate because it scans recommendation history, but it is still portfolio-field support rather than a full operations section build.

## Codex escalation code-review result

Not required for W-001 unless implementation scope expands into release/deployment behavior.

## Gate results

Passed: `python3 -m pytest -q tests/test_dashboard_operations_views.py tests/test_frontend_projections.py tests/test_operations.py` exited 0 with `17 passed, 12 deselected, 6 subtests passed in 5.22s`.

## Plan update summary

W-001 completed and plan evidence updated.

## Plan archive result

Not applicable for W-001; the full plan remains active until all work items complete.

## Archive and merge result

Archived for later commit. The branch will not merge until W-004 passes because the plan is being executed in full-plan mode.
