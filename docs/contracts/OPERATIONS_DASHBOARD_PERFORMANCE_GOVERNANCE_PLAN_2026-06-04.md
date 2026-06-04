# Operations Dashboard Performance Governance Plan - 2026-06-04

## Status

`startup_prewarm_backgrounding_in_progress`

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
7. After publishing the serialization/index fix, the LaunchAgent HTTP path still showed unstable `details?section=portfolios` latency (`12s+`) while the same runtime code and DB were `~1.9s` in-process. The paper-tracking hot path therefore needs a short in-process response cache plus startup prewarm, not only faster serialization.
8. Legacy `/dashboard/operations` still included `simulation_workspace`, whose builder can write account presence and wait on SQLite locks. The compatibility endpoint must stay read-only/lightweight; simulation workspace belongs to `/dashboard/operations/details?section=simulation_workspace`.
9. After publishing `dbc3dc1`, the actual user runtime made the priority paths fast (`summary 0.016s`, `portfolios 0.019s`, legacy `0.021s` with `simulation_workspace=null`), but release verification still timed out because non-priority bounded detail sections reused `build_operations_dashboard()` and paid the full dashboard rebuild cost for tiny section payloads.
10. After publishing `dd1d6b3`, backend reached ASGI startup but did not bind `/health` before the publish health deadline. The remaining blocker is synchronous operations response prewarm inside FastAPI lifespan: cache warmup should be best-effort and must not block service startup.

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
| 8 | completed | Add a 60s operations response cache and startup prewarm for `details=portfolios` plus lightweight legacy operations, keyed by target login and shared across sample symbols for sample-independent compatibility payloads. | Runtime-sized temporary API first portfolios request `0.0025s`; DeepSeek cache review reported no blocker. |
| 9 | completed | Keep legacy `/dashboard/operations` read-only by excluding inline simulation workspace; load simulation workspace only through its dedicated details/projection path. | Test asserts legacy response has `simulation_workspace: null`; avoids account-presence writes in legacy GET/prewarm. |
| 10 | completed | Split `build_operations_detail()` into section-specific builders for `replay`, `manual_queue`, `factor_observation`, `sector_exposure`, `policy_governance`, and `simulation_workspace`, so small bounded detail endpoints do not rebuild portfolios, stock dashboard measurements, data quality, and unrelated sections. | Runtime-sized temporary API: replay `0.787s`, manual_queue `0.088s`, factor `0.034s`, sector `0.055s`, policy `0.024s`; DeepSeek plan and code reviews found no blockers. |
| 11 | in_progress | Move operations response prewarm out of the blocking ASGI startup path. Default prewarm mode becomes background best-effort; tests can opt into `ASHARE_OPERATIONS_RESPONSE_PREWARM_MODE=sync` to keep deterministic cache assertions. | Backend `/health` becomes available before prewarm completion; publish health check no longer times out. |

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
- A final DeepSeek review of the response cache/prewarm design found no blockers: the cache is target-login scoped, hot compatibility payloads intentionally ignore `sample_symbol`, TTL is 60s, startup prewarm is disableable through `ASHARE_DISABLE_OPERATIONS_RESPONSE_PREWARM`, and the new TestClient lifespan tests verify the prewarmed cache path.
- A follow-up is now required because the first publish of `dbc3dc1` proved the priority user paths are fast, but release verifier still exercises other bounded details sections. Those sections must become true bounded section builders before the release can be considered published.
- DeepSeek plan review for Step 10 found no blocking issue: response wrappers and data keys remain compatible, release verifier fingerprints ignore `generated_at`, text audit still merges the same bounded data keys, and endpoint URLs do not change. It called out one implementation detail: `manual_queue` can use a simpler fallback symbol when the requested sample is not active.
- DeepSeek code review for Step 10 found no blocking issue: non-portfolio sections do not call `build_operations_dashboard()`, each section only calls its own domain builder, response keys remain compatible, and there is no eager execution risk. It noted a non-blocking defensive dead-code check in the portfolios branch.

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
- Runtime-sized cache/prewarm follow-up:
  - Temporary worktree backend startup prewarmed the portfolios response before health became available.
  - First `/dashboard/operations/details?section=portfolios&sample_symbol=002475.SZ`: `0.0025s`, `476KB`.
  - `/dashboard/operations/summary?sample_symbol=002475.SZ`: `0.0051s`, `43KB`.
  - `/dashboard/operations?sample_symbol=002475.SZ`: `2.40s`, `1009KB`.
  - `/dashboard/operations/details?section=portfolios&sample_symbol=600519.SH`: `0.0021s`, proving the sample-independent portfolios cache key works.
