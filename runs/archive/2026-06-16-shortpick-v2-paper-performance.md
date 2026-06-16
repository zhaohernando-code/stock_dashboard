# Run: Shortpick V2 Paper Performance

## Run ID

2026-06-16-shortpick-v2-paper-performance

## Plan path

`plans/active/plan-20260616-shortpick-v2-paper-performance.md`

## Hop ID

W-001 through W-004

## Work item ID

W-001 through W-004

## Goal

Reduce `试验田v2 / 纸面追踪` cold-load latency without changing strategy output, replay rows, account curves, or UI semantics. Ensure publish and scheduled refresh prewarm the cache so users do not trigger the cold rebuild.

## Non-goals

- No strategy selection changes.
- No buy amount, exit, return, or account NAV formula changes.
- No frontend layout changes.

## Plan evidence

Cold profiling showed the endpoint returns a small display payload but rebuilds it from about 313k market-bar rows. Same-process memory cache already made repeated calls fast, but restart/publish discarded that cache.

## Source coverage evidence

- SRC-001: Persistent cache targets the 30s-level cold wait concern.
- SRC-002: Output semantics are preserved by caching rows/coverage/account curves after normal construction.
- SRC-003: Cache identity includes latest daily market observation timestamp and display policy version.

## Production path fidelity evidence

- PF-001 will be validated by runtime publish and served route verification.
- PF-002 is covered by a targeted pytest using a temp SQLite database and temp cache path.

## Files expected to change

- `src/ashare_evidence/shortpick_v2_read_model.py`
- `scripts/prewarm-shortpick-v2-paper-cache.sh`
- `scripts/publish-local-runtime.sh`
- `scripts/run-scheduled-refresh.sh`
- `tests/test_shortpick_v2_read_model_api.py`
- `tests/test_publish_script_static.py`
- `tests/test_scheduled_refresh_static.py`
- `docs/investigations/SHORTPICK_LAB_V2_PAPER_PERFORMANCE_DEFECT_2026-06-16.md`
- `plans/active/plan-20260616-shortpick-v2-paper-performance.md`

## Implementation steps

1. Add cache version and cache path selection.
2. Read persisted cache after memory-cache miss and before market-window rebuild.
3. Write persisted cache after successful rebuild.
4. Add pytest proving persistent cache hit bypasses market-window loader.
5. Add publish and scheduled-refresh prewarm hooks.
6. Validate with runtime data timing and served route after publish.

## Acceptance criteria

- Persistent cache hit must not call `_load_daily_series_for_replay_window`.
- Cached display rows, coverage, and account curves must match the normal build result.
- Publish and scheduled refresh should prewarm the cache after restart/data refresh.
- Runtime page must still render paper and historical replay tabs.

## Planned Evidence

- Plan validation.
- Targeted pytest.
- Frontend build.
- Project pre-push gate.
- Runtime publish.
- Served route verification.

## Actual Evidence

- Plan validation: passed.
- `tests/test_shortpick_v2_read_model_api.py`: 28 passed.
- `tests/test_scheduled_refresh_static.py tests/test_publish_script_static.py tests/test_shortpick_v2_read_model_api.py`: 51 passed.
- Existing display route/static tests: passed.
- `npm run build`: passed.
- Runtime-data process timing before publish: first process 6.125s, second process 0.233s.
- Served runtime timing: no persisted cache first request 42.35s, cache-present backend restart first request 1.20s.
- Final publish prewarm: 7.578s, 54 replay rows, 2 account curves.
- Final backend restart first v2 paper request with persisted cache: 1.186667s.
- Served API/browser verifier: passed for paper and historical replay tabs.

## Risk and rollback notes

The cache is a derived read-model cache. If it is corrupt or stale, the code ignores it and rebuilds from the database. Rollback is safe by reverting the cache read/write helpers.

## Gate plan

Run targeted tests, frontend build, full pre-push gate, publish runtime, and served route verification.

## MiMo plan-review result

Round 1 passed with no blocker or major. MiMo raised two minor test-coverage findings: cache invalidation on latest market data change and corrupt-cache fallback.

Round 2 passed with no blocker or major. MiMo raised one invalid minor about publish pipe failure handling that is already covered by `set -euo pipefail`, and one accepted minor requesting explicit static coverage for the shortpick daily-cycle prewarm warning.

## Codex escalation plan-review result

Not required.

## Implementation summary

Added persisted replay display cache keyed by DB identity, active paper config IDs, latest daily observed timestamp, and display policy version. Default cache path follows the SQLite database directory; tests therefore write under `tmp_path`, runtime writes under runtime `data/`. Added a prewarm script and wired it into publish and scheduled refresh.

## MiMo code-review result

Round 1 minor findings resolved by adding `test_shortpick_v2_paper_display_persistent_cache_misses_when_market_data_changes` and `test_shortpick_v2_paper_display_ignores_corrupt_persistent_cache`.

Round 2 accepted minor resolved by adding a static assertion for the shortpick daily-cycle prewarm warning ordering. The publish pipeline concern was rejected because `publish-local-runtime.sh` already enables `pipefail`.

## Codex escalation code-review result

Not required.

## Gate results

Final pre-push gate, publish, cache prewarm, backend-restart API timing, and served-route browser verification passed.

## Plan update summary

W-001 through W-004 complete.

## Plan archive result

Plan status updated to done after runtime verification.

## Archive and merge result

Pending merge and push from task branch to main.
