---
schema_version: 1
plan_id: "plan-20260616-shortpick-v2-paper-performance"
title: "Shortpick V2 Paper Performance"
status: "done"
created_at: "2026-06-16"
source_request: "Reduce 试验田v2 paper tracking cold-load latency; 30s-level waiting is not logical for the visible data volume."
target_repo: "/Users/hernando_zhao/codex/worker-workspaces/stock_dashboard/20260615-shortpick-v2-paper-tracking-display"
owner: "user"
review_rounds: 2
---

# Plan: Shortpick V2 Paper Performance

## Compaction-Resistant Summary

Goal: reduce `试验田v2 / 纸面追踪` cold-load backend latency without changing strategy output.
Hard scope: backend read-model caching and runtime prewarm only; no strategy, capital, return, or UI wording changes.
Key dependency: v2 paper display derives rows from local daily market bars and H10 governance artifacts.
Major risk: stale cache after market data refresh; mitigate with cache key tied to latest 1d `MarketBar.observed_at` and display policy version.
Approval state: user reported the 30s-level wait as unacceptable and previously approved continuing without prompts.

## Goal

Make the v2 paper tracking endpoint avoid rebuilding the same display replay rows from hundreds of thousands of daily bars after service restart when market data and policy inputs have not changed.

## Problem / Rationale

Profiling showed the visible payload is small, but cold construction loads about 313k daily market-bar rows to rebuild 54 replay display rows and two account curves. Existing in-memory caching makes the second same-process request fast, but service restart or publish loses that cache and pushes the cold-load cost back to the first user.

## Source Requirement Coverage

| Source ID | Source Requirement | Plan Coverage | Coverage Status | Scope Decision | Evidence Required |
|-----------|--------------------|---------------|-----------------|----------------|-------------------|
| SRC-001 | The v2 paper page must not routinely require 30s-level waiting for a small visible result set. | W-001,W-002,W-004 | covered | in-scope | Profiling evidence plus runtime API timing after fix and runtime prewarm. |
| SRC-002 | The fix must not change strategy, buy/sell, return, or display semantics. | W-002,W-003 | covered | in-scope | Regression tests compare existing display behavior and assert cache hit bypasses only rebuild work. |
| SRC-003 | Cache must invalidate when market data changes. | W-002,W-003 | covered | in-scope | Cache key includes latest daily `MarketBar.observed_at`, active config IDs, and display cache version. |

## Production Path Fidelity

| Path ID | User / Production Path | Validation Path | Responsibility Owner | Test Setup / Bypass | Fidelity Status | Evidence Required |
|---------|------------------------|-----------------|----------------------|---------------------|-----------------|-------------------|
| PF-001 | Browser opens `试验田v2 -> 纸面追踪`; backend serves `/shortpick-lab-v2/paper-tracking`. | Runtime publish plus served API/browser verifier against local runtime. | FastAPI read model | none | matches_product_path | Served API and browser verification pass after publish. |
| PF-002 | Backend process restarts and first paper request should reuse valid persisted display cache when inputs match. | Targeted pytest with temp cache path and failing market-data loader on second call. | v2 read model cache | controlled temp database and temp cache path; production owner still exercised through read model | controlled_simulation | Test proves second process-equivalent cache hit avoids market loader and preserves display rows. |

## Scope

### In Scope

- Add a persisted v2 paper display cache for replay rows, coverage, and account curves.
- Key the cache by database identity, active config IDs, latest daily observed timestamp, and display policy version.
- Prewarm the cache during publish and scheduled refresh so users do not trigger the cold rebuild path.
- Add focused tests and runtime timing evidence.

### Out of Scope

- Changing strategy selection, buy amount rules, account curve math, or UI layout.
- Replacing the broader market-data loader used by other research paths.

## Assumptions and Dependencies

- The display replay rows are deterministic for a given daily market-data snapshot and active H10 paper config set.
- Output artifacts under `output/` are acceptable for local runtime read-model cache files.

## Work Items

