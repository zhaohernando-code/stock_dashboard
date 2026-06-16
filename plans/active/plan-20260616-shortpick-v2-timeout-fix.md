---
schema_version: 1
plan_id: "plan-20260616-shortpick-v2-timeout-fix"
title: "Shortpick V2 Timeout Fix"
status: "done"
created_at: "2026-06-16"
source_request: "Fix 试验田v2 repeatedly showing 本次连接等待超过 10s while loading content."
target_repo: "/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260615-shortpick-v2-paper-tracking-display"
owner: "user"
review_rounds: 2
---

# Plan: Shortpick V2 Timeout Fix

## Compaction-Resistant Summary

Goal: stop `试验田v2` paper tracking from surfacing 10s per-attempt timeout errors for valid slow reads.
Hard scope: frontend request profile only; no strategy, data, or account-calculation changes.
Key dependency: `frontend/src/api/core.ts` request behavior profiles.
Major risk: hiding real backend hangs; mitigated by using existing 180s total long-running timeout, not infinite waiting.
Approval state: user reported a defect; implementation completed under problem closeout.

## Goal

Make the v2 paper tracking request tolerate cold-cache account-curve generation without showing the 10-second operations request error.

## Problem / Rationale

The v2 paper tracking endpoint can legitimately take longer than 10 seconds when generating replay rows and account curves. The frontend used the operations dashboard profile, whose per-attempt timeout is 10 seconds, causing user-visible aborts before the long read can finish.

## Source Requirement Coverage

| Source ID | Source Requirement | Plan Coverage | Coverage Status | Scope Decision | Evidence Required |
|-----------|--------------------|---------------|-----------------|----------------|-------------------|
| SRC-001 | Preserve and fix the user-visible 10s timeout complaint. | W-001,W-002 | covered | in-scope | Investigation records the raw problem; API client uses long-running behavior. |
| SRC-002 | Prevent regression to the 10s operations request profile. | W-003 | covered | in-scope | Static test asserts `getShortpickV2PaperTracking()` uses `longRunningRequestBehavior`. |
| SRC-003 | Keep unrelated v2 endpoints unchanged. | W-002,W-003 | covered | in-scope | Historical replay and summary behavior are not changed. |

## Production Path Fidelity

| Path ID | User / Production Path | Validation Path | Responsibility Owner | Test Setup / Bypass | Fidelity Status | Evidence Required |
|---------|------------------------|-----------------|----------------------|---------------------|-----------------|-------------------|
| PF-001 | User opens `试验田v2 -> 纸面追踪`, frontend calls `/shortpick-lab-v2/paper-tracking`. | Static client test plus frontend build; runtime publish verification before final closeout. | React API client | none | matches_product_path | Request client uses long-running behavior and runtime page still loads. |

## Scope

### In Scope

- Change only the v2 paper tracking frontend request behavior.
- Add a focused regression test.
- Record the defect and closeout evidence.

### Out of Scope

- Backend strategy changes.
- Account NAV formula changes.
- New cache architecture or async job queue.

## Assumptions and Dependencies

- `longRunningRequestBehavior` keeps a finite total timeout of 180 seconds and a per-attempt timeout of 60 seconds.
- The v2 paper full read endpoint is heavier than summary and historical replay.

## Work Items

| ID | Status | Order | Depends On | Task | Deliverable | Acceptance Type | Acceptance Spec | Evidence |
|----|--------|-------|------------|------|-------------|-----------------|-----------------|----------|
| W-001 | done | 1 | - | Record the defect investigation. | Investigation document. | file_exists | path:docs/investigations/SHORTPICK_LAB_V2_REQUEST_TIMEOUT_DEFECT_2026-06-16.md | Investigation document added. |
| W-002 | done | 2 | W-001 | Change v2 paper tracking request behavior. | Frontend API client change. | file_contains | path:frontend/src/api/shortpick.ts \| pattern:longRunningRequestBehavior | `getShortpickV2PaperTracking()` now uses `longRunningRequestBehavior`. |
| W-003 | done | 3 | W-002 | Add regression coverage. | Static frontend test. | test_pass | cmd:python3 -m pytest -q tests/test_frontend_shortpick_static.py::FrontendShortpickStaticTests::test_shortpick_v2_tab_uses_separate_read_only_surface | Focused static test passed. |
| W-004 | done | 4 | W-003 | Publish and served-route verify. | Runtime deployment and served page verification. | manual | manual:runtime page loads without the 10s operations request profile | `ASHARE_PUBLISH_REFRESH_MODE=skip bash scripts/publish-local-runtime.sh` passed; `verify-shortpick-v2-paper-tracking-display-runtime.sh` passed against `http://127.0.0.1:5173/?view=shortpick-v2&shortpickV2Tab=paper-tracking`. |

## Acceptance Criteria & Validation Gates

### Overall Acceptance Criteria

- `getShortpickV2PaperTracking()` uses the long-running request profile.
- Static tests prevent returning this endpoint to the 10-second operations attempt profile.
- Frontend build passes.
- Runtime served page still loads `试验田v2 -> 纸面追踪`.

### Validation Gates

- `python3 /Users/hernando_zhao/.codex/skills/reviewed-plan-generator/scripts/validate_plan.py plans/active/plan-20260616-shortpick-v2-timeout-fix.md`
- `python3 -m pytest -q tests/test_frontend_shortpick_static.py::FrontendShortpickStaticTests::test_shortpick_v2_tab_uses_separate_read_only_surface`
- `npm run build` in `frontend`
- `bash scripts/hooks/pre-push-stock-dashboard.sh`
- Publish and runtime verification after commit.

## Risks and Mitigations

- Risk: masking a truly stuck backend call.
  Mitigation: use the existing finite long-running request behavior, not an unlimited wait.

## Open Questions

- None blocking.

## Revision History

| Round | Date | Change | Author |
|-------|------|--------|--------|
| 0 | 2026-06-16 | Initial defect repair plan and implementation record. | Codex |

## External Review Log

| Round | Reviewer | Finding | Severity | Disposition | Reason | Affected IDs |
|-------|----------|---------|----------|-------------|--------|--------------|
| 1 | Xiaomi MiMo | No blocker or major; repair is narrow, does not alter summary or historical replay, and regression test guards the endpoint profile. | note | accepted | Confirms current scope. | W-002,W-003 |
| 2 | DeepSeek | No blocker or major; static test depends on function-order string splitting, but fails closed if order changes. | minor | accepted | Fragility is acceptable for this bounded static test and prevents silent regression. | W-003 |

## User Review Notes

- User reported repeated 10-second wait messages in `试验田v2`.
