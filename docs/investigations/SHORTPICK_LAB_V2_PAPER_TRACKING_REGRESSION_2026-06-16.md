# Short Pick Lab V2 Paper Tracking Regression Investigation

Status: active
Owner: Codex
Created at: 2026-06-16
Project: stock_dashboard

## rawProblem

用户报告 `试验田v2` 存在以下问题：

1. 没有按照需求完全按照 `试验田v1` 的纸面策略展示。原试验田的折线图和柱状图没有出现，表格没有筛选功能，表格的“说明”过于冗长。
2. 只有买入情况，没有卖出情况，也没有地方查看收益。
3. `纸面追踪` 里只有一个策略；但之前应该有几个还不错的候选。
4. `历史回放` 结果明显回退：此前花了大量精力得出的多种高年化选股模式消失，只看到一些很差的数字。

用户要求先从上下文或归档文档里重新查找和统计此前得出的方案，全面整理。已有历史回测数据的有意义方案应进入 `纸面追踪`，表现最好的作为冻结策略，其余作为对照组。用户举例：`rank2: +271.23%, 最大回撤 -11.90%`。

## normalizedProblem

`试验田v2` 的用户可见页面把前一轮治理中固化的 H10 quiet champion 证据和 v1 纸面追踪结构丢失了：纸面追踪展示不具备 v1 的收益/退出/筛选体验，历史回放读取旧弱 artifact，导致高收益候选策略没有出现在用户路径中。

## expectedBehavior

- `纸面追踪` 结构应对齐 `试验田v1`：最新模拟交易、策略说明、累计收益折线图、策略/退出效果柱状图、可筛选表格。
- `纸面追踪` 应展示从 `2026-05-08` 信号日以来的详细结果，并用 `回放` 标签标记追补行。
- 纸面明细不只显示买入，还要能看到卖出/退出状态和收益。
- `纸面追踪` 应展示当前高价值策略组合：最佳策略为冻结主线，其余合格或关键候选作为对照组；诊断策略必须清楚标记诊断，不得误升为冻结策略。
- `历史回放` 不展示具体逐行内容，但必须展示已固化的历史统计，包括 H10 quiet champion 的高收益候选，而不是只展示早期弱结果。
- 所有用户可见说明应是中文可读文本，避免 raw config/key 形态。

## actualBehavior

Served API check on 2026-06-16:

- `/shortpick-lab-v2/paper-tracking` 返回 `selected_configs` 含 fixed85/fixed80，但 `paper_display.charts` 只有 `覆盖情况` 和 `动作分布` 两个进度条式 bar 数据。
- `paper_display.table.columns` 为 `信号日/记录类型/策略/动作/标的/入选位置/数量/剩余现金/说明`，没有退出日、退出收益、收益状态或筛选模型。
- 表格 `rows=54`，latest trade 为 `2026-05-27 买入首选 振华科技 000733.SZ`，说明重复且冗长。
- `/shortpick-lab-v2/historical-replay?sample_limit=0` 返回 `status=blocked`，`selected_config_count=0`，只展示旧基线 `top1_or_skip_v1 +11.3%` 和旧 rejected rows，例如 `conservative_cash_reserve_60k_top5_v1 +24.6%`、`fixed_notional_40k_top5_v1 +30.6%`。
- 当前历史回放没有展示 fixed85/fixed80、rank2 冠军、fixed90 诊断、rank1/rank3 ablation、参数显著性结果。

## reproductionEvidence

Real API path:

- `python3` read of `http://127.0.0.1:8000/shortpick-lab-v2/paper-tracking`
  - selected configs:
    - `quiet_breakout_rank2_poolhot10_mtw__fixed_notional_85k_top5_h10_v1`
    - `quiet_breakout_rank2_poolhot10_mtw__fixed_notional_80k_top5_h10_v1`
  - charts: `覆盖情况`, `动作分布`
  - table rows: `54`
  - table columns omit exit/return fields.
- `python3` read of `http://127.0.0.1:8000/shortpick-lab-v2/historical-replay?sample_limit=0`
  - status: `blocked`
  - selected configs: `0`
  - baseline config: `top1_or_skip_v1`, total return `+11.3162%`, max drawdown `-30.8438%`
  - rejected configs: old weak strategy-search rows only.

Limitations:

