# Shortpick v3 真上游探索记录（2026-07-09）

## 目标

本轮目标不是继续调 selected_top_k 之后的权重、执行或卖出，而是从 selected_top_k 之前的候选池重新做上游排序、过滤或空仓模型。

候选晋级条件比前几轮更严格：每个核心指标都必须优于当前前端已展示的 6 条策略中对应最优值，且至少一个重要指标相对当前 6 条最优值仍改善 `>= 10%`，或负收益月份进一步减少 1 个。

## 前端 6 条策略逐项最优门槛

当前前端 6 条策略包括：

- 主策略：14 tranche 复投 + 分层退出
- 候选对照：上游元信号稳健缩放
- 候选对照：元信号质量分层
- 候选对照：三段稳定性控制
- 候选对照：条件化攻击模式
- 对照组：15 tranche 低集中度复投

逐项最优门槛如下。新候选必须同时超过这些门槛。

| 指标 | 必须优于 | 当前最优来源 |
|---|---:|---|
| 总收益 | `> 336.32%` | 上游元信号稳健缩放 |
| 年化收益 | `> 69.21%` | 上游元信号稳健缩放 |
| 最大回撤 | `> -6.92%` | 上游元信号稳健缩放 |
| 负收益月份 | `< 3` | 上游元信号稳健缩放、元信号质量分层 |
| 最差月收益 | `> -1.47%` | 上游元信号稳健缩放 |
| 订单跳过率 | `< 21.77%` | 15 tranche 低集中度复投 |
| 信号跳过率 | `< 21.61%` | 元信号质量分层、15 tranche 低集中度复投 |
| 最大单票暴露 | `< 25.19%` | 上游元信号稳健缩放 |
| 最终净值 | `> 872,638.95 CNY` | 上游元信号稳健缩放 |

这个门槛组合非常硬：收益、回撤、负月份来自同一强候选，但跳过率来自低集中度/低最小下单额对照组。新模型不能靠放松资金、手数、成本或最小下单额来通过。

## 数据可用性检查

完整公平验证需要 `2023-09-07 ~ 2026-06-26` 的 selected_top_k 之前候选池或 PIT feature matrix。

检查结果：

- 之前用于 full713 探索的 `/private/tmp/.../pit-feature-matrix-0cc2f4d7b223cfe9.json`、`executable-label-matrix-403088086820ac2d.json`、extended candidate-run 等临时文件已被系统清理。
- 当前运行时持久 artifact store 中最大的 PIT feature matrix 为 `pit-feature-matrix-47417185baa11025.json`，只覆盖 `2025-09-22 ~ 2026-05-27`，共 160 个交易日。
- 当前运行时持久 artifact store 另有 `2026-05-28 ~ 2026-06-25` 的 20 日矩阵，但仍缺少 `2023-09-07 ~ 2025-09-21` 的完整 selected_top_k 之前候选池。
- 运行时现有 walk-forward candidate-run 大多没有可直接复用的 `selected_top_k_picks_by_date`，不能作为完整历史真上游候选来源。

结论：当前持久数据不足以对完整历史窗口做公平的真上游正式回放。不能把局部窗口结果包装成完整历史突破候选。

## 局部真上游扫描

为验证方向，本轮在当前仍可用的持久矩阵上做了一次局部真上游扫描：

- 窗口：`2025-09-22 ~ 2026-06-25`
- 来源：
  - `pit-feature-matrix-47417185baa11025.json`
  - `pit-feature-matrix-bce3f29619c01bb7.json`
- 方法：从 selected_top_k 之前的全候选池按日期重新打分，保留 top1/top2/top3；不使用 forward label 做选股；再用同一 20 万资金池、14 tranche、2250 元最小下单额、分层退出回放。
- 扫描公式族：
  - `momentum`
  - `strong_breakout`
  - `stable_breakout`
  - `regime_dynamic`
  - `anti_crowd`
  - `midcap_quality`

局部扫描 artifact：

- `/tmp/stock_dashboard_v3_true_upstream_partial_scan_20260709.json`

局部扫描中表现相对最好的可交易候选为 `regime_dynamic_top3`：

| 指标 | `regime_dynamic_top3` 局部结果 |
|---|---:|
| 局部总收益 | `9.83%` |
| 局部年化收益 | `13.16%` |
| 最大回撤 | `-10.03%` |
| 负收益月份 | `5` |
| 最差月收益 | `-3.56%` |
| 订单跳过率 | `20.21%` |
| 信号跳过率 | `1.88%` |
| 最大单票暴露 | `14.12%` |

这个结果只说明“跳过率和集中度可以通过上游重排改善”，但收益、回撤和负月份远弱于当前前端候选，且窗口不完整，不能晋级。

## 劣化原因复盘

