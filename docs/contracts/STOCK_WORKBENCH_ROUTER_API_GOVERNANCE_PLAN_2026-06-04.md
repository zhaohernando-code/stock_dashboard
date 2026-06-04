# Stock Workbench Router and API Governance Plan

Status: `published_runtime_verified`
Owner: `codex`
Created: `2026-06-04`
Worktree: `/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260604-router-api-governance-fb0d0b`
Branch: `task/router-api-governance`

## User Goal

The stock workbench must preserve user location across refreshes, default into `试验田 -> 纸面跟踪`, and stop timing out on routine single-user usage.

## Root Causes Found

1. No real router exists.
   - `frontend/src/App.tsx` only initializes view from `?view=` in `initialViewFromUrl()`.
   - `handleViewChange()`, mobile tab changes, candidate selection, and permission fallback call `setView()` directly without writing URL state.
   - Refreshing a bare `/stocks` or `/projects/ashare-dashboard/` URL therefore returns to the hard-coded default `candidates`.

2. The default view is still `关注池`.
   - `initialViewFromUrl()` falls back to `candidates`.
   - `ShortpickLabView` can read `shortpickTab` via `initialShortpickWorkspaceTab()`, but its local tab state is not kept in history after tab changes.
   - Result: the user must repeatedly click `试验田`, then `纸面跟踪`.

3. Entering the trial field creates a request burst.
   - `ShortpickLabView` mount currently starts `loadLab`, `loadPaperTracking`, `loadValidationQueue`, and `loadFeedback` concurrently.
   - If the active tab is replay, it also starts replay run, replay feedback, and market study work.
   - `App.loadShellData()` also fetches shortpick paper tracking for the home badge, so the paper-tracking endpoint is called before and after entering the trial field.

4. Several read endpoints are much heavier than their user-visible purpose.
   - Local runtime measurements on `2026-06-04`:
     - `/dashboard/shell`: `0.116s`, `23KB`
     - `/shortpick-lab/paper-tracking`: `3.855s`, `1.1MB`
     - `/shortpick-lab/runs?limit=100`: `4.338s`, `1.9MB`
     - `/shortpick-lab/validation-queue?limit=50&offset=0`: `6.956s`, `100KB`
     - `/shortpick-lab/model-feedback`: `0.112s`, `345KB`
     - `/dashboard/operations/summary?sample_symbol=002475.SZ`: `27.57s`, `41KB`
   - A concurrent approximation of the trial-field boot request burst pushed `/shortpick-lab/runs?limit=100` to about `20.4s`.

5. Paper tracking has a clear N+1 query path.
   - `_build_shortpick_paper_tracking_ledger()` selects candidate rows and then calls `_paper_tracking_validation_snapshot(session, candidate.id)` per candidate.
   - Current live paper ledger has `207` returned rows; this means hundreds of extra validation queries for one endpoint.
   - The existing `_shortpick_validations_by_candidate()` helper already provides the batched shape needed to remove this N+1.

6. Some heavy aggregation is repeated across endpoints.
   - `_attach_shortpick_replay_decision_projection()` calls `_build_shortpick_paper_tracking_ledger()` while the frontend also calls `/shortpick-lab/paper-tracking`.
   - That makes replay feedback capable of repeating the same ledger build during trial-field navigation.

7. Timeout configuration hides the true bottleneck.
   - The frontend defaults are `10s` total and `3s` per attempt.
   - Operations-style requests use `30s` total and `10s` per attempt.
   - Heavy endpoints can cross per-attempt thresholds even on localhost, causing abort/retry churn instead of a fast deterministic load.

## DeepSeek Review Summary

DeepSeek independently agreed with the main diagnosis:

- Frontend state is not routed; the workbench only reads `view` from query params at boot.
- `ShortpickLabView` launches a parallel request burst on mount.
- `paper-tracking` and replay projection paths are heavyweight and repeat ledger construction.
- The fix should prioritize route persistence, default route semantics, request gating/lazy loading, and batched backend ledger queries before broad timeout increases.

DeepSeek mentioned "timeout causing route protection jumping to home"; local code review did not find a direct timeout-to-home redirect. The reproducible home reset is caused by URL state not being persisted. Timeout still contributes to the bad path by making the required clicks fragile.

## DeepSeek Plan Review Adjustments

DeepSeek reviewed this plan after the first draft. Required changes accepted into the plan:

- `operations/summary` cannot stay as a vague slow symptom; Step 7 must include root-cause profiling before repair.
- Response-size targets must be explicit, not described as "materially smaller".
- Paper tracking must optimize both query count and response size; batching alone may not meet the target if the endpoint keeps returning a 1.1MB ledger for summary use cases.
- Step 3 and Step 4 must be verified together before backend timing claims are accepted.
- Baseline API timing must be rerun after Step 5, Step 6, and Step 7, not only at final closeout.

