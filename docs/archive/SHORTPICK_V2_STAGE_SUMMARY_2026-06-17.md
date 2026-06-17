# 试验田 v2 阶段性总结与证据索引（2026-06-17）

本文是试验田 v2 近几轮研究的统一入口。目标不是再证明某个策略可用，而是把已经做过的试验、结果、失败原因和后续边界归档到当前仓库，避免后续继续依赖散落在 worker worktree 里的记忆或临时文件。

## 总判断

到 2026-06-17 为止，还没有找到一个同时满足“历史回测强、纸面追踪强、逻辑可解释、资金约束真实可执行”的新策略。

当前历史回测最强的基线仍然是：

| 基线 | 选股/买股口径 | 历史总收益 | 年化 | 市场超额 | 最大回撤 | 交易 | 纸面窗口 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `fixed85` 主基线 | 安静突破 Rank2 + 热度池 10% + 周一至周三 + 单笔约 8.5 万 + Top5 候补/跳过 + H10 | +271.2% | +53.9% | +229.4% | -11.9% | 190/192 | -9.5%，回撤 -18.1% |
| `fixed80` 资金影子基线 | 同上，单笔约 8 万 | +257.2% | +52.0% | +215.4% | -11.9% | 192 | -9.5%，回撤 -18.1% |

这两条线在三年历史回测内足够强，但 2026-05-08 之后的纸面窗口表现很差。当前判断是：不能因为 7 笔纸面交易就推翻历史基线，也不能把三年回测当成足够可靠的晋级证据。后续需要继续研究“为什么近期错过主线”和“是否存在可解释的排序/主题/位置形态修正”。

## 证据已经归档到当前仓库

以前散落在 worker worktree 的 JSON 和重跑报告已归档到：

- [归档包目录](shortpick-v2-stage-summary-2026-06-17/)
- [归档 JSON 产物](shortpick-v2-stage-summary-2026-06-17/artifacts/)
- [归档重跑报告](shortpick-v2-stage-summary-2026-06-17/reports/)

归档包补齐了早期没有进入主线目录的产物，包括：

- initial/refined/next 三轮 v2 策略搜索 selection/replay JSON。
- H10 quiet、robust、strength、exit、entry-quality、MA accel、MA accel refine 等方向的 selection/replay JSON。
- H10 champion、benchmark robustness、parameter significance、rank ablation、execution decomposition 等核心 JSON。
- 交易日/回撤/金额矩阵、持有周期敏感性、OOS 大亏过滤、风险开关、ranking 替代、主题位置诊断、paper divergence 的 JSON。
- 2026-06-17 重跑报告：`SHORTPICK_V2_NEXT_DIAGNOSTICS_20260617_RERUN.md`、`SHORTPICK_PAPER_DIVERGENCE_ATTRIBUTION_20260617_RERUN.md`。

后续不应再引用 worker worktree 作为证据源；如果需要恢复细节，先从本文和上述归档包进入。

## 试验总表

