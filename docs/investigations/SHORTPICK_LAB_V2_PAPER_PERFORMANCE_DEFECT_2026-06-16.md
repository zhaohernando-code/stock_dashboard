# Shortpick Lab V2 Paper Performance Defect Investigation

## rawProblem

User report on 2026-06-16:

> 30s还是太慢了，我觉得我们没有那么大的数据量，这个时间不符合逻辑

## normalizedProblem

`试验田v2 / 纸面追踪` can still feel too slow after the frontend timeout fix because the backend cold path rebuilds a small display projection from a large market-data input window.

## expectedBehavior

The page should not make the first user after a service restart pay the full cost of rebuilding deterministic replay display rows when market data and active paper strategy inputs have not changed.

## actualBehavior

The visible response is about 55KB and contains 54 replay display rows plus two account curves, but cold construction reads about 313k daily market-bar rows for 3,074 symbols from SQLite.

## reproductionEvidence

Runtime profiling on 2026-06-16:

- Window: 2026-01-08 through 2026-06-15.
- Rows read: 313,513 daily bars.
- Symbols read: 3,074.
- Joined column select alone: about 4.93s.
- Cold read-model build: about 6.49s to 8.10s.
- Same-process warm calls: about 0.15s.
- Worktree code with runtime data after persistent cache:
  - first process: 6.125s, writes cache.
  - second process: 0.233s, reads persisted cache.
- Served runtime after publish:
  - no persisted cache: first request 42.35s, second request 1.01s.
  - persisted cache present after backend restart: first request 1.20s.

## directCause

`_paper_display_replay_rows_from_session()` used only an in-memory cache. Service restart, deploy, or process loss cleared the cache, so the next `/shortpick-lab-v2/paper-tracking` request rebuilt the display rows by calling `_load_daily_series_for_replay_window()` and loading the full market window.

## rootCauseChain

1. v2 paper tracking was adjusted to display replay rows and account curves.
2. The display projection reused a general market-window loader that reads all eligible symbols.
3. An in-memory cache made repeated same-process requests fast.
4. Runtime validation after publish restarted the service and exposed the cold path again.
5. The previous timeout fix prevented frontend aborts but did not reduce backend cold latency.

## missedInterceptors

- Runtime performance gate: served-route verification checked correctness but did not assert cold-path latency.
- Review scope: previous repair focused on the 10s frontend abort rather than backend cold-path cost.
- Cache design: cache key existed but was not persisted across process restart.

## downstreamImpactScan

Inspected:

- `src/ashare_evidence/shortpick_v2_read_model.py`
- `src/ashare_evidence/shortpick_ranked_pool_replay_input.py`
- `/shortpick-lab-v2/paper-tracking`
- `/shortpick-lab-v2/paper-tracking/summary`
- `/shortpick-lab-v2/historical-replay`

Findings:

- The full v2 paper endpoint is affected.
- Summary and historical replay remain fast and should not use this heavy display rebuild path.
- Account curve generation is not the bottleneck.

## remediations

| Type | Status | Remediation | Evidence Required |
|------|--------|-------------|-------------------|
| known_defect | fixed | Add persisted cache for deterministic v2 paper replay display rows, coverage, and account curves. | Targeted cache-hit test and runtime timing evidence. |
| process_gap | fixed | Record cold-path profiling and add regression tests that prove cache hit bypasses the market-window loader, market-data changes invalidate cache, and corrupt cache falls back to rebuild. | Investigation doc and pytest evidence. |
| process_gap | fixed | Prewarm the v2 paper display cache during publish and after scheduled refresh paths so users do not become the cold-cache builder. | Script static tests and runtime publish evidence. |
| downstream_impact | fixed | Keep summary and historical replay behavior unchanged; only full paper display uses persisted replay display cache. | Targeted endpoint tests and served route verification. |

## confidence

High. Profiling isolates the dominant cost to the market-window loader, and a second independent process returns from persisted cache in about 0.233s with the same replay row count. Served runtime also returns in about 1.20s after backend restart when persisted cache is present.

## openQuestions

Backend cold rebuild can still take tens of seconds in the served runtime when the cache is absent. The mitigation is to materialize this cache during publish and scheduled refresh. A later optimization could still reduce the underlying market-window loader cost.
