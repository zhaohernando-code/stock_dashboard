# Operations Dashboard Performance Governance Plan - 2026-06-04

## Status

`implemented_ds_reviewed_pending_merge_publish`

## Problem

`GET /dashboard/operations?sample_symbol=002475.SZ` is not an acceptable user or release-verification path.

Runtime baseline on 2026-06-04:

| Endpoint | Time | Size | Finding |
| --- | ---: | ---: | --- |
| `/dashboard/operations?sample_symbol=002475.SZ` | 82.21s | 4.7MB | Legacy all-in-one endpoint times out normal browser/proxy/verifier budgets. |
| `/dashboard/operations/summary?sample_symbol=002475.SZ` | 0.09s | 41KB | Summary projection path is healthy. |
| `/dashboard/operations/details?section=portfolios&sample_symbol=002475.SZ` | 12.17s | 4.25MB | Portfolio detail is too large for a tab-level request. |

In-process profiling with the runtime DB shows `build_operations_dashboard(..., include_simulation_workspace=True)` takes about 2.4s and emits about 5.0MB. The HTTP path is much slower than the in-process builder. Treat the residual cost as a combined effect of deep response-model validation/serialization, large ORM object graphs, and large payload transfer; do not assume SQL alone explains the timeout.

## Root Causes

1. `/dashboard/operations` mixes user read, maintenance tick, complete dashboard aggregation, simulation workspace, and release verifier payload capture in one synchronous endpoint.
2. Portfolio detail returns every portfolio's full `nav_history`. Runtime payload shows each portfolio has 1250 points; repeated tracks produce more than 4MB before response-model validation.
3. The release verifier fingerprints `/dashboard/operations`, forcing every publish to exercise the legacy worst-case endpoint.
4. One frontend simulation action refresh still calls `api.getOperationsDashboard(...)`, bypassing the summary/detail split.
5. The initial worktree measurement used the repo-local 35MB SQLite database; the live runtime database is 2.5GB with 2.27M `market_bars` rows. The runtime-sized DB exposed a second hot path: FastAPI's default response serialization/jsonable encoding of operations payloads added several seconds even after payload compaction.
6. Cached operations projections can contain legacy Python-style datetime strings (`YYYY-MM-DD HH:MM:SS...`), so the fast JSON response path must normalize both live `date`/`datetime` objects and existing cached date strings to ISO-style strings.

## Targets

| Path | Target |
| --- | --- |
| Default operations overview | `< 2s`, `< 250KB` |
| Portfolio details | `< 2s`, `< 500KB` |
| Release verifier API checks | No full `/dashboard/operations` call; use summary and bounded details |
| Legacy `/dashboard/operations` | No read-triggered maintenance tick; bounded response under verifier default timeout |

## Plan

| Step | Status | Action | Validation |
| --- | --- | --- | --- |
| 1 | completed | Review this plan with DeepSeek before code changes. | DeepSeek response captured in this doc. |
| 2 | completed | Add compact portfolio shaping for operations responses, sampling `nav_history` with first point, bounded intermediate points, and latest point while preserving existing fields. | Runtime `details?section=portfolios` under target; UI still renders portfolio tabs. |
| 3 | completed | Remove full-dashboard refresh from the frontend simulation action path; use summary plus affected details. | Static test prevents `getOperationsDashboard` hot-path usage. |
| 4 | completed | Change release verifier API endpoint set from full operations to `/dashboard/operations/summary` and bounded detail endpoints. | Verifier no longer requests `/dashboard/operations`. |
| 5 | completed | Make `/dashboard/operations` a compatibility read endpoint: no `run_operations_tick` inside GET and bounded payload by default. | Direct curl returns within target/default timeout. |
| 6 | in_progress | Run local tests/build, DeepSeek code review, then merge, push, publish, browser-verify, and remove task worktree. | DeepSeek code review passed after required fixes; merge/publish still pending. |
| 7 | completed | Add an operations-only fast JSON response path with ISO date normalization and a runtime DB covering index for `market_bars(timeframe, stock_id, observed_at)`. | Runtime-sized temporary API: summary `0.0085s`, portfolios `1.79s`, legacy full `2.33s`; DeepSeek P1 follow-up reported no blocker. |

## DeepSeek Plan Review

DeepSeek plan review completed in read-only mode.

Accepted findings:

- Root-cause direction is valid, but 82s should not be attributed solely to Pydantic validation; ORM eager loading, per-portfolio path calculations, and chained sub-builders must remain in the risk register.
- Release verifier must keep operations text audit meaningful after moving away from `/dashboard/operations`.
- `nav_history` compaction needs a deterministic sampling strategy that preserves chart anchors.
- `GET /dashboard/operations` should stop running `run_operations_tick(session)`.
- Tests must cover verifier endpoint selection, text-audit behavior, frontend avoidance of `getOperationsDashboard`, and bounded portfolio payload size.

