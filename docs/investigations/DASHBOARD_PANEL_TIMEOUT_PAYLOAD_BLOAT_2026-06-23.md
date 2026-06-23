# Dashboard Panel Timeout Payload Bloat Investigation

## rawProblem

User report on 2026-06-23:

> 面板一直在超时
> 超时这个问题为什么一直无法解决
> 已经治理了快10次了。还是一直出现

Follow-up constraint:

> 不要这么改，30s也太久了，我也无法接受，你要做的是压缩时间，说实话我们的数据量并不大，为什么每一次会有这么长的loading时间，我不是很理解

## normalizedProblem

The dashboard repeatedly shows frontend timeout or panel-load failure symptoms even after several prior timeout governance attempts. Increasing frontend timeout windows is not acceptable; the product should reduce actual load time.

## expectedBehavior

The v1 paper-tracking panel should return quickly enough for normal interactive use without relying on long frontend wait windows. The response should contain only fields needed by the visible table, charts, filters, and status cards.

## actualBehavior

The `/shortpick-lab/paper-tracking` response was around 3.3 MB for 386 visible rows. Warm runtime measurements still showed 2-6 second response time variance. The row count was small, but each row carried repeated/debug-heavy fields that the v1 paper-tracking frontend does not render.

## reproductionEvidence

Runtime measurements before compaction:

- `/dashboard/shell`: about 0.15-1.18s.
- `/stocks/002028.SZ/dashboard`: about 0.58-2.87s, 51 KB response.
- `/shortpick-lab/paper-tracking`: about 2.03-5.90s, 3,321,579-byte response.

Payload size attribution from `/shortpick-lab/paper-tracking`:

- `selection_score_components`: about 852 KB.
- `paper_tracking_exit_tracks`: about 522 KB.
- `validation_by_horizon`: about 311 KB.
- `monitoring_tracks`: about 258 KB.
- Top-level `combined_ledger`: about 716 KB, including duplicated `rows` and `retrospective_rows`.

Direct builder profiling showed the ledger calculation itself was not the main bottleneck:

- `_build_shortpick_paper_tracking_ledger`: about 0.48-0.78s in direct Python calls.
- `jsonable_encoder` + JSON dump: well below the multi-second UI symptom.

After compacting row payload fields in the worktree, TestClient measurements for `/shortpick-lab/paper-tracking` were 0.25-0.54s with a 917,545-byte response.

Runtime follow-up after publishing the compaction showed the payload dropped to 1,104,890 bytes for 386 rows, but real HTTP still took about 2.1-3.5s. `/shortpick-lab/paper-tracking/summary` was only about 13 KB and still took about 1.6-5.3s. Direct in-process profiling against the same runtime DB and `data/runtime-artifacts` root showed the builder itself was about 0.20-0.40s, so the remaining user-visible delay came from rebuilding and returning the same read projection on every request through the served API path, not from the row count.

After adding a per-app encoded-response cache for the v1 paper-tracking full and summary endpoints, TestClient measurements with runtime DB were:

- `/shortpick-lab/paper-tracking/summary`: cold about 0.43s, cache hits about 0.002s.
- `/shortpick-lab/paper-tracking`: cold about 0.30s, cache hits about 0.022s.

## directCause

The panel timeout symptom was first driven by oversized v1 paper-tracking payloads, not by the count of displayed rows. The endpoint returned per-row fields meant for internal diagnostics, governance inputs, or repeated contract context:

- `selection_score_components`
- `validation_by_horizon`
- `monitoring_tracks`
- `gate`
- `regime`
- Full top-level `combined_ledger.rows` / `true_forward_rows` / `retrospective_rows`

The frontend v1 paper-tracking table/charts do not render those fields. Carrying them inflated transfer size and browser parse work, and it increased the chance that other concurrent panel requests would trip the existing short frontend request attempt timeout.

Payload compaction alone was insufficient because the endpoint remained an uncached read-model rebuild on every HTTP request. The same paper-tracking projection is read-only between refreshes, so repeated panel opens and summary/full requests should reuse a short-lived encoded response instead of recomputing the ledger and reserializing it on every request.

## rootCauseChain

1. Prior timeout mitigations treated frontend timeout windows as the control surface.
2. The endpoint payload contract was not audited for visible-field necessity.
3. New paper-tracking governance/control fields accumulated in each row.
4. The UI still loaded the full row payload on entry to the paper-tracking tab.
5. Normal row count looked small, masking the fact that response bytes were large.
6. The first payload fix reduced bytes but did not add a read-model cache, so the served API path still paid rebuild overhead for every request.

## missedInterceptors

- Performance gate: tests asserted endpoint shape and summary compaction but did not cap or inspect full-row response bloat.
- Review gate: prior fixes accepted longer frontend waits rather than measuring endpoint bytes and row-field usage.
- Runtime verification: successful 200 responses were treated as enough, even when response size and latency remained high.

## downstreamImpactScan

Checked:

- `frontend/src/components/ShortpickLabView.tsx`: visible paper-tracking table, filters, and charts require `paper_tracking_exit_tracks`, label/status fields, entry/exit rule text, dates, returns, and governance labels. They do not render the removed debug/repeated fields or top-level combined ledger row arrays.
- `frontend/src/components/shortpickLabPaperTracking.ts`: helper logic uses entry/exit rules, thesis for search, and `paper_tracking_exit_tracks`; it does not require `selection_score_components`, `validation_by_horizon`, `monitoring_tracks`, `gate`, or `regime`.
- `tests/test_shortpick_lab_paper_tracking.py`: endpoint assertions require exit tracks and summary behavior, not the removed heavy fields.
- `/stocks/{symbol}/dashboard`: direct builder profile is about 0.43s and the response is about 55 KB; it is not the primary payload-bloat source.

Limitations:

- This remediation does not change the frontend timeout policy.
- This remediation does not optimize SQLite query plans beyond reducing response payload size.

## remediations

| Type | Status | Remediation | Evidence Required |
|------|--------|-------------|-------------------|
| known_defect | fixed | Compact v1 paper-tracking row payload before returning it to the frontend, removing non-rendered heavy row fields while preserving `paper_tracking_exit_tracks`. | Endpoint test verifies removed fields are absent and exit tracks remain. |
| known_defect | fixed | Return only combined-ledger counts/source metadata at the top level; retrospective rows remain available through merged `items`. | Endpoint test verifies `combined_ledger.rows`, `true_forward_rows`, and `retrospective_rows` are absent from the full endpoint. |
| known_defect | fixed | Cache encoded v1 paper-tracking full and summary responses for a 5-minute default TTL, with startup prewarm and stale-while-refresh behavior. | Endpoint cache regression verifies repeated full and summary requests are satisfied without rebuilding. |
| process_gap | fixed | Record payload bloat plus missing read-model cache as the root cause and add regression tests for both. | Investigation document plus `tests/test_shortpick_lab_paper_tracking.py`. |
| downstream_impact | bounded | Profiled stock dashboard and shell paths; paper-tracking was the only multi-MB response on the reported flow. | Local measurements in this record. |

## confidence

High. The endpoint payload size was measured directly, the largest fields were identified by byte contribution, and compacted worktree responses dropped to under 1 MB and under 0.6s in TestClient without increasing frontend timeout windows.

## openQuestions

None blocking this remediation. A future performance gate should add a formal response-size budget for live-facing read endpoints.