用户指出“没有找到候选不能算完成”后，本轮继续追查劣化来源。新的证据显示，上一轮简单公式扫描失败不等于上游没有空间，主要劣化原因是：

1. **手写公式绕开了项目内正式上游选择逻辑。** 已注册 registry 中存在 `regime_adaptive_breakout_defensive_ranker`、风险缩放、补位、日期曝光缩放等上游选择策略；上一轮只用少量手写公式从 feature matrix 打分，没有执行 `_select_top_k_rows` 的 rank 权重、补位、日期缩放和信号空仓逻辑。
2. **标签代理收益和 20 万账户可买性严重错位。** `risk_scaled_balanced_concentrated_liquidity_momentum_20d_v1` 的 Top20 在标签代理上看起来强，但账户回放中 Top3 订单跳过率超过 `82%`，Top5 超过 `96%`，主因是 `price_too_high_for_slot`。这些候选多为高价/大额票，小资金 rolling tranche 每格预算买不起一手，代理收益无法转化成真实账户收益。
3. **收益和稳定性冲突集中在 Rank1 强势末端。** 正式 capacity-cluster 上游候选进入账户后，可买性大幅改善，但最差亏损仍集中在 Rank1：例如 `2026-05-06 605389.SH`、`2026-04-17 605365.SH`、`2026-04-23 600208.SH`、`2026-04-22 605100.SH`。这些入场共同点是强基准/高动量环境下，Rank1 已经从 20 日高点回落，继续机械持有 20 日会放大强势末端亏损。
4. **当前可用窗口偏近期，不能替代完整历史。** 可正式流式复用的持久矩阵仍只有 `2025-09-22 ~ 2026-05-27` 的 160 个交易日和 `2026-05-28 ~ 2026-06-25` 的 20 个交易日。局部突破不能直接说明三年全历史通过。

## 正式上游候选补充回放

为避免继续依赖手写公式，本轮使用项目内正式 workbench 跑了单模型流式 candidate-run：

- model spec：`weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_weak_overheated_underfilled_capacity_cluster_candidate_replacement_v1`
- 窗口：`2025-09-22 ~ 2026-05-27` 的 160 日矩阵，其中 walk-forward 可评估信号日为 `2025-12-23 ~ 2026-05-27`，共 `100` 个信号日
- candidate-run：`/tmp/stock_dashboard_v3_true_upstream_capacity_cluster_160d_20260709/research_validation/walk_forward_model_candidate_runs/walk-forward-model-candidate-run-df70ab994319101b.json`
- comparison report：`/tmp/stock_dashboard_v3_true_upstream_capacity_cluster_160d_20260709/research_validation/model_comparison_reports/model-comparison-report-51892c32952b86d9.json`
- 账户回放：`/tmp/stock_dashboard_v3_true_upstream_capacity_cluster_trial-000_rolling_account_160d_20260709.json`

同一 20 万资金池、14 tranche、2250 元最小下单、分层退出下，正式上游候选局部账户结果：

| 指标 | capacity-cluster 正式上游局部结果 |
|---|---:|
| 局部总收益 | `23.82%` |
| 局部年化收益 | `52.48%` |
| 最大回撤 | `-8.70%` |
| 负收益月份 | `1` |
| 最差月收益 | `-3.75%` |
| 订单跳过率 | `36.98%` |
| 信号跳过率 | `10.59%` |
| 买入订单数 | `121` |
| 最大单票暴露 | `27.00%` |

这个结果相比手写扫描明显更接近可用方向，但仍没有达到“稳定盈利”的目标：回撤、最差月和单票暴露都不够好，且窗口不是完整历史。

## 强势末端入场门控局部突破

基于坏单复盘，本轮测试了一个窄上游入场门控，而不是修改卖出：

- 条件：Rank1 所在信号日满足 `benchmark_return_20d >= 0.05`、`rank1 distance_from_20d_high <= -0.015`、`rank1 return_5d_percentile >= 0.94`
- 动作：当天 selected_top_k 全部空仓，不进入 rolling tranche
- 命中日期：`2026-01-15`、`2026-04-21`、`2026-04-22`、`2026-04-23`、`2026-04-24`、`2026-04-29`、`2026-05-06`、`2026-05-07`、`2026-05-12`、`2026-05-13`
- 扫描摘要：`/tmp/stock_dashboard_v3_true_upstream_capacity_cluster_strong_benchmark_pullback_scan_best_20260709.json`

局部账户结果：

| 指标 | 门控前 | 强势末端门控后 |
|---|---:|---:|
| 局部总收益 | `23.82%` | `32.49%` |
| 局部年化收益 | `52.48%` | `74.26%` |
| 最大回撤 | `-8.70%` | `-8.21%` |
| 负收益月份 | `1` | `0` |
| 最差月收益 | `-3.75%` | `0.43%` |
| 订单跳过率 | `36.98%` | `37.35%` |
| 信号跳过率 | `10.59%` | `22.35%` |
| 买入订单数 | `121` | `104` |
| 最大单票暴露 | `27.00%` | `26.95%` |

