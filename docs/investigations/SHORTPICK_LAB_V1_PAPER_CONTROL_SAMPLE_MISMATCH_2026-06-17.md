# Shortpick Lab V1 Paper Control Sample Mismatch Investigation

## rawProblem

User report on 2026-06-17:

> 当前股票看板试验田v1的纸面跟踪的曲线图和柱状图部分
> “同股冷却过滤”等几个后加入的策略的数据和原有数据的数据量是对不上的，是不是没有触发这些数据的自动更新获取

Follow-up report on 2026-06-17:

> 当前信号日仍然和冻结策略等对不上，我要求的是完全对齐，他们应该是一样的

## normalizedProblem

The `试验田v1` paper-tracking effect line and bar charts show visibly different sample counts and latest signal dates for later-added controls such as `同股冷却过滤` compared with the frozen strategy. The user expects the v1 retrospective control chart signal-date coverage to fully align with the frozen strategy for each matured exit track.

## expectedBehavior

The chart grouping should make it clear whether a strategy row is true-forward paper tracking, archived diagnostic history, or retrospective forward replay. Later-added controls should not be collapsed into generic `市场因子对照`, and the retrospective replay/combined-ledger rows used for v1 control charts should refresh as forward windows mature so their latest matured signal date matches the frozen strategy.

## actualBehavior

Live runtime data has three different sample bases:

- `frozen_paper_primary`: 29 candidates from 2026-05-08 through 2026-06-17.
- Older archived controls such as `market_factor_control_cooldown_top1`, `market_factor_control_no_limit_chase_low_turnover_uptrend`, `market_factor_control_offensive_top1`, and `market_factor_control_top3_equal_weight`: 24 signal days through 2026-06-10.
- Later true-forward controls such as `market_factor_control_same_symbol_cooldown_low_turnover_uptrend`, `market_factor_control_drawdown_reversal_low_turnover_uptrend`, and `market_factor_control_repeated_exposure_low_turnover_uptrend`: 5 signal days from 2026-06-11 through 2026-06-17.
- The stale retrospective combined-ledger artifact generated on 2026-06-11 had `mechanical_10d` completed only through 2026-05-26 for `同股冷却过滤`, `回撤/反转过滤`, and `重复暴露限制`; frozen strategy had already completed/displayed `mechanical_10d` through 2026-06-02 after 2026-06-17 market data arrived.
- After manually regenerating retrospective replay artifacts and a new combined-ledger artifact, the artifact payload had 72 retrospective rows and `mechanical_10d` completed through 2026-06-02. Before the API merge fix, the paper-tracking projection still used the old duplicate rows because the artifact merge kept the first duplicate row by filename order.

The frontend grouped the retrospective labels but did not map the true-forward later-added role labels, so those true-forward rows appeared under generic `市场因子对照` in chart summaries and chart-to-table filtering.

## reproductionEvidence

Checked live runtime DB `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db` on 2026-06-17:

- Role candidate counts showed `frozen_paper_primary`, `market_factor_control_low_turnover_uptrend_next_open_entry`, and `market_factor_control_random_pool` at 29 rows through 2026-06-17.
- `market_factor_control_cooldown_top1`, `market_factor_control_no_limit_chase_low_turnover_uptrend`, `market_factor_control_offensive_top1`, and `market_factor_control_top3_equal_weight` stopped at 2026-06-10.
- The three later true-forward controls started at 2026-06-11 and had 5 rows each through 2026-06-17.
- Validation snapshots were updated on 2026-06-17 around 09:14-09:16, so the validation updater did run.
- Served `GET /shortpick-lab/paper-tracking/summary` reported `current_generation_roles` containing only the current active generation set, and listed older controls under `archived_controls`.
- Served `GET /shortpick-lab/paper-tracking` before the replay refresh showed frozen `mechanical_10d` at 18 signal dates through 2026-06-02, while `同股冷却过滤`, `回撤/反转过滤`, and `重复暴露限制` had only 13 signal dates through 2026-05-26.
- Runtime replay artifacts under `data/runtime-artifacts/shortpick_retrospective_replays/` were generated on 2026-06-11, before the 2026-05-27 through 2026-06-02 10-day windows matured.
- Manual refresh on 2026-06-17 regenerated `shortpick-retrospective-forward-replay-request:{f5bd43aac9146f02,b714d0e13817d7d4,3a4186dff6c24b5e}.json` and materialized `shortpick-combined-ledger-backfill:8a27d779f8041a8c.json` with `generated_at=2026-06-17T12:00:53.566624+00:00`.
- Using the fixed projection logic against the live runtime artifact root produced aligned control chart coverage: each of `同股冷却过滤`, `回撤/反转过滤`, and `重复暴露限制` had `mechanical_10d` count 18 from 2026-05-08 through 2026-06-02.

## directCause

There are four confirmed causes:

1. Backend data is intentionally not one uniform historical sample. `SHORTPICK_CURRENT_PAPER_TRACKING_GENERATION_ROLES` currently allows only the frozen primary, open-entry control, random pool, and the three later true-forward controls. Older simple market-factor controls are archived diagnostics after 2026-06-10, and later controls were not retroactively generated as true-forward rows before their 2026-06-11 start.
2. `frontend/src/components/shortpickLabPaperTracking.ts` recognized the retrospective labels `同股冷却过滤`, `回撤/反转过滤`, and `重复暴露限制`, but did not map the live true-forward role labels `同股亏损冷却版`, `回撤反转过滤版`, and `重复暴露限制版`. That made chart and table grouping understate or hide the later true-forward rows.
3. The scheduled shortpick daily cycle ran recent validation but did not refresh the retrospective replay and combined-ledger artifacts after forward windows matured. The v1 control chart therefore continued reading a 2026-06-11 replay snapshot.
4. Even after manually regenerating the combined-ledger artifact, the API projection merged duplicate `combined_ledger_row_id` rows by first-seen filename order, so an older artifact could keep a `pending_forward_window` row and suppress a newer `completed` row for the same signal/control pair.

