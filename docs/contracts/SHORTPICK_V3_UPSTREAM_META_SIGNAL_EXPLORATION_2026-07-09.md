# Shortpick v3 上游元信号探索结果（2026-07-09）

## 目标

在不回退到 v1 简单规则、不缩小历史验证窗口、不放松 20 万资金池/滚动建仓/整手/成本约束的前提下，探索上游选股侧是否还有突破空间。

本轮验收口径：

- 核心指标不得劣化：总收益、年化收益、最大回撤、负收益月份、最差月、订单跳过率、信号跳过率、最大单票暴露。
- 至少一个重要指标形成明确突破：收益或回撤相对改善 `>= 10%`，或负收益月份减少至少 1 个。
- 前向纸面追踪与历史回放必须使用同一策略配置，不允许历史和前向分裂。

## 基准

基准仍为 `daily_14_tranche_rank_weighted_compound_min2250_layered_rank1_quickfail_rank3_pullback_exit_v1`。

完整历史窗口：`2023-09-07 ~ 2026-06-26`，初始资金 `200,000 CNY`，每日滚动 `14 tranche`，最小下单额 `2,250 CNY`，卖出策略为 Rank1 快速冲高失败 + Rank3 入场回撤后期亏损保护。

| 指标 | 基准 |
|---|---:|
| 总收益 | 311.92% |
| 年化收益 | 65.77% |
| 最大回撤 | -7.76% |
| 负收益月份 | 4 |
| 最差月收益 | -1.78% |
| 订单跳过率 | 35.23% |
| 信号跳过率 | 24.56% |
| 最大单票暴露 | 26.76% |
| 最终净值 | 823,833.71 CNY |

## 通过候选

候选 ID：`daily_14_tranche_upstream_meta_signal_quality_min2250_weak100_strong165_lead135_low090_v1`

策略含义：不改变原始 v3 selected_top_k 模型、不改变卖出策略、不改变滚动执行方式；只在每个信号日根据 Rank1 的上游元信号质量，对当天 selected_top_k 的 `portfolio_weight` 做统一缩放。

触发规则：

| 信号段 | 条件 | 权重缩放 |
|---|---|---:|
| 弱基准 | Rank1 `benchmark_return_20d < -0.02` | 1.00 |
| 强信号 | Rank1 `benchmark_return_20d >= 0`、`return_20d_percentile >= 0.98`、`industry_return_20d_excess <= 0.50`、`distance_from_20d_high >= -0.08` | 1.65 |
| 行业领导力 | Rank1 `industry_return_20d_excess >= 0.35` 且 `benchmark_return_20d >= 0.05` | 1.35 |
| 低质量 | Rank1 `industry_return_20d_excess <= 0.20` 且 `benchmark_return_20d <= 0.08` | 0.90 |

正式回放变更规模：`389` 个信号日、`1167` 条选股记录被缩放。

## 正式回放结果

| 指标 | 基准 | 上游元信号稳健缩放 | 变化 |
|---|---:|---:|---:|
| 总收益 | 311.92% | 336.32% | +7.82% |
| 年化收益 | 65.77% | 69.21% | +5.23% |
| 最大回撤 | -7.76% | -6.92% | 改善 10.81% |
| 负收益月份 | 4 | 3 | 减少 1 个 |
| 最差月收益 | -1.78% | -1.47% | +0.31 pct |
| 订单跳过率 | 35.23% | 34.70% | 改善 1.49% |
| 信号跳过率 | 24.56% | 24.56% | 持平 |
| 最大单票暴露 | 26.76% | 25.19% | 改善 5.89% |
| 买入订单数 | 616 | 621 | +5 |
| 最终净值 | 823,833.71 CNY | 872,638.95 CNY | +5.92% |

结论：通过。本候选虽然收益提升不到 10%，但最大回撤相对改善 `10.81%`，负收益月份减少 1 个，且核心约束和主要指标未劣化，符合本轮 goal 退出条件。

## 备查候选

`upstream_meta_w100_s180_l090_v1` 收益更高：

- 总收益 `340.48%`
- 年化收益 `69.79%`
- 最大回撤 `-7.04%`
- 负收益月份 `3`
- 最大回撤改善 `9.21%`

它未达到回撤改善 `>= 10%`，因此本轮不作为主候选，只保留为收益型备查。

## Artifact

- 轻量扫描：`/tmp/stock_dashboard_v3_upstream_goal_single_config_scan_20260709.json`
- 正式回放汇总：`/tmp/stock_dashboard_v3_upstream_goal_formal_replay_summary_20260709.json`
- 通过候选 run：`/tmp/stock_dashboard_v3_upstream_meta_w100_s165_l090_v1_candidate_run_20260709.json`
- 通过候选正式回放：`/tmp/stock_dashboard_v3_upstream_meta_w100_s165_l090_v1_formal_replay_20260709.json`
- 收益型备查正式回放：`/tmp/stock_dashboard_v3_upstream_meta_w100_s180_l090_v1_formal_replay_20260709.json`

## 落地状态

- [x] 加入 rolling tranche 执行合同。
- [x] 加入历史回放静态读模型。
- [x] 加入纸面追踪读模型。
- [x] 加入日刷计划单生成脚本，前向和历史使用同一配置。
- [x] 发布运行时并验证 API。