解释：

- 这是目前最有价值的新增方向：它直接覆盖“强势末端衰竭/行业趋势末端入场风险”，并在局部账户回放中同时改善收益、年化、回撤、负月和最差月。
- 它仍不能晋级：窗口只有 100 个账户信号日；信号跳过率上升到 `22.35%`，略高于前端 6 策略逐项最优门槛 `21.61%`；最大回撤 `-8.21%` 也弱于前端 6 策略最优 `-6.92%`。
- 下一轮应该围绕这个方向继续做完整历史恢复后的验证，或在局部窗口内寻找“不显著增加信号跳过率”的替代门控，而不是回到泛化手写动量公式。

### 回撤优先的窄门控变体

随后在同一方向上缩小扫描范围，加入 turnover 条件，寻找“不牺牲收益、但优先压回撤和跳过率”的变体：

- 条件：Rank1 所在信号日满足 `benchmark_return_20d >= 0.02`、`rank1 distance_from_20d_high <= -0.03`、`rank1 return_5d_percentile >= 0.90`、`rank1 turnover_rate_percentile >= 0.82`
- 动作：当天 selected_top_k 全部空仓
- 命中日期：`2026-01-07`、`2026-01-09`、`2026-01-14`、`2026-01-20`、`2026-01-21`、`2026-04-17`、`2026-05-07`、`2026-05-19`、`2026-05-25`

局部账户结果：

| 指标 | 门控前 | 回撤优先窄门控 |
|---|---:|---:|
| 局部总收益 | `23.82%` | `24.39%` |
| 局部年化收益 | `52.48%` | `53.87%` |
| 最大回撤 | `-8.70%` | `-6.65%` |
| 负收益月份 | `1` | `1` |
| 最差月收益 | `-3.75%` | `-0.18%` |
| 订单跳过率 | `36.98%` | `38.69%` |
| 信号跳过率 | `10.59%` | `21.18%` |
| 买入订单数 | `121` | `103` |
| 最大单票暴露 | `27.00%` | `26.56%` |

解释：

- 这个变体的重点不是收益突破，而是证明“强势末端 + turnover 条件”可以把局部最大回撤压到 `-6.65%`，已经好于前端 6 策略逐项最优门槛 `-6.92%`。
- 它仍不能晋级：负收益月份没有减少到 `0`，总收益提升只有约 `2.4%`，没有达到 10% 明显优势；订单跳过率也更差。
- 这给下一轮提供了更明确的搜索边界：收益型门控和回撤型门控是同一信号族的两个端点，下一步应寻找二者的组合或学习式门控，而不是继续扩大无解释参数网格。

## 旧版完整池子尝试（已被后续补正）

本节保留为问题来源记录。后续复查发现这里使用的 `pit-feature-matrix-3119cfbf6cc3a06b`
元数据窗口虽然写着 `2023-09-07 ~ 2026-06-26`，但实际行只覆盖 `2025-04-03 ~ 2026-06-26`。
因此本节中的 `106.13%`、`111.15%`、`112.89%` 只能解释当时为什么出现比较口径错误，
不能作为完整历史结论。正式完整历史逐订单回放见下一节“候选完整历史逐订单回放补正”。

用户指出公平比较前必须先建立完整池子后，本轮补建并持久化了
`2023-09-07 ~ 2026-06-26` 的 selected_top_k 之前研究池子。产物均写入运行时 artifact
store，不再依赖 `/tmp`。

完整池子输入与矩阵产物：

| 产物 | artifact id | 关键覆盖 |
|---|---|---:|
| input snapshot | `model-exploration-input-snapshot-26e409cb12f68441` | 3036 个可用股票、675 个 as_of 日期 |
| PIT feature matrix | `pit-feature-matrix-3119cfbf6cc3a06b` | 886,135 行 |
| executable label matrix | `executable-label-matrix-f8e325850f561dbd` | 886,135 行，其中 819,608 行 label ready |

label matrix 仍存在 `blocked_or_partial_label_rows`，原因是 `2026-06-26` 附近缺少完整
forward 20d 标签；这是前视收益标签窗口限制，不代表上游池子缺失。

随后使用完整池子补跑正式上游 candidate-run：

- candidate-run：`walk-forward-model-candidate-run-346be99ad61a1a60`
- comparison report：`model-comparison-report-9e757d3b4c5f7b92`
- 账户回放：`shortpick-v3-full-upstream-gate-account-replay-20260709.json`
- 回放信号期：`2025-07-03 ~ 2026-06-05`，共 176 个信号日、528 条 selected picks