## rootCauseChain

1. V1 paper tracking added controls in phases.
2. Backend governance narrowed active generation to the current paper-tracking role allowlist.
3. Retrospective replay rows were merged into the paper-tracking display as diagnostic evidence, not as true-forward generation.
4. Frontend chart grouping was updated for retrospective display labels, but not for the later true-forward role labels.
5. The chart sample counts therefore looked like a refresh gap instead of a mixed evidence-basis and maturity issue.
6. Retrospective replay artifacts were not part of the daily post-validation refresh, so matured 10-day windows did not become visible automatically.
7. The API projection had no latest-row conflict rule, so duplicate artifact rows could keep stale maturity status even after a refresh artifact existed.

## missedInterceptors

- Requirement intake: the UI requirement did not require chart labels to distinguish active true-forward controls from retrospective replay controls.
- Test design: helper tests covered retrospective `control_label` rows but not runtime-shaped true-forward role rows without `control_label`.
- Runtime verification: served API checks confirmed payload availability but did not verify chart grouping semantics for the later-added controls.
- Scheduled refresh design: daily validation did not include a dependent v1 retrospective replay/combined-ledger materialization step.
- Read-model design: combined-ledger projection did not prefer newer duplicate rows by `combined_ledger_materialized_at` or artifact `generated_at`.

## downstreamImpactScan

Checked areas:

- `src/ashare_evidence/shortpick_lab.py`: confirmed active generation allowlist and archived control contract.
- `src/ashare_evidence/api.py`: confirmed `/shortpick-lab/paper-tracking` merges candidate rows and combined-ledger retrospective rows.
- `frontend/src/components/shortpickLabPaperTracking.ts`: confirmed chart/group/filter mapping gap.
- `src/ashare_evidence/api.py`: confirmed duplicate combined-ledger rows kept first-seen artifact rows.
- `src/ashare_evidence/shortpick_combined_ledger_writer.py`: confirmed materialization could write `generated_at: null` when CLI callers did not pass `--generated-at`.
- `scripts/run-scheduled-refresh.sh`: confirmed shortpick daily cycle refreshed validation and frontend projections but not v1 control replay/combined-ledger artifacts.
- `tests/test_frontend_shortpick_paper_tracking_helpers.py`: confirmed test gap for active true-forward role labels.
- Served runtime API and live DB: confirmed auto refresh and validation snapshots ran on 2026-06-17.
- Served browser page after publish: confirmed the new runtime bundle was served, but the v1 paper page still hit an existing `本次连接等待超过 3s` shell/panel timeout and could not render the paper charts during this run.

Non-findings:

- No evidence that the scheduled refresh failed globally.
- No evidence that validation snapshots stopped updating.
- No database backfill was performed as part of this investigation; only runtime JSON artifacts were regenerated.
- No evidence that the chart grouping fix caused the served-page timeout; direct `/shortpick-lab/paper-tracking` reads are heavy and took about 49 seconds in one successful cold-runtime read during this investigation.

## remediations

| Type | Status | Remediation | Evidence Required |
|------|--------|-------------|-------------------|
| known_defect | fixed | Map the three later true-forward control roles and labels into the same chart/filter strategy names used by their retrospective counterparts, while keeping legacy `cooldown_top1` out of `同股冷却过滤`. | Focused frontend helper test passes. |
| process_gap | fixed | Add a regression test for runtime-shaped true-forward rows without `control_label`, plus a negative check for legacy cooldown top1 misclassification. | `tests/test_frontend_shortpick_paper_tracking_helpers.py` passes. |
| known_defect | fixed | Regenerate runtime retrospective replay and combined-ledger artifacts so v1 control chart `mechanical_10d` coverage reaches 2026-06-02, matching frozen strategy. | Fixed projection reads runtime artifact root with each control `mechanical_10d` count 18 through 2026-06-02. |
| known_defect | fixed | Prefer newer duplicate combined-ledger rows by row materialization time or artifact `generated_at`. | `tests/test_shortpick_combined_ledger_projection.py` passes. |
| process_gap | fixed | Add `scripts/refresh-shortpick-v1-control-combined-ledger.sh` and call it after shortpick validation in the scheduled daily cycle. | `bash -n` passes; script manually refreshed runtime artifact successfully. |
| process_gap | fixed | Default combined-ledger materializer `generated_at` to current UTC time when CLI callers do not supply it. | `tests/test_shortpick_strategy_governance.py -k defaults_generated_at` passes. |
| downstream_impact | bounded | Backend generation scope remains unchanged: no retroactive true-forward database backfill and no strategy parameter changes. A separate v1 paper read-model performance/page-timeout issue remains open. | Investigation records DB/API evidence, code scope, runtime artifact refresh, and live-page verification limitation. |

## confidence

High. Live DB counts, served API contract fields, and frontend helper behavior all point to active generation scope plus frontend grouping semantics, not a failed updater.

## openQuestions

- Should the UI add an explicit evidence-basis selector or visual tag for `true_forward_tracking` versus `retrospective_forward_replay` in the chart controls? This is useful but separate from the immediate grouping defect.
- Should `/shortpick-lab/paper-tracking` get the same timeout/performance closeout treatment as the prior v2 paper read-model timeout work? During live verification, the full endpoint could take about 49 seconds and concurrent reads could exceed 90 seconds.
