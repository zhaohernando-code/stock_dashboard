# Shortpick Lab V2 Request Timeout Defect Investigation

## rawProblem

User report on 2026-06-16:

> 试验田v2的内容太容易超时了
> 一直提示“本次连接等待超过 10s，已等待约 10.0s”

## normalizedProblem

The `试验田v2` paper tracking page can show a 10-second connection wait error while loading the heavy `/shortpick-lab-v2/paper-tracking` read model.

## expectedBehavior

The v2 paper tracking page should tolerate a slow but valid account-curve read model request without surfacing a 10-second per-attempt error to the user.

## actualBehavior

`getShortpickV2PaperTracking()` used `operationsDashboardRequestBehavior`, which has a 10-second per-attempt cap. When the v2 paper read model is cold or cache-missed, the frontend aborts the request and displays:

`本次连接等待超过 10s，已等待约 10.0s。`

## reproductionEvidence

Runtime API timing on 2026-06-16:

- `/shortpick-lab-v2/paper-tracking`: about `6.4s` with warm runtime cache.
- `/shortpick-lab-v2/paper-tracking/summary`: about `0.01s`.
- `/shortpick-lab-v2/historical-replay?sample_limit=0`: about `0.02s`.

The full paper endpoint is a legitimate long read path because it generates replay display rows and account curves. Cold cache and restart paths can exceed the 10-second operations attempt cap.

## directCause

`frontend/src/api/shortpick.ts` used `operationsDashboardRequestBehavior` for `/shortpick-lab-v2/paper-tracking`. That behavior is suitable for compact dashboard endpoints, not for a heavy read model that can validly exceed 10 seconds on a cold cache.

## rootCauseChain

1. v2 paper tracking gained heavier account-curve display data.
2. The frontend kept using the operations dashboard request profile.
3. Closeout checks verified correctness and runtime rendering, but did not assert that long v2 paper reads use the long-running request profile.

## downstreamImpactScan

Checked areas:

- `frontend/src/api/shortpick.ts`: affected v2 paper tracking API behavior.
- `frontend/src/api/core.ts`: confirmed operations attempt cap is 10 seconds and long-running attempt cap is 60 seconds.
- `tests/test_frontend_shortpick_static.py`: lacked a guard for v2 paper request behavior.

Non-findings:

- v2 summary and historical replay endpoints are fast and do not need request-profile changes.

## remediations

| Type | Status | Remediation | Evidence Required |
|------|--------|-------------|-------------------|
| known_defect | fixed | Change v2 paper tracking API client to `longRunningRequestBehavior`. | Static test and frontend build pass. |
| process_gap | fixed | Add a static regression test that prevents the v2 paper tracking client from returning to operations dashboard behavior. | `test_shortpick_v2_tab_uses_separate_read_only_surface` asserts long-running behavior. |
| downstream_impact | fixed | Leave fast v2 historical replay and summary behavior unchanged. | Focused tests and runtime checks remain scoped to paper tracking. |

## confidence

High. The user-visible error string comes directly from the frontend request core when a request exceeds its per-attempt timeout, and the v2 paper client was using the 10-second operations attempt profile.

## openQuestions

None blocking. Backend performance can still be optimized separately, but this defect is the incorrect frontend request profile for a valid long read.