注意：池子覆盖已经补齐到 `2023-09-07 ~ 2026-06-26`，但 walk-forward 训练和 forward label
要求导致可评估账户信号期从 `2025-07-03` 开始。因此下面结果是“完整池子基础上的
walk-forward 可评估信号期回放”，不能包装成完整三年账户收益。

### 完整池子账户基线

| 指标 | capacity-cluster 完整池子基线 |
|---|---:|
| 总收益 | `106.13%` |
| 年化收益 | `104.62%` |
| 最大回撤 | `-4.72%` |
| 负收益月份 | `1` |
| 最差月收益 | `-0.30%` |
| 订单跳过率 | `35.36%` |
| 信号跳过率 | `21.59%` |
| 买入订单数 | `223` |
| 平均投入比例 | `61.73%` |
| 最大单票暴露 | `24.32%` |
| 最终净值 | `412,267.89 CNY` |

这个结果比局部 100 信号日回放更强，说明正式 capacity-cluster 上游本身在完整池子可评估期内
有较好的收益和稳定性。但它仍不能直接与前端 6 条完整历史策略做三年级别公平比较，原因是可评估
信号期不同。

### 原“收益型”粗门控复验失败

局部窗口里表现最好的收益型门控是：

- 条件：`benchmark_return_20d >= 0.05`、Rank1 `distance_from_20d_high <= -0.015`、
  Rank1 `return_5d_percentile >= 0.94`
- 动作：当天 selected_top_k 全部空仓

完整池子可评估期复验结果：

| 指标 | 基线 | 原收益型粗门控 |
|---|---:|---:|
| 总收益 | `106.13%` | `75.72%` |
| 年化收益 | `104.62%` | `74.72%` |
| 最大回撤 | `-4.72%` | `-4.69%` |
| 负收益月份 | `1` | `1` |
| 最差月收益 | `-0.30%` | `-0.45%` |
| 订单跳过率 | `35.36%` | `37.37%` |
| 信号跳过率 | `21.59%` | `35.23%` |
| 买入订单数 | `223` | `181` |

结论：原收益型方向的“整天空仓”动作在局部窗口过拟合，完整池子中会错过 2025 年 8-9 月和
2026 年 5 月的一批趋势赢家，收益大幅劣化。它不能晋级，也不应该继续沿用原规则。

### 收益型窄门控深挖

为了保留“强势末端 Rank1 入场风险”的方向，同时避免整天空仓，本轮继续做两类窄变体扫描：

- `shortpick-v3-full-upstream-strong-tail-gate-grid-20260709.json`：只降低触发日期的 Rank1 权重。
- `shortpick-v3-full-upstream-strong-tail-rerank-grid-20260709.json`：触发日期把 Rank1 主预算重排给 Rank2/Rank3。

最好的窄门控变体：

- 条件：`benchmark_return_20d >= 0.04`、Rank1 `distance_from_20d_high <= -0.035`、
  Rank1 `return_5d_percentile >= 0.94`、Rank1 `turnover_rate_percentile >= 0.88`
- 动作：只把 Rank1 权重降为 `0`，不整天空仓
- 命中日期：`2025-08-25`、`2025-09-03`、`2025-09-11`、`2025-09-17`、`2026-01-14`

| 指标 | 基线 | 窄门控 |
|---|---:|---:|
| 总收益 | `106.13%` | `111.15%` |
| 年化收益 | `104.62%` | `109.55%` |
| 最大回撤 | `-4.72%` | `-4.53%` |
| 负收益月份 | `1` | `0` |
| 最差月收益 | `-0.30%` | `0.05%` |
| 订单跳过率 | `35.36%` | `35.59%` |
| 信号跳过率 | `21.59%` | `22.16%` |
| 买入订单数 | `223` | `219` |
| 最大单票暴露 | `24.32%` | `26.02%` |

这个变体满足“稳定盈利”的方向性要求：总收益提升约 `4.73%`，最大回撤改善约 `4.12%`，
负收益月份减少 1 个，最差月从负转正，按既定口径属于 10% 以上稳定性突破。但最大单票暴露上升到
`26.02%`，信号跳过率也小幅上升。因此它是有效研究方向，不是无副作用晋级策略。

最好的重排变体：

- 条件：`benchmark_return_20d >= 0.08`、Rank1 `distance_from_20d_high <= -0.015`、
  Rank1 `return_5d_percentile >= 0.94`、Rank1 `turnover_rate_percentile >= 0.88`
- 动作：Rank1 主预算拆给 Rank2/Rank3

