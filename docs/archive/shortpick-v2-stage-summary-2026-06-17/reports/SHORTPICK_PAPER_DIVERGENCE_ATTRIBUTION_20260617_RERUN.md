# 试验田 v1/v2 纸面分歧归因

本报告只用于研究归因，不代表策略晋级、淘汰或实盘建议。

## 口径

- 观察起点：2026-05-08
- 最新可用日期：2026-06-16
- 初始资金：200000.0
- 买入限制：100 股整手；不允许延迟买入。
- v1 原始纸面记录是候选 forward return；20 万账户路径是本产物派生的研究对照。

## 策略对照

| 策略 | 状态 | 总收益 | 最大回撤 | 交易 | 跳过 | 候补 | 说明 |
|------|------|--------|----------|------|------|------|------|
| 8.5 万目标买入方案 | ready | -9.5% | -18.1% | 7 | 21 | 0 | v2_paper_account_curve |
| 8 万目标买入方案 | ready | -9.5% | -18.1% | 7 | 21 | 0 | v2_paper_account_curve |
| v1 原始候选 forward 观察 | ready | - | - | 17 | - | - | v1_candidate_forward_return_not_account_nav |
| v1 派生对照：20万账户，只买首位候选，买不起就跳过 | ready | 2.0% | -5.1% | 5 | 23 | 0 | derived_v1_200k_account_control |

## 归因判断

- short_window_noise: uncertain。当前窗口成交笔数偏少，不能单独否定三年历史回测。
- v1_factor_current_window: supports。v1 派生 20 万账户 当前收益 2.0%；v2 fixed85 当前收益 -9.5%。
- execution_capital_constraint: uncertain。v2 fixed85 当前窗口候补买入 0 次；若这些交易为负，需要继续拆分 fallback 贡献。
- concentration_tail_risk: supports。v1 派生账户最差单笔 P/L 约 -10630.00 元；短窗结果可能被少数交易主导。
- regime_shift: uncertain。本产物优先做同窗账户归因；市场 regime 需要结合指数与候选池覆盖率进一步确认。

## 当前结论

- 当前更像是一个需要拆分的纸面窗口分歧，而不是可以直接推翻三年历史基准的证据。
- 支持项应作为下一轮策略治理输入，但不能单独触发策略晋级或淘汰。