DeepSeek code review:

- Initial code review found two required fixes: strengthen the `nav_history` compaction test to preserve critical extrema, and make the release verifier audit all bounded operations sections instead of only summary + portfolios.
- Both fixes were implemented.
- Follow-up DeepSeek review reported no blocker.
- Later runtime-sized testing found HTTP serialization still too slow on the live 2.5GB SQLite database. A second DeepSeek code review accepted the fast-response/index approach but raised one P1: `default=str` could return Python-style datetime strings instead of ISO 8601.
- The P1 was fixed with explicit date/datetime `.isoformat()` handling plus recursive normalization of cached datetime strings. DeepSeek follow-up reported: `P1 已解决，无阻塞合入问题。`

## Implementation Notes

Do not remove the existing response shape. The frontend and tests expect fields like `portfolios`, `nav_history`, `recent_orders`, `recommendation_replay`, and `simulation_workspace`; the fix should bound list sizes, not delete keys.

The release verifier still needs a user-visible operations text audit. It should audit the summary projection and any bounded detail text needed for required terms instead of forcing the full all-in-one payload. The verifier change must include a test proving required terms still exist and banned internal terms still fail when present in the bounded payload.

`nav_history` compaction policy: preserve the first point and last point, then evenly sample interior points up to a fixed budget. This keeps the line chart anchored across the full visible history instead of showing only the most recent window.

## Verification Log

Baseline:

- `/dashboard/operations?sample_symbol=002475.SZ`: `82.21s`, `4.7MB`.
- `/dashboard/operations/summary?sample_symbol=002475.SZ`: `0.09s`, `41KB`.
- `/dashboard/operations/details?section=portfolios&sample_symbol=002475.SZ`: `12.17s`, `4.25MB`.
- In-process full builder: `2.4s`, `5.0MB`.

Worktree implementation checks:

- In-process full builder after compacting portfolios: `2.15s`, `993KB`, max `nav_history` points `90`.
- In-process portfolio detail after compacting portfolios: `1.24s`, `473KB`, max `nav_history` points `90`.
- HTTP worktree backend `127.0.0.1:18002`:
  - `/dashboard/operations/summary?sample_symbol=002475.SZ`: `0.009s`, `41KB`.
  - `/dashboard/operations/details?section=portfolios&sample_symbol=002475.SZ`: `1.44s`, `449KB`.
  - `/dashboard/operations?sample_symbol=002475.SZ`: `1.96s`, `946KB`.
- Tests:
  - `PYTHONPATH=src python3 -m unittest tests.test_operations tests.test_release_verifier tests.test_frontend_shortpick_static`
  - `PYTHONPATH=src python3 -m pytest tests/test_frontend_projections.py`
  - `PYTHONPATH=src python3 -m unittest tests.test_dashboard_operations_views tests.test_operations tests.test_release_verifier tests.test_frontend_shortpick_static tests.test_frontend_mobile_static`
  - `PYTHONPATH=src python3 -m pytest tests/test_frontend_projections.py tests/test_multi_account_isolation.py tests/test_api_access.py`
  - `PYTHONPATH=src python3 -m ruff check src/ashare_evidence/operations.py src/ashare_evidence/api.py src/ashare_evidence/release_verifier.py tests/test_operations.py tests/test_release_verifier.py tests/test_frontend_projections.py tests/test_dashboard_operations_views.py`
  - `npm run build`

Runtime-sized follow-up checks after API serialization/index governance:

- Live runtime DB size: `2.5GB`; `market_bars`: `2,276,340` rows; repo-local DB was only `35MB`.
- Temporary worktree backend `127.0.0.1:18003` using the live runtime DB:
  - `/dashboard/operations/summary?sample_symbol=002475.SZ`: `0.0085s`, `43KB`.
  - `/dashboard/operations/details?section=portfolios&sample_symbol=002475.SZ`: `1.79s`, `476KB`.
  - `/dashboard/operations?sample_symbol=002475.SZ`: `2.33s`, `1009KB`.
  - `overview.generated_at` returned ISO-style `2026-06-04T19:39:21.075133+08:00`.
- Added `idx_market_bars_timeframe_stock_observed` and verified it exists on the live runtime DB after startup.
- Tests:
  - `PYTHONPATH=src python3 -m pytest tests/test_frontend_projections.py tests/test_frontend_shortpick_static.py tests/test_operations.py tests/test_release_verifier.py`
  - `PYTHONPATH=src python3 -m ruff check src/ashare_evidence/api.py src/ashare_evidence/db.py tests/test_frontend_projections.py tests/test_frontend_shortpick_static.py`