| 指标 | 基线 | 重排变体 |
|---|---:|---:|
| 总收益 | `106.13%` | `112.89%` |
| 年化收益 | `104.62%` | `111.26%` |
| 最大回撤 | `-4.72%` | `-4.82%` |
| 负收益月份 | `1` | `0` |
| 最差月收益 | `-0.30%` | `0.29%` |
| 订单跳过率 | `35.36%` | `34.99%` |
| 信号跳过率 | `21.59%` | `21.02%` |
| 最大单票暴露 | `24.32%` | `25.85%` |

这个变体的收益更强、跳过率更好，但最大回撤和单票暴露有副作用，所以也不能判定为严格通过。

## 候选完整历史逐订单回放补正

用户指出上一版没有真正落实“候选完整历史逐订单回放”。问题根因是：先前的正式
walk-forward candidate-run 仍受训练窗口和 forward label ready 约束，导致账户回放只覆盖
`2025-07-03 ~ 2026-06-05` 的 176 个信号日。这个结果不能让前序上游探索和前端 6 条完整历史
策略公平比较。

本次补正新增了确定性上游候选完整历史选择流程：

- CLI：`shortpick-model-deterministic-full-history-select`
- 作用：从 PIT feature matrix 直接按已注册确定性 model spec 生成完整历史 selected TopK 源；
  不使用 forward label 做选股，不受 walk-forward split 截短。
- 配套回放 CLI：`shortpick-v3-rolling-account-replay-build`
- 公平门禁修正：`signal_date_from`、`signal_date_to` 是强制同窗口项；
  `signal_day_count`、`selected_pick_count` 是诊断项，因为不同上游模型在同一日期范围内可以有不同可交易日数。

### 完整历史输入产物

之前提到的 `pit-feature-matrix-3119cfbf6cc3a06b` 元数据窗口看似完整，但实际行只覆盖
`2025-04-03 ~ 2026-06-26`，不能作为三年完整候选池。已改用运行时数据库重建完整 PIT feature
matrix：

| 产物 | artifact id | 实际覆盖 |
|---|---|---:|
| input snapshot | `model-exploration-input-snapshot-26e409cb12f68441` | `2023-09-07 ~ 2026-06-26` |
| PIT feature matrix | `pit-feature-matrix-9e2854ba4a2cd78e` | 1,990,456 行、675 个交易日 |

完整特征矩阵路径：

`/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/artifacts/research_validation/pit_feature_matrices/pit-feature-matrix-9e2854ba4a2cd78e.json`

### 完整历史候选源

复验的上游候选仍是前序探索中最值得保留的 capacity-cluster/收益型方向：

`weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_weak_overheated_underfilled_capacity_cluster_candidate_replacement_v1`

完整历史候选源：

`/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/artifacts/research_validation/walk_forward_model_candidate_runs/walk-forward-model-candidate-run-84adc785808483d3.json`

候选源覆盖：

| 指标 | 数值 |
|---|---:|
| 特征行数 | 1,990,456 |
| trial 数 | 4 |
| 每个 trial 入选信号日 | 511 |
| 每个 trial selected picks | 1,533 |
| label 依赖 | 不需要 |

### 逐订单账户回放结果

账户合同：20 万初始资金、当前 NAV 复投、100 股整手、逐订单成交、同一入场/退出可执行性约束。
4 个 trial 均完成 `2023-09-07 ~ 2026-06-26` 完整历史逐订单回放，并通过同窗口审计。

| trial | 总收益 | 年化收益 | 最大回撤 | 负收益月份 | 最差月收益 | 订单跳过率 | 信号跳过率 | 买入订单 | 最终净值 | 平均投入 | 最大单票暴露 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 000 | 295.72% | 63.41% | -7.34% | 4 | -1.73% | 19.92% | 19.37% | 772 | 791,443.21 | 65.42% | 25.32% |
| 001 | 303.56% | 64.56% | -7.23% | 4 | -1.73% | 19.71% | 19.18% | 774 | 807,120.73 | 65.78% | 25.32% |
| 002 | 299.30% | 63.94% | -7.34% | 4 | -1.73% | 20.02% | 19.57% | 771 | 798,607.76 | 65.71% | 25.32% |
| 003 | 303.69% | 64.58% | -7.23% | 4 | -1.73% | 19.61% | 19.18% | 775 | 807,382.02 | 65.90% | 25.32% |

逐订单回放产物：

- `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/artifacts/research_validation/shortpick_v3_account_replays/shortpick-v3-full-history-upstream-capacity-cluster-trial-000-account-replay-20260709.json`
- `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/artifacts/research_validation/shortpick_v3_account_replays/shortpick-v3-full-history-upstream-capacity-cluster-trial-001-account-replay-20260709.json`
- `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/artifacts/research_validation/shortpick_v3_account_replays/shortpick-v3-full-history-upstream-capacity-cluster-trial-002-account-replay-20260709.json`
- `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/artifacts/research_validation/shortpick_v3_account_replays/shortpick-v3-full-history-upstream-capacity-cluster-trial-003-account-replay-20260709.json`

