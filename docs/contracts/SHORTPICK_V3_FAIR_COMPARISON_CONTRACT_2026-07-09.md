# Shortpick v3 公平比较合同

日期：2026-07-09  
状态：已落地为 CLI 门禁和单元测试  
代码入口：`shortpick-strategy-lab-comparison-readiness`

## 背景

> 2026-07-15 修订：本文记录的 8 条是当时的准入全集。当前活跃前沿已按
> `SHORTPICK_V3_ACTIVE_STRATEGY_SET_2026-07-15.md` 收敛为 3 个角色；其余 5 条保留历史证据但不再参与活跃前沿。

前端 v3 历史回放展示的是策略全集在完整历史窗口的静态账户回放统计。R14 候选准入后当时为 8 条，
具体数量和逐项最优值必须从静态 read model 动态读取，不能继续使用旧的 6 条快照：

- 窗口：`2023-09-07 ~ 2026-06-26`
- 信号日：`509`
- 初始资金：`200,000 CNY`
- 约束：20 万资金池、复投、100 股整手、逐订单账户回放

而新一轮真上游探索最初虽然已经补齐完整候选池，但正式 walk-forward candidate-run 受训练窗口和
forward label 可用性限制，账户回放窗口曾只有：

- 窗口：`2025-07-03 ~ 2026-06-05`
- 信号日：`176`

所以“100% 左右收益”和前端“300%+ 收益”不是同一比较口径。前者只能说明较短可评估窗口内的方向，
不能作为替换前端完整历史策略全集的证据。

2026-07-09 已补充 `shortpick-model-deterministic-full-history-select`，对确定性上游候选从 PIT
feature matrix 直接生成完整历史 selected TopK 源，不再被 forward label 或 walk-forward split 截短。
这类候选随后必须再跑 `shortpick-v3-rolling-account-replay-build` 生成逐订单账户回放。

## 强制规则

任何新模型、上游候选、卖出策略或资金分配策略，要声称“优于当前前端 v3 策略组”，必须同时满足：

1. `signal_date_from`、`signal_date_to` 与前端完整历史基准完全一致；或给前端策略全集补同一候选窗口的逐订单回放。
2. 使用同一账户合同：20 万初始资金、当前 NAV 复投、100 股整手、逐订单成交、同一费用和同一入场/退出可执行性约束。
3. 至少输出以下指标：总收益、年化收益、最大回撤、负收益月份、最差月收益、订单跳过率、信号跳过率、买入订单数、最终净值、平均投入比例、最大单票暴露。
4. 总收益不能跨窗口比较；年化收益可以作为探索线索，但不能单独作为上线或替换证据。
5. CLI 审计状态不是 `passed_same_window_metrics_ready` 时，只能标记为方向性研究，不能做同窗口优劣判断。
6. 要进入前端策略组，还必须带 `--require-frontier-acceptance` 运行严格门禁，并取得
   `passed_frontier_acceptance`；同窗口本身不代表指标达标。

说明：`signal_day_count`、`selected_pick_count`、`market_symbol_count` 是诊断指标，不再作为同窗口
阻断项。不同上游模型天然可能在同一日期范围内选择更多/更少可交易日，这应通过跳过率、订单数、
收益、回撤等指标评价，而不是阻止比较。

## 可执行门禁

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli shortpick-strategy-lab-comparison-readiness \
  --candidate-replay-artifact /path/to/candidate-account-replay.json \
  --output-json /path/to/fair-comparison-readiness.json
```

退出码含义：

- `0`：候选窗口与前端完整历史窗口一致，可以进入同窗口指标比较。
- `1`：候选缺少 `data_scope` 或窗口不一致，只能作为方向性研究。

## 当前完成状态

- [x] 已将前端完整历史基准窗口固化为审计参考。
- [x] 已实现 `shortpick_strategy_lab_fair_comparison_contract.v1`。
- [x] 已新增 CLI：`shortpick-strategy-lab-comparison-readiness`。
- [x] 已新增测试覆盖短窗口阻塞和同窗口通过。
- [x] 已明确当前 `2025-07-03 ~ 2026-06-05` 的真上游结果不能直接与前端 `2023-09-07 ~ 2026-06-26` 的 300%+ 完整历史收益比较。
- [x] 2026-07-10 新增 `--require-frontier-acceptance`：按前端当时 7 条策略逐指标取最优值，强制所有核心指标不劣化，并要求至少一项改善 10% 或负收益月份减少 1 个。
- [x] R14 候选通过准入前 7 条策略九项动态前沿后加入前端；2026-07-15 起门禁按 3 条活跃角色抬高前沿。
- [x] 已修正门禁：同窗口强制项为起止日期；信号日数为诊断项。
- [x] 已支持从逐订单回放 `leaderboard + results[].summary` 读取候选完整指标。
- [x] 已用完整历史候选回放产物验证门禁可通过。

## 后续探索的退出路径

下一轮上游探索要想真正完成，需要二选一：

1. 把候选上游模型补成完整历史窗口账户回放，再跑本合同门禁。
2. 对前端策略全集补 `2025-07-03 ~ 2026-06-05` 同窗口逐订单账本，再在短窗口内比较。

没有完成其中之一前，任何“收益 100% vs 300%”的结论都应视为比较口径错误。

截至 2026-07-09，本轮 capacity-cluster 候选已完成第一条路径：

- 完整候选源：`walk-forward-model-candidate-run-84adc785808483d3.json`
- 完整历史逐订单回放：`shortpick-v3-full-history-upstream-capacity-cluster-trial-000/001/002/003-account-replay-20260709.json`
- 同窗口审计：`shortpick-v3-full-history-upstream-capacity-cluster-trial-000/001/002/003-fair-comparison-readiness-20260709.json`
- 审计状态：4 个 trial 均为 `passed_same_window_metrics_ready`