| ID | Status | Order | Depends On | Task | Deliverable | Acceptance Type | Acceptance Spec | Evidence |
|----|--------|-------|------------|------|-------------|-----------------|-----------------|----------|
| W-001 | done | 1 | - | Profile cold v2 paper tracking load. | Timing evidence. | manual | manual:identify cold-load hotspot | Cold profile: about 313k rows loaded; market series loader about 5.25s of 6.49-8.10s cold build; same-process warm request about 0.15s. |
| W-002 | done | 2 | W-001 | Implement persisted read-model cache and runtime prewarm hooks. | Backend cache implementation and prewarm scripts. | file_contains | path:src/ashare_evidence/shortpick_v2_read_model.py \| pattern:SHORTPICK_V2_PAPER_DISPLAY_CACHE_VERSION | Added persisted cache identity, read, and atomic write helpers keyed by DB identity, active configs, latest daily observed timestamp, and display policy version; added publish and scheduled-refresh prewarm hooks. |
| W-003 | done | 3 | W-002 | Add regression coverage for persistent cache hit and invalidation key. | Targeted pytest. | test_pass | cmd:python3 -m pytest -q tests/test_shortpick_v2_read_model_api.py::test_shortpick_v2_paper_display_uses_persistent_cache_after_cold_build | Passed: targeted cache-hit test plus full v2 read-model suite; added miss-on-market-data-change, corrupt-cache fallback, and script prewarm wiring coverage after MiMo review. |
| W-004 | done | 4 | W-003 | Validate, publish, and verify served route performance. | Runtime verification evidence. | manual | manual:served `/shortpick-lab-v2/paper-tracking` returns from persisted cache quickly after restart | Final publish prewarm succeeded in 7.578s with 54 replay rows and 2 account curves; backend restart first v2 paper request returned in 1.186667s; served API/browser verifier passed. |

## Acceptance Criteria & Validation Gates

### Overall Acceptance Criteria

- First cold build writes a persisted cache file.
- A later process with matching latest market data can serve the paper display from persisted cache without reloading the full market window.
- Cache mismatch falls back to normal rebuild instead of returning stale data.
- Publish and scheduled refresh prewarm the cache so normal users do not trigger the cold rebuild.
- Served runtime v2 paper page still renders paper and historical replay tabs.

### Validation Gates

- `python3 /Users/hernando_zhao/.codex/skills/reviewed-plan-generator/scripts/validate_plan.py plans/active/plan-20260616-shortpick-v2-paper-performance.md`
- `python3 -m pytest -q tests/test_shortpick_v2_read_model_api.py::test_shortpick_v2_paper_display_uses_persistent_cache_after_cold_build`
- `python3 -m pytest -q tests/test_shortpick_v2_read_model_api.py::test_shortpick_v2_read_api_full_paper_tracking_returns_display_rows tests/test_frontend_shortpick_static.py::FrontendShortpickStaticTests::test_shortpick_v2_tab_uses_separate_read_only_surface`
- `npm run build` in `frontend`
- `bash scripts/hooks/pre-push-stock-dashboard.sh`
- Publish and served route verification.

## Risks and Mitigations

- Risk: stale display rows after data refresh.
  Mitigation: cache key includes latest daily observed timestamp and active config IDs.
- Risk: corrupt cache file blocks endpoint.
  Mitigation: cache read failures are ignored and normal rebuild is used.
- Risk: cache write failure hides a deployment issue.
  Mitigation: endpoint still serves rebuilt data; investigation record documents performance fallback.

## Open Questions

- None blocking.

## Revision History

| Round | Date | Change | Author |
|-------|------|--------|--------|
| 0 | 2026-06-16 | Initial performance remediation plan from profiling evidence. | Codex |

## External Review Log

| Round | Reviewer | Finding | Severity | Disposition | Reason | Affected IDs |
|-------|----------|---------|----------|-------------|--------|--------------|
| 1 | Xiaomi MiMo | No blocker or major. Recommended tests for cache invalidation when `latest_observed_at` changes and corrupt-cache fallback. | minor | resolved | Added `test_shortpick_v2_paper_display_persistent_cache_misses_when_market_data_changes` and `test_shortpick_v2_paper_display_ignores_corrupt_persistent_cache`; `tests/test_shortpick_v2_read_model_api.py` now passes 28 tests. | W-003 |
| 2 | Xiaomi MiMo | Publish prewarm pipeline could hide failure without pipefail; scheduled shortpick daily-cycle prewarm warning position lacked explicit static coverage. | minor | resolved | Pipeline concern rejected because `publish-local-runtime.sh` already uses `set -euo pipefail`; added static assertion for shortpick daily-cycle prewarm warning ordering. | W-002,W-003 |

## User Review Notes

- User challenged the prior 30s-level wait as illogical for the visible v2 data volume.