同窗口审计产物：

- `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/artifacts/research_validation/fair_comparison_readiness/shortpick-v3-full-history-upstream-capacity-cluster-trial-000-fair-comparison-readiness-20260709.json`
- `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/artifacts/research_validation/fair_comparison_readiness/shortpick-v3-full-history-upstream-capacity-cluster-trial-001-fair-comparison-readiness-20260709.json`
- `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/artifacts/research_validation/fair_comparison_readiness/shortpick-v3-full-history-upstream-capacity-cluster-trial-002-fair-comparison-readiness-20260709.json`
- `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/artifacts/research_validation/fair_comparison_readiness/shortpick-v3-full-history-upstream-capacity-cluster-trial-003-fair-comparison-readiness-20260709.json`

审计状态：4 个 trial 均为 `passed_same_window_metrics_ready`。

## 劣化归因与增量优化

在完整历史逐订单回放基础上，本轮继续拆解 trial-003 的劣化来源，并尝试只接受“收益、回撤、
负月份、跳过率不劣化”的优化。

### 劣化来源

trial-003 原最佳配置为
`daily_15_tranche_rank_weighted_compound_min1000_rank3_pullback_late_trend_loss_guard_v1`。
主要劣化点如下：

1. 负收益月份集中在 `2023-10`、`2023-12`、`2025-01`、`2025-10`，共 4 个。
2. 最大亏损单主要来自 Rank1 机械 20 日持有：例如 `603039.SH 泛微网络`、`000697.SZ 炼石航空`、
   `002101.SZ 广东鸿图`、`002357.SZ 富临运业`、`605077.SH 华康股份`。
3. 这些坏单的常见入场特征是：`return_20d_percentile` 与 `return_5d_percentile` 很高，
   `industry_return_20d_excess` 较强，成交额放大，但已经跌离 20 日高点。也就是“强势末端
   + 行业拥挤 + 回撤后继续满权重”。
4. 直接对这类 strong-tail 入场做降权能把负月份从 4 降到 3，但总收益会明显下降，因此不能作为
   不劣化优化。
5. 正贡献段主要来自 Rank1/Rank2 行业领导者，尤其是 `industry_return_20d_excess >= 0.35` 的
   候选；单独小幅增配 Rank1 行业领导者可以小幅增收，但幅度不足。

### 已验证但未接受的方向

| 方向 | 结果 | 结论 |
|---|---|---|
| strong-tail 降权 | 负月份可从 4 降到 3，但收益从 303.69% 降到约 293% 或更低 | 稳定性方向成立，但收益劣化，不接受 |
| 行业领导者增配 + strong-tail 轻度降权 | 收益最高约 318.34%，负月份 3，但最大回撤劣化到约 -7.37% | 有研究价值，但不满足回撤不劣化 |
| 13 tranche 加大投入 | 收益最高约 334.53%，接近前端最佳，但回撤、单票暴露、跳过率变差 | 证明 15 tranche 偏保守，但风险副作用过大 |
| 13 tranche + 单票成本上限 | 压低集中度后收益明显回落，不能保留 13 tranche 的优势 | 不接受 |

### 接受的增量优化

本轮发现一个严格不劣化的小优化：给 `15 tranche + min1000` 增加与主线一致的
`Rank1 quick-fail + Rank3 pullback late guard` 退出策略。

新增配置：

`daily_15_tranche_rank_weighted_compound_min1000_layered_rank1_quickfail_rank3_pullback_exit_v1`

4 个 trial 的完整历史结果：

| trial | 原最佳总收益 | 新配置总收益 | 原最大回撤 | 新最大回撤 | 负收益月份 | 订单跳过率 | 信号跳过率 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 000 | 295.72% | 301.02% | -7.34% | -7.14% | 4 | 20.12% | 19.57% |
| 001 | 303.56% | 305.12% | -7.23% | -7.12% | 4 | 19.92% | 19.37% |
| 002 | 299.30% | 301.06% | -7.34% | -7.14% | 4 | 20.02% | 19.57% |
| 003 | 303.69% | 305.14% | -7.23% | -7.14% | 4 | 19.81% | 19.37% |

解释：

- 这是一个小幅但真实的无副作用增量：收益和回撤同时改善，跳过率只小幅变化，负月份不变。
- 它没有达到“10% 明显突破”，也没有超过前端当前最佳 `336.32%` 总收益和 3 个负月份。
- 因此它应进入候选回放合同，作为后续探索基线的一部分，但不能被包装成新主策略。

新增逐订单回放产物：