- Browser screenshot is not yet captured in this investigation phase; API and source inspection already reproduce the data mismatch.
- The high-performing H10 replay JSON files referenced by archived docs are not present under current source `output/`, so the current machine-readable source for the champion evidence is the archived governance JSON plus durable markdown decisions.

## priorStrategyInventory

Durable benchmark evidence from `DECISIONS.md` and `docs/archive/SHORTPICK_LAB_V2_H10_QUIET_CHAMPION_RUN_2026-06-15.md`:

| Role | Strategy | Total Return | Annualized | Market Excess | Max Drawdown | Trades | Skip | Disposition |
|------|----------|--------------|------------|---------------|--------------|--------|------|-------------|
| Frozen benchmark candidate | `quiet_breakout_rank2_poolhot10_mtw__fixed_notional_85k_top5_h10_v1` | `+271.23%` | about `+53.9%` | about `+229.4%` | `-11.90%` | `190` | `73.65%` | Best current benchmark; must be primary line. |
| Capital shadow candidate | `quiet_breakout_rank2_poolhot10_mtw__fixed_notional_80k_top5_h10_v1` | `+257.25%` | about `+52.0%` | about `+215.4%` | `-11.90%` | `192` | `73.37%` | Control / capital-shadow line. |
| Boundary diagnostic | `quiet_breakout_rank2_poolhot10_mtw__fixed_notional_90k_top5_h10_v1` | `+284.35%` | not stable enough for promotion | not recorded in current display | `-11.90%` | not recorded in current display | not recorded in current display | Diagnostic only because turnover gate failed. |
| Lower notional diagnostic | `quiet_breakout_rank2_poolhot10_mtw__fixed_notional_75k_top5_h10_v1` | `+241.87%` | `+49.84%` | `+200.03%` | `-11.83%` | `193` | `73.23%` | Promising but robustness blocked direct paper promotion. |
| Lower notional diagnostic | `quiet_breakout_rank2_poolhot10_mtw__fixed_notional_70k_top5_h10_v1` | `+223.03%` | `+47.07%` | `+181.18%` | `-11.44%` | `192` | `73.37%` | Promising but robustness blocked direct paper promotion. |

Parameter and ablation evidence from archived docs:

- H10 remains the bounded horizon; v1 evidence showed 10 trading days dominated 1/3/5/20.
- MTW weekday gate is supported as a bounded empirical setting, not a causal claim.
- poolhot10 remains supported; poolhot09 increased coverage but drawdown deteriorated to around `-27%`, poolhot11/12 had no trades.
- Rank2 is directly supported in same-gate ablation:
  - rank1 fixed85: `+60.74%`, max drawdown `-25.48%`, trades `175`
  - rank2 fixed85: `+271.23%`, max drawdown `-11.90%`, trades `190`
  - rank3 fixed85: `+50.80%`, max drawdown `-28.05%`, trades `177`
- Old strategy-search artifact rows such as `conservative_cash_reserve_60k_top5_v1` are rejected under the later market/annualized gates and must not dominate the final v2 history view.

## directCause

Confirmed direct causes:

1. `src/ashare_evidence/shortpick_v2_read_model.py` builds `/shortpick-lab-v2/historical-replay` from `SHORTPICK_V2_REPLAY_ARTIFACT_CANDIDATES` and `SHORTPICK_V2_RULE_SELECTION_ARTIFACT_CANDIDATES`, which resolve in runtime to the old 2026-06-12 strategy-search artifacts. That path has `selected_configs=[]` and weak rejected rows, so the H10 quiet champion results disappear from historical replay.
2. The H10 governance artifact is read only by the paper-tracking path. It exposes fixed85/fixed80 as future-observation candidates, but the historical replay path does not merge or summarize the H10 governance/parameter/rank-ablation evidence.
3. `ShortpickLabV2View.tsx` implements a simplified v2 paper tab instead of matching the v1 `PaperTrackingTab` structure. It renders progress bars through `PaperDisplayChartCard`, not ECharts cumulative return and ranking charts.
4. `_paper_display_row_from_replay_decision()` and `_paper_display_visible_rows()` include only action/buy/cash fields. Exit tracks, exit day, stock return, and portfolio return are not projected to the v2 paper display table.
5. Current tests and runtime verifier asserted presence of section labels and absence of raw field-shaped strings, but did not assert v1 parity, exit/return visibility, multi-strategy roster completeness, or H10 historical replay restoration.

## rootCauseChain