| 序号 | 方向 | 怎么选股/买股 | 结果 | 当前结论 | 入口 |
| ---: | --- | --- | --- | --- | --- |
| 1 | v2 原始资金约束建模 | 20 万初始资金，A 股 100 股整手，不允许延迟买入；候选买不起则候补或跳过 | 初始 broad search 无达标结果，很多组合年化不足或回撤过大 | 资金约束必须保留；延迟买入被排除 | [v2 计划](../contracts/SHORTPICK_LAB_V2_PLAN_2026-06-12.md)、[回放设计](../contracts/SHORTPICK_LAB_V2_REPLAY_DESIGN_2026-06-12.md) |
| 2 | 初始/下一轮/refined 策略搜索 | conservative cash reserve、fixed notional、position cap、golden cross、industry diversified、ma/strength/exit/entry-quality 等多方向网格 | 选择产物多次 `blocked`；初始 29 个拒绝，next 25 个拒绝，entry-quality 44 个拒绝 | 广撒网方向没有打出可用替代，不应继续无约束扩网 | [初始 selection](shortpick-v2-stage-summary-2026-06-17/artifacts/shortpick-v2-strategy-search-selection-artifact.json)、[next selection](shortpick-v2-stage-summary-2026-06-17/artifacts/shortpick-v2-next-strategy-search-selection-artifact.json)、[entry-quality selection](shortpick-v2-stage-summary-2026-06-17/artifacts/shortpick-v2-h10-entry-quality-standard-selection-artifact.json) |
| 3 | H10 安静突破冠军族 | 安静突破 Rank2 + 热度池 10% + 周一至周三 + H10；比较固定 70k/75k/80k/85k/90k 等 | fixed85 +271.23%，年化 +53.96%，回撤 -11.90%；fixed80 +257.25%，年化 +52.03%，回撤 -11.90%；fixed90 收益高但 turnover 超门槛 | fixed85/fixed80 固化为后续对标基线；90k 只能诊断，不能绕过治理门槛 | [H10 champion run](SHORTPICK_LAB_V2_H10_QUIET_CHAMPION_RUN_2026-06-15.md)、[champion artifact](shortpick-v2-stage-summary-2026-06-17/artifacts/shortpick-v2-h10-quiet-champion-selection-artifact.json) |
| 4 | 参数显著性 | 对 MTW、poolhot10、fixed85/fixed80、fallback/skip/no delayed buy、Rank2、90k 等做 bounded same-window 检查 | MTW、poolhot10、fixed85/fixed80 有统计支撑；Rank2 在本轮先标为待消融；90k 诊断-only | 支持项可以作为当前基线说明，不能解释为因果证明 | [参数显著性](SHORTPICK_LAB_V2_H10_PARAMETER_SIGNIFICANCE_RUN_2026-06-15.md)、[artifact](shortpick-v2-stage-summary-2026-06-17/artifacts/shortpick-v2-h10-parameter-significance-artifact.json) |
| 5 | Rank 消融 | 固定同一 gate，比较 Rank1/Rank2/Rank3/Rank4/Rank5 | Rank2 明显最好；Rank1 +60.7%、回撤 -25.5%；Rank2 +271.2%、回撤 -11.9%；Rank3 +50.8%、回撤 -28.1% | Rank2 不再只是拍脑袋，是当前同窗消融下最强项 | [Rank ablation](SHORTPICK_LAB_V2_H10_RANK_ABLATION_RUN_2026-06-15.md)、[artifact](shortpick-v2-stage-summary-2026-06-17/artifacts/shortpick-v2-h10-rank-ablation-artifact.json) |
| 6 | 持有周期敏感性 | 固定 v2 主线，比较 H1/H3/H5/H7/H10/H15/H20，单笔 8 万/8.5 万 | H10 最强；H5/H7 收益低但回撤更低；H1/H3 不合格；H15/H20 回撤/跳过恶化 | H10 在 v2 资金约束回放里重新成立，不只是 v1 遗留假设 | [持有周期](SHORTPICK_V2_HORIZON_SENSITIVITY_2026-06-16.md)、[artifact](shortpick-v2-stage-summary-2026-06-17/artifacts/shortpick-v2-horizon-sensitivity-20260616.json) |
| 7 | 交易日、回撤反转、金额矩阵 | 比较周一至周三/周一至周五、v1 回撤反转开关、1 万到 8.5 万单笔金额 | 周一至周三 + 不加回撤反转 + 8.5 万最强；周一至周五放开交易日后回撤扩大；低金额显著降收益 | 当前数据支持 MTW，但不能宣称星期因果；1 万到 3 万低金额无法满足收益目标 | [矩阵文档](SHORTPICK_LAB_V2_H10_WEEKDAY_DRAWDOWN_NOTIONAL_MATRIX.md)、[artifact](shortpick-v2-stage-summary-2026-06-17/artifacts/shortpick-v2-h10-weekday-drawdown-notional-matrix-artifact.json) |
| 8 | 固定 8.5 万交易日验证 | 固定金额 8.5 万，比较 123、234、135、345、1234、12345，叠加回撤反转对比 | MTW 仍领先；交易日扩展没有带来稳健改进 | 交易日限制有数据支撑，但仍应写成统计事实，不写成逻辑因果 | [fixed85 weekday validation](SHORTPICK_LAB_V2_H10_WEEKDAY_DRAWDOWN_FIXED85_VALIDATION.md)、[artifact](shortpick-v2-stage-summary-2026-06-17/artifacts/shortpick-v2-h10-weekday-drawdown-fixed85-validation-artifact.json) |
| 9 | 风险开关 | 弱势日降仓/跳过、最多 3 仓、v1 回撤反转入场过滤、全防御组合 | 弱势日降到 5 万历史最接近但不改善纸面；v1 回撤反转过滤纸面恶化到 -20.2% / -27.3% | 没有可替代基线的风险开关；回撤反转不能直接吸收到 v2 主线 | [风险开关](SHORTPICK_V2_RISK_SWITCH_EXPERIMENT_2026-06-16.md)、[artifact](shortpick-v2-stage-summary-2026-06-17/artifacts/shortpick-v2-risk-switch-experiment-20260616.json) |
| 10 | OOS 大亏前兆过滤 | 高涨幅过滤、涨幅贴高过滤、贴 20 日高点过滤、市场走强叠加个股涨幅过滤 | 没有同时满足 holdout 收益保留、回撤改善和 paper 改善；高涨幅过滤也未晋级 | 不要用当前纸面亏损反向调阈值 | [OOS loss filter](SHORTPICK_V2_OOS_LOSS_FILTER_2026-06-16.md)、[artifact](shortpick-v2-stage-summary-2026-06-17/artifacts/shortpick-v2-oos-loss-filter-20260616.json) |
| 11 | 排序替代回测 | 行业热度 + 回撤蓄势、行业热度 + 成交额、回撤优先 + 低追高，对比原 Rank2 | paper 上个别替代有改善，但 holdout 和全历史显著弱于原 Rank2；不能晋级 | 不要继续围绕这三个弱排序扩大参数网格 | [ranking backtest](SHORTPICK_V2_RANKING_BACKTEST_2026-06-16.md)、[artifact](shortpick-v2-stage-summary-2026-06-17/artifacts/shortpick-v2-ranking-backtest-20260616.json) |
| 12 | 纸面追踪计算/展示治理 | v2 纸面追踪只展示 2026-05-08 后的回放；历史回放只展示统计值；修复先买后卖导致负现金的显示问题 | 展示 bug 修复后，真实纸面回撤仍然存在，不是纯显示问题 | 工程展示问题和策略问题要分开，不可用展示修复掩盖策略亏损 | [tracking contract](../contracts/SHORTPICK_LAB_V2_PAPER_TRACKING_CONTRACT_2026-06-12.md)、[performance defect](../investigations/SHORTPICK_LAB_V2_PAPER_PERFORMANCE_DEFECT_2026-06-16.md) |
| 13 | v1/v2 纸面分歧归因 | v2 fixed85/fixed80 纸面账户 vs v1 原始 forward 观察 vs v1 20 万账户派生对照 | 2026-06-16 重跑：v2 -9.5%、回撤 -18.1%、7 笔；v1 派生账户 +2.0%、回撤 -5.1%、5 笔；但 v1 资金约束强对照历史 -37.0%、回撤 -65.1% | 当前窗口支持“v1 因子近期更顺”，但不足以替换 v2；v1 资金约束历史表现太差 | [paper divergence 6/16](SHORTPICK_PAPER_DIVERGENCE_ATTRIBUTION_2026-06-16.md)、[paper divergence 6/17 rerun](shortpick-v2-stage-summary-2026-06-17/reports/SHORTPICK_PAPER_DIVERGENCE_ATTRIBUTION_20260617_RERUN.md) |
| 14 | 下一轮死胡同诊断 | 逐笔画像、相似指数窗口、v1 资金约束强对照 | 纸面只有 7 笔，单笔影响大；历史相似沪深300窗口后续中位数为负；当前环境不一定是纯偶然噪声 | 需要继续归因，不是“纯等着”；但也不能从 7 笔交易生成强规则 | [next diagnostics 6/16](SHORTPICK_V2_NEXT_DIAGNOSTICS_2026-06-16.md)、[next diagnostics 6/17 rerun](shortpick-v2-stage-summary-2026-06-17/reports/SHORTPICK_V2_NEXT_DIAGNOSTICS_20260617_RERUN.md) |
| 15 | 主题和位置形态诊断 | 检查 6 月强势股是否在 eligible universe、是否进入 Top5、实际是否买入；比较高位追强/回撤蓄势形态 | 6 月 Top50 强势股 98% 在合格观察域，但只有 2% 进入 Top5，实际买入 0%；当前更像 Top5 排序错过主线 | 后续应研究排序/主题入口，而不是继续改买入金额或简单过滤 | [theme diagnostics](SHORTPICK_V2_THEME_POSITION_DIAGNOSTICS_2026-06-16.md)、[artifact](shortpick-v2-stage-summary-2026-06-17/artifacts/shortpick-v2-theme-position-diagnostics-20260616.json) |