- `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/artifacts/research_validation/shortpick_v3_account_replays/shortpick-v3-full-history-upstream-capacity-cluster-trial-000-account-replay-with-15tranche-quickfail-20260709.json`
- `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/artifacts/research_validation/shortpick_v3_account_replays/shortpick-v3-full-history-upstream-capacity-cluster-trial-001-account-replay-with-15tranche-quickfail-20260709.json`
- `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/artifacts/research_validation/shortpick_v3_account_replays/shortpick-v3-full-history-upstream-capacity-cluster-trial-002-account-replay-with-15tranche-quickfail-20260709.json`
- `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/artifacts/research_validation/shortpick_v3_account_replays/shortpick-v3-full-history-upstream-capacity-cluster-trial-003-account-replay-with-15tranche-quickfail-20260709.json`

同窗口审计产物：

- `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/artifacts/research_validation/fair_comparison_readiness/shortpick-v3-full-history-upstream-capacity-cluster-trial-000-with-15tranche-quickfail-fair-comparison-readiness-20260709.json`
- `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/artifacts/research_validation/fair_comparison_readiness/shortpick-v3-full-history-upstream-capacity-cluster-trial-001-with-15tranche-quickfail-fair-comparison-readiness-20260709.json`
- `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/artifacts/research_validation/fair_comparison_readiness/shortpick-v3-full-history-upstream-capacity-cluster-trial-002-with-15tranche-quickfail-fair-comparison-readiness-20260709.json`
- `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/artifacts/research_validation/fair_comparison_readiness/shortpick-v3-full-history-upstream-capacity-cluster-trial-003-with-15tranche-quickfail-fair-comparison-readiness-20260709.json`

## 当前结论

本次补正后，前序上游探索已经有了可比较的完整历史逐订单账户结果。结论变为：

1. 之前 `100%` 左右收益确实是比较口径错误，不代表上游方向真实退化到只能赚 100%。
2. capacity-cluster 上游候选在完整历史逐订单回放中能达到约 `305%` 总收益，已经回到前端策略组同量级。
3. 它仍不能晋级为新主策略：前端当前最佳为 `336.32%` 总收益、`69.21%` 年化、`-6.92%` 最大回撤、`3` 个负收益月份；本候选最佳 trial-003 新配置为 `305.14%`、`64.79%`、`-7.14%`、`4` 个负收益月份。
4. 本候选的优势是跳过率明显更低：最佳 trial 的订单跳过率约 `19.81%`，优于前端 6 条中的最优 `21.77%`；信号跳过率约 `19.37%`，优于前端最优 `21.61%`。但收益和稳定性没有全面超过当前前端最佳。
5. 因此它是有意义的完整历史对照候选或进一步优化基线，不是可直接替换前端主策略的完成态。

完成状态：

- [x] 已明确前端 6 条策略的逐项最优硬门槛。
- [x] 已确认旧完整池子产物实际行覆盖不足，不能支持完整历史结论。
- [x] 已重建并验证 `2023-09-07 ~ 2026-06-26` 的完整 PIT feature matrix。
- [x] 已新增确定性上游候选完整历史选股源生成能力。
- [x] 已新增 candidate-run 到逐订单账户回放 CLI。
- [x] 已修正公平比较门禁：信号日差异是诊断项，不是同窗口阻断项。
- [x] 已完成 capacity-cluster 候选 4 个 trial 的完整历史逐订单回放。
- [x] 已完成 4 个 trial 的同窗口公平审计，状态均通过。
- [x] 已新增 15 tranche quick-fail 分层退出候选配置，并完成 4 个 trial 的完整历史回放。
- [x] 未把该候选包装成上线主策略；原因是核心收益/回撤/负月仍未超过前端当前最佳。

## 下一步方向

继续真正上游探索时，应该以这次完整历史逐订单回放作为新基线，而不是再用短窗口结果：

1. 保留 capacity-cluster 的低跳过率优势，优先寻找能减少负收益月份到 `<= 3` 且不降低收益的 Rank1 强势末端风险处理。
2. 继续验证 `强基准 + Rank1 已回撤 + 5日强势 + 高换手` 的窄门控，但必须在完整历史逐订单回放上验证，不能再用局部窗口代理结论。
3. 继续测试“Rank1 风险触发后重排给 Rank2/Rank3”的上游方案，目标是保留收益并消除回撤副作用。
4. 继续做上游学习式重排时，必须把“20 万账户一手可买性/价格过高/最小下单额”作为候选生成或排序的一等约束，不能只看 label 代理收益。

## 自驱动上游探索 Goal 结果

本轮 goal 的验收条件：

- 比较口径必须是 `2023-09-07 ~ 2026-06-26` 完整历史逐订单账户回放。
- 基线使用当前 capacity-cluster trial-003 + `15 tranche + min1000 + Rank1 quick-fail + Rank3 pullback`
  候选：总收益 `305.14%`，年化 `64.79%`，最大回撤 `-7.14%`，负收益月份 `4`，
  订单跳过率 `19.81%`，信号跳过率 `19.37%`，最大单票暴露 `25.32%`。