1. H10 strategy work correctly discovered and archived the quiet champion benchmark.
2. Paper-governance work intentionally prevented historical replay from being claimed as true-forward paper performance.
3. Display work then added replay-tagged catch-up rows, but constrained validation around row volume, bounded query behavior, and readable labels.
4. The plan/review gate did not require semantic equivalence to v1 paper tracking or historical replay completeness against the H10 champion inventory.
5. The served route therefore passed technical smoke checks while failing the user's actual analysis workflow.

## missedInterceptors

- Requirement intake: "展示结构要和试验田v1一致" was accepted too loosely as section names, not feature parity.
- Source coverage: prior H10 results were not enumerated as a required strategy roster for history/paper display.
- Production path fidelity: served verification checked strings and counts, but not the actual strategy rows and return values the user relies on.
- External review: review focus was bounded raw-field and runtime behavior, not whether high-performing strategies disappeared.
- Test design: no regression test fails when `/historical-replay` omits fixed85/fixed80 or when v2 paper table lacks exit/return fields.

## downstreamImpactScan

Inspected:

- `DECISIONS.md`, `PROJECT_STATUS.json`
- `docs/archive/SHORTPICK_LAB_V2_H10_*`
- `plans/archive/plan-20260615-shortpick-v2-paper-tracking-display.md`
- `runs/archive/2026-06-15-*`
- `src/ashare_evidence/shortpick_v2_read_model.py`
- `frontend/src/components/ShortpickLabV2View.tsx`
- `frontend/src/components/ShortpickLabView.tsx`
- `frontend/src/components/shortpickLabPaperTracking.ts`
- served `/shortpick-lab-v2/paper-tracking`
- served `/shortpick-lab-v2/historical-replay?sample_limit=0`

Findings:

- H10 source artifacts referenced by archived docs are missing from current source `output/`; the only current machine-readable H10 candidate artifact is `docs/archive/SHORTPICK_LAB_V2_H10_PAPER_GOVERNANCE_ARTIFACT_2026-06-15.json`.
- Current runtime historical replay still resolves to old `shortpick-v2-replay-artifact-20260612.json` / `shortpick-v2-rule-selection-artifact-20260612.json`.
- v1 paper UI already has reusable interaction concepts: latest simulated trade, strategy status metrics, strategy explanations, cumulative return chart, strategy exit-effect ranking chart, search/group/entry/exit filters, table rows with exit result.
- v2 paper display data model lacks fields needed to render equivalent exit/return behavior.

Bounded non-findings:

- No evidence that fixed85/fixed80 disappeared from paper-tracking `selected_configs`; they exist as metadata.
- No evidence that fixed90 is currently promoted to selected paper configs; it remains diagnostic in the governance artifact.

## remediations

| Type | Status | Remediation | Evidence Required |
|------|--------|-------------|-------------------|
| known_defect | planned | Restore H10 quiet champion strategy inventory into historical replay and paper-tracking strategy roster. | Backend tests and served API showing fixed85/fixed80, diagnostic fixed90, and rank ablation/readout context. |
| known_defect | planned | Extend v2 paper display projection with sell/exit and return fields for 2026-05-08 onward replay-tagged rows. | Backend tests showing exit day/status/return fields; served API rows include exit/return data. |
| known_defect | planned | Rebuild v2 paper UI to match v1 paper tracking interaction structure: latest trade, strategy explanation, line chart, bar chart, filters, concise table. | Browser verification on canonical route and frontend tests/static checks. |
| process_gap | planned | Add source-roster and v1-parity validation to the runtime verifier so future closeout cannot pass with only old weak artifacts. | Verification script checks strategy IDs, headline returns, chart types, filter controls, and exit/return text. |
| downstream_impact | planned | Record missing H10 output artifact handling and ensure runtime/source read path has a durable H10 summary source. | Plan/run evidence identifies chosen durable data source and prevents old artifact override. |

## confidence

High. The served API, source code, and archived decisions align: the user-visible regression is caused by old historical replay artifact selection plus a v2-specific simplified paper UI/data model that does not project v1 paper-tracking semantics.

## openQuestions

- Whether the repair should regenerate missing H10 JSON artifacts into `output/` or make the archived H10 governance artifact the durable summary source for history. The plan should decide this explicitly.
- Whether 70k/75k diagnostics should appear in the UI as secondary diagnostics or remain only in history documentation because robustness rejected direct paper promotion.
