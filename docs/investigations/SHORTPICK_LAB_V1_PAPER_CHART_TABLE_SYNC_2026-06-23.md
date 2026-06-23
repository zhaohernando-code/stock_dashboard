# Shortpick Lab V1 Paper Chart/Table Sync Investigation

## rawProblem

User report on 2026-06-23:

> 当前试验田v1纸面追踪的图表部分的数据和下方对不上，有滞后
> 这是不应该的，他们照理来说应该是用的同一批数据源（不应该做接口拆分，只是同个接口的不同表现）
> 你需要找到原因，并让他们进行同步更新

## normalizedProblem

The `试验田 v1 -> 纸面追踪` chart section and the ledger table below it could diverge in freshness and maturity, and the first remediation over-corrected by linking chart rows to table filters. The corrected contract is one backend payload from `/shortpick-lab/paper-tracking`, with charts and table as independent presentations of the same source payload. Table filters must not mutate chart data, and chart clicks must not mutate table filters.

## expectedBehavior

The effect charts should derive from the primary paper-tracking rows in the same endpoint payload, independent of the ledger table's record group, entry status, entry rule, exit status, and search filters. The ledger table should keep its own filtering controls. Completed-effect charts should not include half-mature validation tracks such as `pending_forward_window` or `pending_benchmark_data`.

## actualBehavior

`PaperTrackingTab` originally built `displayRows` for the table and a separate `chartRows` for charts. The first remediation replaced the chart input with `displayRows`, which made table filters drive chart data and made chart clicks drive table filters. That violated the corrected product contract: same endpoint source, independent UI presentations.

Runtime data inspection also found a separate maturity problem: some 10-day tracks entered charts from validation snapshots whose status was `pending_benchmark_data`. Example: signal date `2026-06-05` for the same-day intraday control had a stock return and exit date, but the validation status was not `completed`. Other strategies for the same signal window were still `pending_forward_window` or `pending_benchmark_data`, which made the chart show inconsistent latest 10-day signal dates.

## reproductionEvidence

Code path inspected in `frontend/src/components/ShortpickLabView.tsx`:

- The corrected chart path now receives `rows={primaryRows}` while the Ant Design table and mobile list receive `dataSource={displayRows}`.
- `displayRows` remains the table-only projection for entry state, exit state, record group, entry rule, and search filters.
- `PaperTrackingEffectCharts` no longer accepts `activeGroupFilter`, `activeExitStateFilter`, `onSelect`, or `onClearSelection`.
- Backend `_paper_tracking_validation_snapshot_from_rows` now merges `paper_tracking_exit_tracks` only from validation snapshots with `status == "completed"`.

This bounds the visible issue to frontend derived state. The backend API path already uses one full v1 endpoint for this tab: `api.getShortpickPaperTracking()` -> `/shortpick-lab/paper-tracking`.

Follow-up user reports in the same closeout:

- The first remediation removed the `累计纸面收益` strategy selector, which was an existing user-facing comparison control. The correction is to restore that selector and default it to `全部策略`, not `冻结策略`.
- The second remediation made chart/table filters interdependent. The correction is to remove that UI linkage while preserving one backend data source.
- 10-day latest signal dates differed because pending validation tracks were treated as chart-ready effect observations. The correction is to require completed validation snapshots for chart/table exit tracks.

## directCause

Frontend state derivation confused two contracts:

- Same backend source payload.
- Independent UI projections for charts and table.

The first fix collapsed those into one filtered row set, which caused the table to drive the charts. Separately, backend paper-tracking snapshot projection merged exit tracks from non-completed validation snapshots, so stock-return-only `pending_benchmark_data` rows appeared as completed chart observations.

## rootCauseChain

1. V1 paper tracking grew chart-to-table filtering and additional strategy/exit filters.
2. The component kept a separate `chartRows` projection to preserve broad comparison.
3. The first repair replaced it with `displayRows`, creating table-to-chart linkage.
4. Backend validation snapshots allowed pending benchmark rows to contribute paper exit tracks.
5. Users saw inconsistent 10-day latest signal dates because partially mature tracks were included in the chart-ready row payload.

## missedInterceptors

- Requirement coverage: the frontend contract did not distinguish "same endpoint source" from "same filtered table projection".
- Test design: static tests checked that charts existed, but also preserved the old comment requiring charts to ignore some filters.
- Runtime verification: prior checks focused on API payload availability and data maturity, not component-level filter synchronization.

## downstreamImpactScan

Checked:

- `frontend/src/api/shortpick.ts`: v1 full paper tab still uses `/shortpick-lab/paper-tracking`; no interface split was introduced for the tab.
- `frontend/src/components/ShortpickLabView.tsx`: only v1 paper chart/table derived-row split and chart click linkage were in scope.
- `frontend/src/components/shortpickLabPaperTracking.ts`: helper calculations consume whichever rows are passed and do not force a separate data source.
- `tests/test_frontend_shortpick_static.py`: had an old assertion preserving the chart/table split contract.
- Existing 2026-06-17 investigation remains valid for retrospective artifact freshness and grouping; this fix addresses the later frontend synchronization regression.

Limitations:

- This run does not change combined-ledger materialization or v2 paper-tracking code.

## remediations

| Type | Status | Remediation | Evidence Required |
|------|--------|-------------|-------------------|
| known_defect | fixed | Pass `primaryRows` into `PaperTrackingEffectCharts`; keep `displayRows` table-only. | Static test verifies `rows={primaryRows}` and forbids `rows={displayRows}` / `chartRows`. |
| known_defect | fixed | Remove chart click -> table filter linkage and remove chart/table linkage UI affordances. | Static test forbids `handlePaperEffectSelect`, linked props, and "清除图表联动筛选". |
| known_defect | fixed | Restore the line chart strategy selector as a local presentation control; default it to `全部策略` and forbid the old `冻结策略` default. | Static test verifies `selectedLineObservations`, `shortpick-paper-effect-strategy-select`, and `PAPER_TRACKING_EFFECT_ALL_STRATEGIES`. |
| known_defect | fixed | Only merge `paper_tracking_exit_tracks` from completed validation snapshots. | Backend test verifies a `pending_benchmark_data` 10-day track is not exposed as a paper-tracking exit track. |
| known_defect | fixed | Make both chart blocks and chart canvases fixed-height. | Static test verifies chart block and chart body fixed heights. |
| process_gap | fixed | Record the corrected contract: same endpoint source, independent chart/table projections. | Investigation document plus static tests. |
| downstream_impact | bounded | Runtime DB showed benchmark bars were present; validation snapshots may still need refresh to convert old pending statuses after publish. | Existing-market-data validation refresh is part of runtime closeout. |

## confidence

High. The current patch matches the latest user contract: one endpoint source, independent chart and table projections, no common-date intersection, no chart/table click linkage, and completed-only exit tracks for effect observations.

## openQuestions

None blocking closure.