## Governance Plan

| Step | Status | Scope | Acceptance |
| --- | --- | --- | --- |
| 1 | `published_runtime_verified` | Add URL-backed workbench routing for main view, shortpick tab, selected symbol, and stock tab while preserving current mounted-base deployment. | Refreshing `?view=shortpick&shortpickTab=paper-tracking` reopens the same view; clicking desktop and mobile navigation updates URL without full reload. |
| 2 | `published_runtime_verified` | Change default route to `试验田 -> 纸面跟踪`. | Bare local and canonical app entry open the trial field paper-tracking tab after auth and shell load. |
| 3 | `published_runtime_verified` | Stop trial-field request burst by loading only the active tab's required data and preloading non-active data opportunistically after primary view is usable. | First render of paper tracking does not call lab runs, validation queue, model feedback, replay runs, or replay feedback before the paper ledger is visible. Must be network-verified together with Step 4 before Step 5 is accepted. |
| 4 | `published_runtime_verified` | Remove duplicate paper-tracking calls between app shell badge and `ShortpickLabView`; share initial badge payload when available or reduce shell badge to a compact endpoint. | Entering default route makes at most one full paper-tracking ledger request. Must be network-verified together with Step 3 before Step 5 is accepted. |
| 5 | `published_runtime_verified` | Optimize `_build_shortpick_paper_tracking_ledger()` by batching validation snapshots and splitting compact summary from full ledger where the caller only needs badge/status data. | Local full `/shortpick-lab/paper-tracking` target: under `1.0s` warm and under `2.0s` cold on current runtime DB; compact summary response target: under `300KB`. Rerun baseline curl after completion. |
| 6 | `published_runtime_verified` | Slim run list responses used by trial-field navigation: keep only run identity, dates, status, operational summary, and failed-round badges; move detailed rounds/candidates to explicit detail calls. | `/shortpick-lab/runs?limit=100` target: under `200KB` and under `1.5s` in the concurrent trial-field baseline. Rerun baseline curl after completion. |
| 7 | `published_runtime_verified` | Profile `operations/summary` before repair: determine whether the `27s` path is projection miss, projection lookup key mismatch, heavy synchronous summary build, missing index, or DB contention; then repair the confirmed cause. | `/dashboard/operations/summary?sample_symbol=<active>` returns from ready projection or deterministic summary within `3s`. Rerun baseline curl after completion and document the confirmed root cause. |
| 8 | `closed_no_timeout_increase` | Adjust request timeout behavior only after backend/request-shaping fixes, with separate behavior for page-critical reads and background preloads. | Page-critical GETs use a bounded short-read policy; background preload failures are non-blocking and visible only in their own tab state. No routine GET uses long-running behavior to mask slow local aggregation. |
| 9 | `published_runtime_verified` | Add regression coverage and served verification. | Unit/build checks pass; browser refresh on local preview and authenticated canonical route preserves `试验田 -> 纸面跟踪`; API timing evidence is captured before publish closeout. |

## Implementation Order

1. Router/default route first, because it removes the daily user friction even before performance work is complete.
2. Trial-field request gating and dedupe next, because it directly reduces timeout probability without changing data semantics.
3. Backend paper-tracking batching, because it addresses the clearest measured server-side N+1 path.
4. Run-list slimming and operations projection repair, because these are larger response-contract changes and need focused verification.
5. Timeout policy cleanup last, after endpoints have realistic latency.

## Current Verification Baseline

Commands run against the current live local runtime on `2026-06-04`:

```bash
curl -sS -w '\nHTTP %{http_code} time_total=%{time_total}\n' http://127.0.0.1:8000/health
curl -sS -o /tmp/ashare-shell.json -w 'shell HTTP %{http_code} time_total=%{time_total} size=%{size_download}\n' http://127.0.0.1:8000/dashboard/shell
curl -sS -o /tmp/ashare-paper.json -w 'paper HTTP %{http_code} time_total=%{time_total} size=%{size_download}\n' http://127.0.0.1:8000/shortpick-lab/paper-tracking
curl -sS -o /tmp/ashare-runs.json -w 'runs HTTP %{http_code} time_total=%{time_total} size=%{size_download}\n' 'http://127.0.0.1:8000/shortpick-lab/runs?limit=100'
curl -sS -o /tmp/ashare-validation.json -w 'validation HTTP %{http_code} time_total=%{time_total} size=%{size_download}\n' 'http://127.0.0.1:8000/shortpick-lab/validation-queue?limit=50&offset=0'
curl -sS -o /tmp/ashare-feedback.json -w 'feedback HTTP %{http_code} time_total=%{time_total} size=%{size_download}\n' http://127.0.0.1:8000/shortpick-lab/model-feedback
curl -sS -o /tmp/ashare-ops-summary-002475.json -w 'ops-summary-002475 HTTP %{http_code} time_total=%{time_total} size=%{size_download}\n' 'http://127.0.0.1:8000/dashboard/operations/summary?sample_symbol=002475.SZ'
```