## 已确认不要重复踩的坑

1. 不要恢复“延迟买入”。当前约定只有买入首选、买入同日候补、跳过；延迟买入口径没有可解释性。
2. 不要再做无边界的 broad search。initial/next/refined/entry-quality/MA/exit/strength 等方向已经大量失败，后续必须围绕明确问题验证。
3. 不要把 90k 当成可晋级策略。90k 历史收益高，但 turnover 超出当前治理边界，只能作为诊断。
4. 不要把周一至周三写成因果规律。它有同窗统计支撑，但没有被证明为星期本身导致收益。
5. 不要直接吸收 v1 回撤反转过滤。它在矩阵里未提升主线，在风险开关 paper 中显著恶化。
6. 不要用当前 7 笔纸面交易反向调阈值。OOS 大亏过滤已经证明这样很容易过拟合。
7. 不要把低单笔金额视为自然更安全。1 万到 3 万虽然降低回撤和暴露，但收益目标完全不达标。
8. 不要继续扩展行业热度 + 回撤蓄势、行业热度 + 成交额、回撤优先 + 低追高这三个排序替代；paper 局部改善不能抵消 holdout/全历史失败。
9. 不要把 v1 纸面近期表现好等同于 v1 资金约束版可用。v1 20 万账户强对照历史回测很差。
10. 不要让历史回放读取明细灌进纸面追踪。纸面追踪只展示 2026-05-08 后的回放交易，历史回放只展示统计值。