- 候选必须不劣化核心指标，并且至少一个关键指标改善 `>= 10%`，或负收益月份减少 1 个。

### 探索方向与结论

| 方向 | 最好结果 | 是否通过 | 结论 |
|---|---|---|---|
| Rank1 强势末端重排 | 总收益 `307.37%`，回撤 `-7.10%`，跳过率小幅改善 | 否 | 严格不劣化，但收益只提升约 `0.73%`，没有达到 10% |
| 新注册 `shallow_drawdown_lowvol` 上游 spec | 最好总收益约 `266.49%`，最大回撤约 `-8.21%`，负收益月份 `5` | 否 | 没有命中关键坏单，且收益/回撤/负月份全面劣化 |
| “伪板块领导力”强势末端门控 | 严格不劣化最好为总收益 `311.18%`，跳过率约 `19.15%` | 否 | 收益提升约 `1.98%`，跳过率改善约 `3.33%`，仍未达到 10% 或减少负月 |
| PIT 同日候选替换 | 最高小幅增收，但负月份增至 `6`、跳过率和回撤劣化 | 否 | 替换看似更健康的候选会破坏原模型捕捉赢家的结构 |
| 20 万账户一手可买性替换 | 订单跳过率最多改善约 `25.87%` | 否 | 跳过率突破成立，但总收益下降约 `2.13%`，回撤和单票暴露劣化 |

### 可保留信号

本轮最有价值但未通过晋级的信号是：

`强势末端 + 行业超额不足 + Rank2 晋级`

触发条件：

- Rank1 `return_5d_percentile >= 0.94`
- Rank1 `return_20d_percentile >= 0.94`
- Rank1 `amount_10d_vs_20d_percentile >= 0.94`
- Rank1 `distance_from_20d_high <= -0.025`
- Rank1 `industry_return_20d_excess <= 0.22`
- `-0.005 <= benchmark_return_20d <= 0.06`
- Rank1 `avg_amount_20d >= 50,000,000`
- 动作：Rank1 置零并把 Rank2 提升为 Rank1

完整历史回放结果：

| 指标 | 基线 | 该信号 |
|---|---:|---:|
| 总收益 | `305.14%` | `311.18%` |
| 年化收益 | `64.79%` | `65.67%` |
| 最大回撤 | `-7.14%` | `-7.14%` |
| 负收益月份 | `4` | `4` |
| 最差月收益 | `-1.73%` | `-1.73%` |
| 订单跳过率 | `19.81%` | `19.15%` |
| 信号跳过率 | `19.37%` | `18.98%` |
| 最大单票暴露 | `25.32%` | `25.32%` |

解释：

- 这是本轮唯一“严格不劣化”的较清晰上游信号。
- 它仍不能晋级，因为没有达到 `>= 10%` 的明确突破，也没有把负收益月份从 `4` 降到 `3`。
- 它可以作为下一轮搜索的局部特征，而不是直接进入前端对照组。

### 运行时产物治理

保留的小型摘要产物：

- `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/artifacts/research_validation/full_upstream_rebuild_logs/self_driven_upstream_rank1_tail_focused_scan_20260709.json`
- `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/artifacts/research_validation/full_upstream_rebuild_logs/self_driven_upstream_shallow_drawdown_lowvol_account_scan_20260709.json`
- `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/artifacts/research_validation/full_upstream_rebuild_logs/self_driven_upstream_pseudo_leadership_tail_scan_20260709.json`
- `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/artifacts/research_validation/full_upstream_rebuild_logs/self_driven_upstream_pit_replacement_scan_20260709.json`
- `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/artifacts/research_validation/full_upstream_rebuild_logs/self_driven_upstream_affordable_replacement_scan_20260709.json`

已清理：

- 失败的 `shallow_drawdown_lowvol` 完整 candidate-run 源，约 `31MB`，不保留以避免数据膨胀。
- 第一次误连 worktree 小数据库产生的异常扫描日志。

### 本轮 Goal 结论

本轮没有找到满足“核心指标不劣化 + 10% 明显突破/负月减少”的可晋级上游策略。
但完成了有效的搜索空间排除：

1. 单纯 Rank1 强势末端重排只能带来小幅收益改善，不能解决负收益月份。
2. 更换成 `shallow_drawdown_lowvol` 类上游 spec 会显著丢失赢家，不能继续。
3. PIT 同日候选替换和一手可买性替换虽然方向合理，但会把低跳过率换成收益/回撤劣化；
   后续如果继续做，必须把“替代候选未来收益结构”转化成不使用 forward label 的稳定特征，而不是简单替换。