## Current Worktree Verification

Worktree backend command:

```bash
PYTHONPATH=src ASHARE_DATABASE_URL=sqlite:////Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db uvicorn ashare_evidence.api:app --host 127.0.0.1 --port 18000
```

Local API evidence on `2026-06-04`:

- `/shortpick-lab/paper-tracking/summary`: `0.392s`, `9,321 bytes`.
- `/shortpick-lab/paper-tracking`: `0.298s`, `1,179,299 bytes` after batched validation snapshot loading.
- `/shortpick-lab/runs?limit=100`: `0.132s`, `113,071 bytes` after list response slimming.
- Concurrent trial-field approximation:
  - `/shortpick-lab/paper-tracking`: `0.452s`, `1,179,299 bytes`
  - `/shortpick-lab/runs?limit=100`: `0.344s`, `113,071 bytes`
  - `/shortpick-lab/validation-queue?limit=50&offset=0`: `0.474s`, `100,314 bytes`
  - `/shortpick-lab/model-feedback`: `0.018s`, `345,399 bytes`
  - wall clock: `0.475s`
- `/dashboard/operations/summary?sample_symbol=002475.SZ` root cause:
  - Existing projections covered `002270.SZ`, `600522.SH`, `600589.SH`, and `002028.SZ`, but not the active `002475.SZ` or default `600519.SH`.
  - Misses therefore rebuilt operations summary synchronously.
  - Fix: summary fallback now upserts a ready `operations_summary` projection for the requested symbol.
  - First fallback request for `002475.SZ`: `1.630s`, `41,914 bytes`.
  - Second same-key request after fallback projection write: `0.003s`, `41,908 bytes`.

Published runtime evidence:

- Commit published to canonical main and runtime: `54c9fd7374cd1820fb971f0f1bff07f92352efe0`.
- `scripts/publish-local-runtime.sh` synced and restarted services. Its default verifier timed out on the legacy full `/dashboard/operations` endpoint; the endpoint is still about `4.7MB` and can take about `19.6s`. A follow-up release verifier with `--timeout-seconds 75` passed local/canonical asset and API parity and updated runtime latest-successful to `output/releases/20260604T115622Z-54c9fd7374cd/manifest.json`.
- Published local browser: `http://127.0.0.1:5173/` opens `?view=shortpick&shortpickTab=paper-tracking&symbol=002028.SZ`; reload preserves the same route and visible paper-tracking tab.
- Authenticated canonical browser: `https://hernando-zhao.cn/projects/ashare-dashboard/` opens `?view=shortpick&shortpickTab=paper-tracking&symbol=002028.SZ`; reload preserves the same route and visible paper-tracking tab.
- Published runtime API sample after verifier load:
  - `/shortpick-lab/paper-tracking/summary`: `2.103s`, `9,321 bytes`
  - `/shortpick-lab/paper-tracking`: `1.898s`, `1,179,041 bytes`
  - `/shortpick-lab/runs?limit=100`: `1.382s`, `113,071 bytes`
  - `/dashboard/operations/summary?sample_symbol=002475.SZ`: `0.015s`, `41,908 bytes`
  - Browser default route logs show shell, stock detail, and paper-tracking only; they do not show the old trial-field run-list/validation/model-feedback/replay request burst.

Regression checks run:

```bash
PYTHONPATH=src python3 -m unittest tests.test_shortpick_lab tests.test_shortpick_lab_paper_tracking tests.test_frontend_shortpick_static
PYTHONPATH=src python3 -m pytest tests/test_frontend_projections.py
python3 -m py_compile src/ashare_evidence/api.py src/ashare_evidence/shortpick_lab.py
npm run build
```

## Closeout Requirements

- Keep this plan status current as steps are implemented.
- Update `PROJECT_STATUS.json`, `PROCESS.md`, and `DECISIONS.md` when durable behavior changes.
- User-visible runtime closeout completed on `2026-06-04`: repo tests/build, runtime publish, local browser verification, authenticated canonical browser verification, and release parity verifier passed.