## 仍然值得保留的方向

1. 继续保留 fixed85/fixed80 作为强历史基线和对照标准。任何新方案必须先在同窗历史、holdout、paper 三层同时解释胜负。
2. 继续研究“eligible universe 覆盖强势股，但 Top5 排序错过主线”的问题。6 月强势股 98% 在观察域，实际买入 0%，这是当前最明确的诊断入口。
3. 把“回撤蓄势/高位追强”当成软排序特征继续验证，而不是直接做硬过滤。历史回撤蓄势样本小但中位收益更好，值得 OOS 验证。
4. H5/H7 可作为降波动对照，不是替代主线。它们历史收益弱于 H10，但回撤和暴露更低。
5. v1 因子近期窗口可以作为解释变量，不应直接替换 v2。后续若研究 v1，应先证明资金约束下的历史路径能过门槛。
6. 相似指数窗口和市场 regime 可以继续作为归因工具，但不能单独生成买卖规则。

## 后续读取顺序

如果后续要恢复研究上下文，建议按这个顺序读：

1. 本文。
2. [H10 champion run](SHORTPICK_LAB_V2_H10_QUIET_CHAMPION_RUN_2026-06-15.md)：确认当前最强历史基线和禁止方向。
3. [参数显著性](SHORTPICK_LAB_V2_H10_PARAMETER_SIGNIFICANCE_RUN_2026-06-15.md)、[Rank 消融](SHORTPICK_LAB_V2_H10_RANK_ABLATION_RUN_2026-06-15.md)、[持有周期](SHORTPICK_V2_HORIZON_SENSITIVITY_2026-06-16.md)：确认基线参数为什么暂时保留。
4. [交易日/回撤/金额矩阵](SHORTPICK_LAB_V2_H10_WEEKDAY_DRAWDOWN_NOTIONAL_MATRIX.md)：确认单笔金额、交易日和回撤反转的证据边界。
5. [OOS 过滤](SHORTPICK_V2_OOS_LOSS_FILTER_2026-06-16.md)、[风险开关](SHORTPICK_V2_RISK_SWITCH_EXPERIMENT_2026-06-16.md)、[ranking 替代](SHORTPICK_V2_RANKING_BACKTEST_2026-06-16.md)：确认哪些“看起来能修 paper”的方向已经失败。
6. [paper divergence 重跑](shortpick-v2-stage-summary-2026-06-17/reports/SHORTPICK_PAPER_DIVERGENCE_ATTRIBUTION_20260617_RERUN.md)、[next diagnostics 重跑](shortpick-v2-stage-summary-2026-06-17/reports/SHORTPICK_V2_NEXT_DIAGNOSTICS_20260617_RERUN.md)：确认当前纸面窗口的最新口径。
7. [主题和位置形态诊断](SHORTPICK_V2_THEME_POSITION_DIAGNOSTICS_2026-06-16.md)：作为后续研究最主要入口。

## 工程和归档注意事项

- 本文和归档包只记录研究证据，不修改纸面追踪策略，不构成实盘建议。
- 归档 JSON 是历史产物，可能包含字段形态内容；用户可读解释以本文和对应 `.md` 报告为准。
- 以后新增试验必须在当前仓库归档对应 plan/run/doc/output，不能只留在 worker worktree。
- 若未来清理 worker worktree，应先确认本文链接的仓库内文件完整存在，再删除临时目录。