- Tests:
  - `PYTHONPATH=src python3 -m pytest tests/test_frontend_projections.py tests/test_frontend_shortpick_static.py tests/test_operations.py tests/test_release_verifier.py` (`28 passed` after adding cache coverage)
  - `PYTHONPATH=src python3 -m ruff check src/ashare_evidence/api.py src/ashare_evidence/db.py tests/test_frontend_projections.py tests/test_frontend_shortpick_static.py`

Published-runtime follow-up after `dbc3dc1`:

- `scripts/publish-local-runtime.sh` built and synced the runtime, backend/frontend health checks passed, then release verifier timed out on local operations bounded details.
- Actual runtime priority paths:
  - `/dashboard/operations/summary?sample_symbol=002475.SZ`: `0.016s`, `43KB`.
  - `/dashboard/operations/details?section=portfolios&sample_symbol=002475.SZ`: `0.019s`, `476KB`.
  - `/dashboard/operations?sample_symbol=002475.SZ`: `0.021s`, `556KB`, `simulation_workspace=null`.
- Remaining slow bounded details:
  - `/dashboard/operations/details?section=replay&sample_symbol=002475.SZ`: `11.21s`, `6KB`.
  - `/dashboard/operations/details?section=manual_queue&sample_symbol=002475.SZ`: `10.88s`, `29KB`.
  - `/dashboard/operations/details?section=factor_observation&sample_symbol=002475.SZ`: `10.42s`, `2KB`.
  - `/dashboard/operations/details?section=sector_exposure&sample_symbol=002475.SZ`: `10.39s`, `714B`.
  - `/dashboard/operations/details?section=policy_governance&sample_symbol=002475.SZ`: `10.25s`, `5KB`.
  - `/dashboard/operations/details?section=simulation_workspace&sample_symbol=002475.SZ`: `0.054s`, `418KB`.

Worktree Step 10 temporary API with live runtime DB, prewarm disabled:

- `/dashboard/operations/details?section=portfolios&sample_symbol=002475.SZ`: `1.960s`, `476KB` uncached.
- `/dashboard/operations/details?section=replay&sample_symbol=002475.SZ`: `0.787s`, `6KB`.
- `/dashboard/operations/details?section=manual_queue&sample_symbol=002475.SZ`: `0.088s`, `64KB`.
- `/dashboard/operations/details?section=factor_observation&sample_symbol=002475.SZ`: `0.034s`, `2KB`.
- `/dashboard/operations/details?section=sector_exposure&sample_symbol=002475.SZ`: `0.055s`, `714B`.
- `/dashboard/operations/details?section=policy_governance&sample_symbol=002475.SZ`: `0.024s`, `5KB`.
- `/dashboard/operations/details?section=simulation_workspace&sample_symbol=002475.SZ`: `0.013s`, `418KB`.
- `/dashboard/operations/summary?sample_symbol=002475.SZ`: `0.003s`, `43KB`.
- `/dashboard/operations?sample_symbol=002475.SZ`: `1.519s`, `591KB`, `simulation_workspace=null`.
- Tests:
  - `PYTHONPATH=src python3 -m pytest tests/test_operations.py tests/test_frontend_projections.py tests/test_release_verifier.py` (`25 passed`)
  - `PYTHONPATH=src python3 -m ruff check src/ashare_evidence/operations.py tests/test_operations.py`

Published-runtime follow-up after `dd1d6b3`:

- `scripts/publish-local-runtime.sh` built and synced the runtime, but timed out waiting for `http://127.0.0.1:8000/health`.
- Backend log reached `Started server process` and `Waiting for application startup`; it had not reached `Application startup complete`.
- Runtime DB checkpoint was not blocked (`PRAGMA wal_checkpoint(PASSIVE)` returned `0|30|30`).
- Fix: schedule `prewarm_operations_response_cache()` on a daemon thread from lifespan startup, while keeping `ASHARE_OPERATIONS_RESPONSE_PREWARM_MODE=sync` available for deterministic TestClient cache tests.
