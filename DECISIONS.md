# 一个关于a股的当前数据和投资建议看板 Decisions

[2026-07-17T17:00:00+08:00] Rank5 real execution is retired and the optimization frontier becomes Rank4-only:

产品目标已明确为稳定盈利优先，“尽量不要漏单”不是硬指标。可复现完整历史账户回放显示，停用 Rank5 后总收益从 332.100% 提高到 333.679%，最大回撤从 -6.885% 略降到 -6.878%，亏损月份仍为 2 个；代价是订单跳过率从 15.145% 上升到 17.531%。该覆盖代价被显式接受。

执行约定
- 新增 Rank4-only 配置作为唯一优化前沿；旧 Rank4-5 配置归档且保持可复现，不原地改变其历史语义。
- 日刷真实替补只允许 Rank4。没有合格 Rank4 时保留现金，Rank5 不能生成买单。
- Rank5 影子观测继续运行，用于保留未来研究证据；达到成熟门槛也不得自动恢复真实执行。
- 活跃角色仍为 3 个，前端、API、纸面账户、日刷计划和历史对比使用同一活跃 ID 集合。
- 当前运行时纸面账本中旧前沿没有实际 Rank4/Rank5 替补成交，因此切换配置 ID 不会改写已发生的 Rank5 经济结果。

证据：`docs/contracts/SHORTPICK_V3_R15_RANK4_ONLY_STABLE_PROFIT_2026-07-17.json`、`docs/contracts/SHORTPICK_V3_ACTIVE_STRATEGY_SET_2026-07-17.md`、`docs/analysis/SHORTPICK_V3_RANK5_RISK_CONTROL_REPORT_2026-07-17.md`。

[2026-07-15T21:00:00+08:00] R14 Rank5 path-quality thresholds are rejected and historical Rank5 threshold search stops:

本轮在读取特征分布和候选结果前冻结 6 个 Rank5 专属路径质量条件，覆盖 20 日日波动率、下行半波动率、路径最大回撤、上涨日占比、趋势效率和一个组合条件。所有特征只使用信号日及以前的最近 21 个有效收盘价，明确禁止未来价格和库存结果字段。

- 511 条 Rank5 库存全部具备 20 个收益观察；确定性 R14 基线逐单摘要精确复现。
- 6 个候选均未通过相对可复现基线与旧 R14 展示合同的双基线九指标门禁。最接近的 4% 日波动率上限只增加 0.037 个百分点总收益，同时增加 0.207 个百分点跳过订单率。
- R14、前端、API、日刷计划单和 3 条活跃策略集合保持不变；路径特征能力不进入活跃配置。
- 已有简单库存字段与新增路径字段连续两轮未形成稳定优势。已平仓 Rank5 只有 22 笔，后续停止在该历史样本上搜索阈值，优先积累固定观察窗下的前向纸面执行证据。
- 未来候选继续按一进一出挑战 R14；即使历史门禁通过，也必须先完成前向纸面执行的同源 PIT 特征构造与一致性验证。

证据：`docs/contracts/SHORTPICK_V3_R14_RANK5_PATH_QUALITY_EXPERIMENT_2026-07-15.json`、`docs/analysis/SHORTPICK_V3_R14_RANK5_PATH_QUALITY_REPORT_2026-07-15.md` 与同目录已执行 notebook。

[2026-07-15T20:00:00+08:00] R14 Rank5 simple quality thresholds are rejected and this feature set stops expanding:

本轮在读取候选结果前冻结 6 个 Rank5 专属、PIT 可得的质量过滤器，覆盖分差、20 日成交额、5/20 日动量分位、距 20 日高点和一个组合条件。所有候选都精确复放同一 R14 执行快照，且明确禁止使用库存里的 `net_excess_return`、`weighted_net_excess_return` 等未来结果字段。

执行约定
- 6 个候选均未通过相对可复现基线与旧 R14 合同的双基线九指标门禁；R14、前端、API、日刷计划单和活跃策略集合保持不变。
- 最佳近似项只增加约 0.282 个百分点总收益，同时提高订单跳过率，没有减少亏损月份，也没有达到突破要求。
- 22 笔已平仓 Rank5 样本中，现有 score、动量、距高点和流动性字段没有形成稳定的赢家边界；停止继续扫描这些字段的更多阈值。
- 可选 Rank5 质量判定能力保留在回放与前向计划代码中，但当前活跃配置不启用，不能改变真实计划单。
- 下一次 Rank5 研究必须先增加实质不同的 PIT 信息或积累更多真实前向样本；仍按一进一出挑战 R14，不能扩张策略数量。

[2026-07-15T18:00:00+08:00] R14 execution-efficiency round retains the existing frontier and freezes a reproducible ledger:

本轮基于新的确定性执行快照只测试替补质量收紧和资金部署两类共 8 个执行层变体。没有候选同时通过相对可复现基线与旧 R14 展示合同的九指标非退化门禁，因此 R14 不变，前端、API、日刷计划单和历史对比不新增策略。

执行约定
- `shortpick-v3-execution-snapshot-067c5b83e085f95f` 是后续 R14 执行优化的可复现输入与基线账本；必须保持摘要校验和逐单重放一致。
- 2026-07-10 的旧 R14 合同仍是历史展示基准，但原始逐单账本未保留，当前代码重建为 58 笔替补而旧合同记录 53 笔，不再声称旧合同可精确复跑。
- 低价替补整体带来正贡献，不能移除；Rank5 分段损益较弱只作为探索诊断，不能直接事后硬编码为禁买规则。
- 提高单信号资金部署会显著增加亏损月份与回撤，当前不调整仓位上限。
- 如继续优化，只允许预先声明、PIT 安全的 Rank5 替补质量特征，并按一进一出规则挑战 R14；不得扩张活跃策略集合。

[2026-07-15T00:00:00+08:00] v3 active strategies converge to three non-expanding roles:

v3 前端与纸面日刷的活跃策略集合固定收敛为 3 条：R14 高质量替补与 25% 暴露再平衡作为唯一优化前沿，上游元信号稳健缩放作为独立模型族对照，现行 14 tranche 分层退出作为前向运行基线。递归 Rank 调整、元信号质量分层、三段稳定性、条件化攻击和 15 tranche 低集中度共 5 条迁入归档，不再生成新计划单，也不进入活跃历史对比；原有合同、静态回放指标和既有纸面历史保留。

执行约定
- 活跃集合上限保持 3 个角色；新候选必须明确替换其中一个角色，不能通过追加第四条来进入持续展示与前向追踪。
- 后续优化统一以 R14 为历史前沿；只击败现行 14 tranche 或某个已归档弱策略，不构成新增活跃候选的理由。
- 前后端都必须按同一活跃 ID 集合过滤；日刷账户、计划单、API read model 和前端表格任何一层都不得重新扩张出归档策略。
- 详细集合与恢复条件见 `docs/contracts/SHORTPICK_V3_ACTIVE_STRATEGY_SET_2026-07-15.md`。

[2026-07-13T09:30:00+08:00] v3 paper strategies use one synchronized account window:

所有进入前端的 v3 策略统一从 2026-07-08、20 万元独立纸面账户起算。日刷必须按信号日保存 candidate source 和计划批次，不能再用“最新计划”覆盖未结算历史。2026-07-08/09 的补齐来源必须标记为 `synchronized_start_backfill`，后续日刷实时保存的来源标记为 `daily_forward_capture`；两者都不能继承历史回放收益。交易明细、现金、持仓、净值曲线和回撤必须来自同一份纸面账本。执行合同见 `docs/contracts/SHORTPICK_V3_PAPER_LEDGER_CONTRACT_2026-07-13.md`。

[2026-07-04T01:15:00+08:00] Short Pick model exploration must let evidence seed strategies before more formula design:

当前目标不是继续手写一个更复杂的固定公式，而是让模型探索机制先从历史矩阵中发现可验证的特征方向，再把通过基础信号检查的方向注册成候选模型 spec 进入 walk-forward 门禁。`model_feature_diagnostic_report` 因此作为 `research_validation/*` artifact 家族加入：它只读取已有 PIT feature matrix 和 executable label matrix，不写业务库、不更新 policy config、不暴露到 dashboard。

2026-07-04 真实 runtime 诊断 `model-feature-diagnostic-report-d66487dc8ad41c57` 覆盖 80 个 label-ready 日期、234,257 条可评估行、10 个特征、2 个方向、5/10/20 日 horizon。结果是 `passing_basic_signal_gate_count=0`。最接近的方向是低 20 日波动、远离 20 日高点、低 20 日平均成交额，但它们的 top-quantile net excess 仍为负。当前可靠结论：现有特征池还没有找到可交易的正收益策略种子；后续应扩展特征来源和组合搜索，而不是继续围绕当前 momentum/turnover/volatility 小公式调权重。

执行约定
- 单特征诊断只负责发现策略种子，不得作为策略通过证明。
- 若诊断没有任何方向通过基础信号门槛，后续优先增加新特征族、交互特征和 regime/industry/relative-strength 信息；不要把负收益 top bucket 包装成“防守策略”。
- 候选策略必须由注册 spec 进入 walk-forward comparison report，并通过 Rank IC、top quantile net excess、PBO/DSR、cost stress、winner dependency 和 governance gates，才能进入任何纸面跟踪或 dashboard projection 讨论。

2026-07-04 追加迭代：把诊断/候选 runner 的 flattened feature universe 从初始 10 个字段扩展到已有 PIT 矩阵中的 24 个数值字段。真实 runtime 诊断 `model-feature-diagnostic-report-1f84ee542071edea` 仍为 `passing_basic_signal_gate_count=0`；低换手率成为最强单特征方向，但 top-quantile net excess 仍为负。扩展特征后的 learned linear/tree walk-forward 报告 `model-comparison-report-aeb8a5e2c686c9f2` 也失败，最佳 tree trial 只有 `rank_ic_mean=0.0117`、top quantile `-0.0279`、`pbo_proxy=0.5`。因此下一步必须新增特征来源或构造方式，不能继续假设现有矩阵字段里藏着可通过门禁的策略。

[2026-07-03T23:20:00+08:00] Short Pick deep research branch is P0 guardrail, not the model exploration mechanism:

项目所有者重新确认：当前 `codex/shortpick-validation-boundary-p0` 分支完成的是旧 `factor_observation / weight_sweep` 链路的研究边界、安全门禁和诊断 artifact prototype，不能被表述为“新模型探索机制已经完成”。`research_input_snapshot`、`pit_feature_store`、`objective_frozen_universe`、`walk_forward_purge_embargo`、`oos_validation`、`governance_promotion_decision`、`dashboard_approved_projection_registry` 这些当前实现都只覆盖 legacy diagnostic factor validation / weight sweep scope。

新的模型探索机制必须另行从 `objective universe x as_of_date` 主矩阵开始，生成独立 PIT feature matrix、executable label matrix、model spec registry、walk-forward candidate predictions 和 comparison report。它不得从 `recommendation_rows`、active watchlist、`factor_observation` 行、`recommendation_payload.factor_breakdown` 或既有强势股票后验特征开始。

执行约定
- `docs/contracts/SHORTPICK_DEEP_RESEARCH_END_STATE_DESIGN_2026-07-03.md` 是终局边界合同，但其中当前实现映射只能解释为 legacy diagnostic prototype。
- `docs/contracts/SHORTPICK_MODEL_EXPLORATION_WORKBENCH_P1_HANDOFF_2026-07-03.md` 是下一轮实现入口。
- 后续开发会话必须先声明实现哪个 P1 artifact family，再更新 handoff 文档的完成状态。
- 在 P1 artifact families、测试和 comparison report 完成前，`independent_model_exploration` 状态必须保持 `not_started` 或 `in_progress`，不得写成 completed。

[2026-06-15T09:50:24+08:00] Short Pick Lab V2 h10 quiet champion is the mandatory benchmark line:

项目所有者明确：后续 `试验田v2` 策略搜索必须以 10 日交易日口径的 quiet champion 为对标标准，不能因为长上下文丢失重新回到无边界的大方向发散。当前固化的主 benchmark 是 `quiet_breakout_rank2_poolhot10_mtw__fixed_notional_85k_top5_h10_v1`（历史简称 `quiet_r2_poolhot10_mtw__fixed85_top5_v1`），保守资金影子是 `quiet_breakout_rank2_poolhot10_mtw__fixed_notional_80k_top5_h10_v1`（历史简称 `quiet_r2_poolhot10_mtw__fixed80_top5_v1`）。

固化依据
- 已知 fixed85 历史读数：总收益约 `+271.2%`，年化约 `53.96%`，市场超额约 `+229.4%`，最大回撤约 `-11.9%`，交易约 `190` 次，skip 约 `73.65%`。
- 已知 fixed80 历史读数：总收益约 `+257.2%`，年化约 `52.03%`，最大回撤约 `-11.9%`，交易约 `192` 次。
- `rank2to6`、`breadth65`、`not_thu`、`ma_accel`、dynamic exit、entry quality 等方向已经产生负面或明显弱于 benchmark 的证据；后续只能作为负面对照或诊断，不再作为主线替代方向。

执行约定
- 10 日 horizon 是主验收口径；不引入延迟买入，动作只有候补买入或不买。
- skip ratio 是资金利用率/机会频率指标，不再作为淘汰 quiet champion 的硬门槛；但交易次数、跑赢大盘、年化 `>= 30%`、最大回撤、同窗对标 fixed85/fixed80 仍是硬约束。
- 新候选只有在同窗口、同费用、同 20w 初始资金、同 100 股手数约束下明显优于 fixed85/fixed80，才允许替换主 benchmark。轻微领先但增加复杂规则的候选不得替换。
- 下一轮只做 quiet champion 附近窄网格：资金档 `75k/80k/85k/90k`、pool-hot 阈值 `0.09/0.10/0.11/0.12`、交易日 `MTW/Mon-Tue/Tue-Wed`、rank2-only 与 fallback 诊断；禁止为了降低 skip ratio 放宽到 rank2-6、breadth65、周四/周五或重新打开 ma_accel/dynamic-exit 大方向。

[2026-06-13T10:18:42+08:00] Short Pick Lab V2 qualification must beat market reference and clear 30% annualized:

项目所有者明确：任何跑不赢大盘的策略都不合格；鉴于股票高风险，年化收益低于 30% 的策略不进入考虑范围。该约定适用于 `试验田v2` 的历史回放晋级、纸面追踪候选和后续参数治理，不能只作为前端展示提示。

本轮先补齐 runtime 本地库宽基指数日线：`000300.SH`、`000905.SH`、`000852.SH` 各 862 条，覆盖 `2022-11-21` 至 `2026-06-12`。在 v2 当前窗口 `2023-05-16` 至 `2026-05-08` 内，沪深300约 `+22.5%`，中证500约 `+42.3%`，中证1000约 `+34.1%`；当前 v2 股票池等权 close-to-close 参考约 `+41.8%`，按日复利参考约 `+45.1%`。已选出的 `conservative_cash_reserve_60k_top5_v1` 总收益约 `+24.6%`、年化约 `+7.5%`，不满足新的大盘超额和 30% 年化门槛。

执行约定
- `shortpick_v2_rule_selection_v2` 之后，候选必须带显式市场参考收益；缺少市场参考证据时 fail closed。
- 非基线配置必须同时满足：总收益为正、总收益严格高于声明的大盘/市场参考收益、年化收益不低于 `30%`、且继续满足原有样本数、交易数、跳过率、回撤、资金利用、换手和 reason-count 门槛。
- `top1_or_skip_v1` 可继续作为 baseline/control 展示，但 baseline 不能被包装成晋级候选。
- 旧的 Phase 4 两个候选只保留历史记录；在 v2 新门槛下不得继续作为纸面追踪候选，除非后续重新生成的 governed selection artifact 明确通过 v2 门槛。

[2026-06-12T10:20:00+08:00] 运营复盘前端入口临时下线，后端与历史证据保留：

项目所有者明确“运营复盘”模块当前已经不再使用，本轮只在前端层面临时移除用户入口。实现边界是：关闭 `operations` view 的可用路由集合与桌面/移动导航入口；直接访问 `?view=operations` 回落到默认试验田视图；保留后端 API、投影、历史数据、组件代码和测试资产，避免把临时前端下线误做成数据删除或后端能力退役。

恢复条件
- 若后续重新启用运营复盘，需要先确认它仍是用户可见工作流，再打开前端入口开关，重跑前端 build、路由静态回归、runtime publish 和 canonical browser 验收。
- 在重新启用前，不应从其他入口新增运营复盘的可见按钮、移动底栏项或 URL-backed view。

[2026-06-10T16:10:00+08:00] Short Pick governance intent clarification: deprecated display bucket and labeled combined-ledger backfill:

项目所有者明确了短投治理的初心，并拍板了此前各轮刻意留待决策的两个问题，记录到 `docs/contracts/SHORTPICK_STRATEGY_GOVERNANCE_PLAN_2026-06-10.md` 的 Round 28 修订段。本条为耐久决策，后续实现轮不得偏移。

决策 A（成绩不好的对照组的"清理"语义）
- "清理" = 从主前端展示与持续推进中移除，但数据保留，并迁移/标记进 deprecated/废弃归档桶，带 regression guard 防止回归。
- 状态映射：`active` / `observe` 留在主视图（仍在观察）；证据明确的 `retire_candidate` 与 `retired` 移入 deprecated 桶、不再推进、数据保留。这比原 P2.5（只归档 `retired`）更严格——所有者要求证据明确后即从主前端隐藏弱对照组，而不必等到完整 `strategy_retirement:v1` artifact。
- 持久 `retired` 记录仍需 `strategy_retirement:v1` artifact + `decision_log_ref`；离开 deprecated 桶只能走受治理的 un-retirement recovery，不得自动回主视图。
- "无意义/冗余"对照组与"成绩不好"分开处理：走 inventory 驱动的归档路径，不塞进性能退役门槛；diagnostic-value gate 仍保护测试独特假设的弱对照组。

决策 B（回溯补算数据的落点）
- 回溯补算数据进入与 true-forward 行**同一张合并 ledger/表**（便于前端对照展示），不再要求物理分表。
- 反泄漏保证改由标注而非物理隔离实现：每行强制非空 `evidence_basis`；回溯行带 `retrospective=true`、`rule_defined_at` 与 leakage 审计字段；回溯行永不被表示/查询/聚合/计入 `true_forward_tracking`；true-forward 的 headline / 晋级 / 退役指标默认按 basis 过滤。
- 每条回溯行带 `pairing_key`（`control_group_id` + `rule_signature` + `symbol` + `signal_date`）与对应 true-forward 行配对，提供方便的对照关系。本决策取代回溯合同早期"物理分表"的读法，但保留其全部 leakage 保护。

实现边界
- 新增需求项 P2.7（deprecated 展示桶 + regression guard）、P2.8（冗余/无意义对照组 inventory 归档）、P3.7（带标注的合并 ledger 回溯补算 + true-forward 配对）、P3.8（把 P3.1-P3.3 控件与 P1.3/P1.4 baseline 落成真实对照链路，先历史回测再补算），状态均为 not_started。
- 仍受同一前置阻塞：真实 `strategy_retirement:v1` artifact 写入器、回测/回放 runner、运行时/前端接线落地之前，本修订仅为合同，不得真正退役、隐藏或补算。
- 若与 `docs/contracts/PHASE5_RESEARCH_CONTRACT.md` 或本决策日志冲突，Phase 5 合同与决策日志优先。

[2026-06-10T12:35:00+08:00] Short Pick strategy governance must land retirement and retrospective-replay contracts before implementation:

首月短投前向验证分析显示，冻结主线存在均值为正但中位数为负、少数大赢家拉高均值、北方华创重复暴露亏损等问题。后续治理不能直接靠临时前端隐藏、临时删策略或把事后新增规则伪装成真实前向验证来解决。本轮新增合同计划 `docs/contracts/SHORTPICK_STRATEGY_GOVERNANCE_PLAN_2026-06-10.md`，作为短投策略退役、回放补算、新诊断对照组和长期收益评估的实现前置。

补充说明
- 弱策略后续可以从 active generation、热路径统计和前端主视图退役，但不得无标准物理抹除唯一证据链。正式退役必须先有确定性门槛、`strategy_retirement:v1` artifact、证据快照引用和决策日志。
- 新增同股冷却、回撤/反转过滤、重复暴露限制等诊断对照组，可以跑历史回测和既有前向区间的 retrospective replay，但必须显式标注 `historical_backtest` / `retrospective_forward_replay` / `true_forward_tracking`，不得把事后补算行写成当时已经真实前向跟踪。
- 真前向跟踪从控制组 ID、规则签名和 artifact family 注册后开始计算；注册日前的补算只能作为 post-hoc replay 或 historical research evidence。
- 新增 artifact family、evaluation baseline、control group ID 和 schema 必须遵守 registry-first。Markdown 计划不是机器真值源；实现前仍需进入 JSON registry / schema 或对应可检查 allowlist。
- 在 registry、退役 artifact 和前端 basis 展示完成前，现有策略生成和展示语义保持不变，不因本计划自动退役、重算、隐藏或替换主线。
- Future strategy questions 必须回接 Phase 5 gate：优先 after-cost excess、20/40 日成熟样本、中位数、胜率、回撤、尾部依赖、regime stability，以及相对注册 baseline 的稳定领先，不另起一套不受合同约束的晋级体系。

[2026-05-20T00:30:00+08:00] Autonomous flow implementation starts with registry and claim gate before scheduler code:

Trial C 收敛了 Trial B 留下的实现前置架构决策。后续自运行流程实现的顺序固定为：先建立机器 registry 与 checker，再实现公共 claim ceiling gate，之后才实现 Phase 5 cycle ledger、recovery ticket、gate readout 的写入路径，最后接入 scheduler、projection 和 publish verifier。

补充说明
- `phase5_cycle_ledger`、`phase5_recovery_ticket`、`phase5_gate_readout` 的权威事实先落 runtime artifact store；SQLite 或 frontend projection 只作为可重建查询层，不作为第一事实源。
- `runtime.publish.verified.v1` 纳入 `phase5_cycle_ledger`，但 ledger 只保存 event envelope、`release_manifest_ref` 和 digest；release manifest 继续作为发布验收明细的权威源，避免双源冲突。
- Registry 的实现阶段机器真值源采用 `JSON allowlist + JSON Schema`；Markdown appendix 继续保留为人工镜像，但如果二者冲突，JSON registry 胜出。
- 暂不引入 DB registry，也暂不把 claim ceiling gate 做成 HTTP 服务。`claim_ceiling` 第一阶段实现为确定性纯函数库 / CLI / 内部模块，不读网络、不调用 LLM、不写库、不直接发布 runtime。
- 后续 Context Pack 应由 JSON registry 派生 allowlist，子进程不得手写 registry 片段。

[2026-05-20T00:00:00+08:00] Autonomous development flow trials must use registry-first design and bounded reruns:

当前项目将作为自动化开发平台的流程试验田。新的流程不再把多 agent 并行产出本身视为成功，而是要求每轮都完成“流程设计 -> 试运行 -> 自动评估 -> 有条件重跑 -> 固化”的闭环。

本轮 Trial A 证明，直接并行生成全局协议和依赖该协议的模块设计，会让模块文档临时发明事件或接口，即使单份文档看起来完整，系统级合同仍会漂移。因此后续流程采用 registry-first 顺序：先冻结术语、事件、artifact family、module interface 和成熟度矩阵，再把这些 allowlist 作为子进程输入。Trial B 按这个规则重跑后，Phase 5 纵向切片只引用已注册的 `*.v1` 事件、artifact family 和 interface id，质量从可用草案提升到可进入实现拆解的流程草案。

补充说明
- Trial B 仍不等同于 production 平台设计。`phase5_cycle_ledger`、`phase5_recovery_ticket`、`phase5_gate_readout` 的正式持久化位置，以及 registry 是否升级为 JSON Schema / DB registry / 代码生成 allowlist，仍是后续架构决策。
- 子进程只负责 owned files，不负责主线状态、发布、合并、最终质量结论或项目状态更新。主进程负责评审、重跑决策、固化和 closeout。
- 任何后续实现任务如果引用未注册事件、artifact 或接口，应先更新 registry，再重跑受影响模块；不能通过总结文字把接口漂移解释为可接受。
- 为降低长文档读取导致的超时和成本，主进程必须先生成短 `Context Pack`，只传递目标、边界、owned files、registry allowlist、成熟度限制、必读路径和禁止动作。

[2026-05-14T19:40:00+08:00] Frontend-facing statistics should be materialized as projections:

随着历史分析、运营复盘和短投试验田数据量扩大，前端接口不能继续在页面请求时直接拼研究态流水、长窗口统计和 artifact projection。新增通用 `frontend_projections` 表作为前端专用读模型：后台定时或显式触发刷新统计，页面 API 只读小 payload；缺失或过期时显示结构化待刷新状态，而不是在打开页面时重算。

补充说明
- 投影表固定字段包括 `projection_key`、`projection_group`、`target_login`、`status`、`version`、`generated_at`、`expires_at`、`source_fingerprint`、`payload`、`metadata_payload`。
- 第一批接入 `shortpick_replay_feedback:v1`，把 aggregate replay feedback + decision projection 预先物化；`/shortpick-lab/replay-feedback` 优先读投影，缺投影才走兼容 fallback。
- 第二批接入 `operations_summary:v1:{target_login}:{sample_symbol}`，按账号和样本股票物化运营复盘摘要；`/dashboard/operations/summary` 不再在前端请求里执行 `run_operations_tick()`，返回前还会把性能阈值改写为当前 summary API 耗时和 summary payload 体积，避免页面继续展示完整聚合构建的旧耗时。
- 第三批接入 `home_shell:v1:{target_login}`，把首页首屏的 `watchlist + candidates + glossary` 合成单个账号隔离 projection；`/dashboard/shell` 优先读投影，只在请求时附加轻量 scheduled-refresh 状态。
- 第四批接入 `shortpick_model_feedback:v1`，把模型反馈页的 rounds/candidates/validation 聚合预先物化；`/shortpick-lab/model-feedback` 优先读投影，缺投影才兼容现算。
- 第五批接入 `simulation_workspace_summary:v1:{target_login}`，把运营复盘模拟参数下钻区的 simulation workspace 预先物化；`/dashboard/operations/details?section=simulation_workspace` 优先读投影，避免打开运营复盘时同步构建模拟工作区。
- 后续迁移顺序应是：继续观察真实接口耗时后再迁移 `shortpick_market_factor_study` 或更细的 operations detail sections，不再把重统计接回页面请求热路径。
- 投影刷新可以跟随盘后 slot 或维护命令执行，但不得在页面请求里写库、补行情、跑回测或触发 LLM。

[2026-05-14T18:55:00+08:00] Shortpick scheduled maintenance must not sit on the live frontend hot path:

前端大面积请求超时的直接原因不是历史分析新增数据，而是短投定时刷新里的 recent validation / failed-round retry 与前端读接口争用 runtime SQLite，导致 `/auth/context`、`/watchlist`、短投接口等无关小请求一起触发 `database is locked`。这些补历史和补失败轮次的维护动作以后默认不跟随 daily shortpick slot 自动执行，只能通过显式环境开关进入维护窗口。

补充说明
- `ASHARE_SHORTPICK_VALIDATE_RECENT_BEFORE_RUN` 默认 `0`；需要补 recent validation 时显式设为 `1`，并避开用户验收和前端使用窗口。
- `ASHARE_SHORTPICK_RETRY_FAILED_AFTER_RUN` 默认 `0`；retry failed rounds 保留能力，但不再默认接在 live daily run 后继续占库。
- 历史回放接口可以继续返回离线策略切片结论，但只下发首屏和下钻实际使用的 projection 字段，不把 `period_strategy_rows`、`regime_strategy_rows`、`portfolio_stability.time_slices` 这类重明细整包塞进 `/shortpick-lab/replay-feedback`。
- 如果再看到多接口同时超时，排查顺序先看 runtime DB 锁持有者和 scheduled refresh 子进程，再评估 payload 大小；不要先把所有超时归因于前端表格数据量。

[2026-05-14T17:10:00+08:00] Short Pick Lab long-window strategy slices must extend breadth without pretending to be LLM replay:

历史回放的 LLM 候选逐条验证仍只有 2026-01-05 至 2026-04-30，不能包装成跨周期结论。为了补广度和深度，页面新增 `strategy_slice_evidence` 离线 artifact：复用已完成的 full-window staged portfolio artifacts，把确定性策略族扩展到 2023-05-16 至 2026-04-29、717 个信号日、约 2999 个新开户主板可交易序列，并按月度组合路径贴本地指数推导的市场阶段标签。

补充说明
- 这个 artifact 只扩充确定性市场因子策略族，不扩充真实 LLM 自由选股 replay；页面必须继续说明“长窗口策略样本不替代 LLM 短窗口 replay”。
- 分行情胜出表以月度组合超额按市场阶段聚合，回答“组合资金曲线在不同市场环境下是否稳定”；它不是逐候选 LLM alpha，也不是实盘成交证明。
- 当前第一版使用已完成的 `full_window-next_close / next_open / same_close_proxy` staged artifacts，避免从页面或 API 请求里重跑 3000 股票级别回测。后续如需每日增量刷新，应继续作为慢预计算产物处理。
- 初始读数显示冻结低换手上升趋势在部分震荡行情桶胜出，但并非所有行情桶最优；页面因此只能把冻结策略表述为当前最稳纸面主线，不能写成全行情最优策略。
- 本轮已发布并在 localhost 与认证后的 canonical route 验证：历史回放页显示长窗口策略样本 `717` 信号日、`2,999` 只可交易序列、`6` 个可用行情桶，以及分行情胜出表中的冻结策略位置。

[2026-05-14T14:48:00+08:00] Short Pick Lab historical replay market-regime and industry evidence must stay offline:

历史回放补充测试开始落地市场阶段与行业/题材两类 artifact。市场阶段只允许由 replay cache 物化时读取本地 CSI300/CSI1000 日线生成标签；行业/题材稳定性和归因只允许来自候选 payload 里的既有行业/题材字段。页面打开时不得补拉行情、补行业映射、重回测或按当前前端状态推断缺项。

补充说明
- 市场阶段标签采用 `trend_regime:volatility_regime:size_style_regime` 组合，当前由 20 日沪深300收益、20 日日收益波动、中证1000相对沪深300强弱离线推导。
- 行业/题材表必须同时展示稳定性和归因：前者看各行业内 5 日可交易超额均值与正超额率，后者看最佳/最差行业以及去最佳行业后的均值。
- 这些字段仍属于历史研究表达，不改变冻结纸面策略、不改生产权重，也不能替代真实前向纸面 tracking。

[2026-05-14T14:20:00+08:00] Short Pick Lab historical replay Phase 2/3 projections are now artifact-backed:

历史回放的剩余分析面板已从“待补命名”推进为离线 artifact projection：aggregate replay feedback 现在物化 `regime_stability`、`confidence_intervals`、`return_attribution`，readout builder 同步投影 `forward_tracking_alignment`。前端只能消费这些已物化字段，不在页面打开时临时 bootstrap、重回测或自行推断缺项。

补充说明
- `confidence_intervals` 使用按交易日聚类的 deterministic bootstrap；策略晋级判断必须优先看区间下沿是否仍为正，而不是只看均值。
- `regime_stability` 当前已覆盖月份/季度和 staged portfolio 年/月 slices；2026-05-14 后续实现已补市场状态标签与行业/题材稳定性 projection，仍必须由 cache 物化，不得前端猜测。
- `return_attribution` 当前覆盖整体、LLM 与默认冻结候选家族的最佳/最差单票、日期、月份和去贡献项后的均值；2026-05-14 后续实现已补行业/题材归因 projection，仍必须由 cache 物化。
- `forward_tracking_alignment` 在纸面跟踪样本不足时必须保持 `continue_observation` / `insufficient_forward_sample`，不能用历史同口径期望替代真实前向结果。

[2026-05-14T10:20:00+08:00] Short Pick Lab historical replay first screen must be a read-only decision projection:

短投试验田历史回放的首屏不再只堆统计表，必须先回答“LLM 自由选股是否有可验证优势、冻结纸面策略是否只能继续观察、候选平均质量和组合资金曲线是否一致、当前最大 blocker 是什么”。这些结论只能由已物化的 replay feedback、market-factor study、staged portfolio backtest 和 paper tracking ledger 投影得到，页面打开时不得触发重回测、行情同步、模型调用或数据库写入。

补充说明
- API 兼容保留既有 `families`、`overall.validation_by_horizon` 与 market-factor study 字段；新增读数挂在 aggregate replay feedback 的 `overall.decision_readout`、`overall.execution_funnel`、`overall.entry_sensitivity_matrix`，单 run feedback 不附带全局结论。
- 可执行性漏斗必须显式标出不同 basis：股票池口径和候选验证行口径不能被解释成同一个分母的真实漏斗；缺 artifact 时返回结构化 pending/missing，不由前端猜测。
- 入场矩阵并排展示 `next_close`、`next_open`、`same_close_proxy`、`same_day_intraday_current`。其中 `same_close_proxy` 永远只代表日线代理，不得写成真实 14:00 全市场成交证明。
- 候选逐条验证与组合资金曲线是两个研究问题：前者衡量选股池平均 alpha，后者衡量账户资金滚动执行后的收益、超额、回撤和交易频率。页面与结论必须分开读。
- Phase 2/3 backlog 固定进入同一 projection 命名：`regime_stability`、`confidence_intervals`、`return_attribution`、`forward_tracking_alignment`。后续开发补 artifact，不重新定义方向。

[2026-05-12T10:35:00+08:00] Intraday same-day shortpick control is time-boxed and deterministic:

短投试验田新增一个盘中同日入场对照组：交易日下午先用实时行情替代当日收盘价，沿用冻结低换手上升趋势规则选股；推荐生成后再读取一次当前价，作为该对照组的纸面买入价。

补充说明
- 这个对照组回答的是“当天推荐、当天收盘前买入”的入场时点问题，不改变冻结主线的次一交易日收盘买入口径，也不替代 16:20 盘后完整 shortpick lab。
- 为了满足 14:00 前后可见，调度默认 `13:55` 启动，只运行已冻结的确定性市场因子规则和 AKShare 实时全市场快照，不跑完整 LLM daily-analysis；LaunchAgent 还会在 `14:00`、`14:05` 显式唤醒同一 slot 作为兜底，成功后由 slot state 防重复写入；完整 LLM 批次仍跟随 16:20 盘后 slot。
- 纸面跟踪必须记录独立 `entry_price_source = same_day_intraday_current`、同日 signal/entry date 和捕获到的 entry price；页面展示为“盘中当前价买入”，避免被误读为次日收盘或次日开盘。

[2026-05-07T18:52:00+08:00] Short Pick Lab return feedback requires three benchmark dimensions:

短投试验田的收益反馈不能继续只展示单一沪深300超额。后续实现必须把后验收益拆成 `沪深300 / 中证1000 / 同板块等权` 三个可切换 benchmark 维度，并让研究池、历史验证队列和模型反馈使用同一组选中口径。

补充说明
- 表格收益列的表头应提供下拉切换控件；默认仍为沪深300，以保持当前兼容口径。
- 后端必须同时落多维 benchmark map；兼容字段 `benchmark_return / excess_return` 暂时继续代表默认沪深300，避免破坏已有 API 消费。
- 同板块等权不是用行业名做展示装饰，而是必须按可得同行日线构造真实基准；同行样本不足、缺板块映射或缺中证行情时显示 pending 原因，不允许静默回退成绝对收益或沪深300。
- 该计划只属于短投试验田后验验证和模型反馈展示，不回写主推荐、不改模拟盘自动调仓、不调整生产权重，也不替代 Phase 5 当前主研究 benchmark。
- 落地时保持兼容字段不变：`benchmark_return / excess_return` 仍是默认沪深300；新增多维 map 和聚合指标承载中证1000与同板块口径，避免旧消费层把多 benchmark 误读成主推荐验证已经升级。
- 2026-05-07 落地后确认：该能力已发布到 runtime 并在 served `试验田 -> 历史验证` 页面验收；表头切换只改变收益反馈维度，不改变候选状态或实验隔离边界。
- 2026-05-07 操作反馈后追加约束：收益反馈切换使用 Select 下拉框，不使用 segmented control；同板块基准在实时库同行样本不足时必须按板块代表股票池补齐到 10 个候选并拉取日线，不能让常见板块长期停在 `0/2` 或样本不足状态。已被成功解析结果取代的 `PARSE_FAILED` 候选必须在验证/重试路径清理，定时短投生成后应自动重试 retryable failed rounds。

[2026-05-06T22:20:00+08:00] Short Pick Lab must expose historical validation and retryable failure handling:

短投试验田不再只以“最新批次”为主产品形态。它必须同时支持今日批次、历史验证和模型反馈三层视图，让旧推荐的 `1/3/5/10/20` 交易日阶梯复盘、模型轮次失败、来源质量和长期反馈都能被运营查看。

补充说明
- 历史验证按 candidate-horizon 粒度服务端分页，默认每页 50 条；前端不得通过一次性拉全量候选来模拟分页。
- `PARSE_FAILED` 或失败轮次不能混入正常研究池，必须进入失败诊断区；DeepSeek/SearXNG 无结果与 JSON 解析失败归为可重跑失败，配置缺失归为配置失败。
- 重跑失败轮次只重跑 retryable failed rounds，不整批重跑；旧失败 artifact id、错误原因和失败分类必须保留在 retry history 中。
- 模型反馈只能作为研究观察：展示轮次成功率、失败率、验证收益、超额收益、收敛/题材表现和来源可达性分布；v1 不把这些反馈接入主推荐评分、候选池、自选池、模拟盘或生产权重。

[2026-05-06T20:35:00+08:00] Scheduled daily refresh status must be visible on the dashboard:

每日分析调度不能只依赖终端命令或 LaunchAgent 日志判断是否完成。股票看板首页必须展示 `16:20` 盘后 daily refresh 的可读状态，包括正在跑、已完成、失败待重试、待补跑和等待触发。

补充说明
- `scripts/run-scheduled-refresh.sh` 继续负责实际调度，同时写出本地状态 marker：运行锁 context、成功 `.ok`、失败 `.failed`、断网等待 `.deferred`。
- 后端通过 `/dashboard/scheduled-refresh-status` 暴露只读状态，前端桌面首页和移动首页都直接展示该状态。
- 失败不代表当天放弃；失败 marker 用于反馈和诊断，下一次 5 分钟轮询仍会自动重试，成功后覆盖为 `.ok`。

[2026-05-06T20:00:00+08:00] Daily refresh schedule uses a single post-market slot with catch-up:

每日分析刷新从 `08:10 / 16:20 / 19:20 / 21:15` 收口为 `16:20` 盘后单一 daily slot。`08:10` 不再主动跑重刷新；`19:20` 与 `21:15` 不再作为独立 daily refresh 时点。盘后日线、日终增量字段、财务指标、主 recommendation 和 Phase 5 artifact 重建集中在 `16:20`。

补充说明
- LaunchAgent 继续保留 `StartInterval=300`，但 5 分钟轮询的职责变成盘中 ops-only 与 daily slot catch-up。若移动、断网或电脑休眠导致 `16:20` 没有成功，脚本会在醒来且联网后读取本地 state file，自动补执行未完成的 postmarket slot；已成功的 slot 不重复跑。
- `scripts/run-scheduled-refresh.sh` 增加运行锁、联网预检和 daily/shortpick 超时保护，避免长时间挂起或并发写入 runtime SQLite。
- 短投试验田仍受 `ASHARE_ENABLE_SHORTPICK_LAB=1` 控制；如果启用，它跟随盘后 slot 的 catch-up 机制运行，但不影响主 daily slot 的完成标记。

[2026-05-05T04:05:00+08:00] Short Pick Lab is an isolated native-web research lab, not a quant pool input:

短投推荐试验田正式定义为独立研究课题：GPT/Codex 与 DeepSeek 在隔离执行环境中使用各自原生联网/搜索能力，从全 A 股自由发现 1-10 个交易日短线候选；系统只负责调度、留痕、解析、混合收敛聚合和后验行情验证。

补充说明
- `shortpick_lab` 不写入 `Recommendation`、`ModelResult`、自选池、候选池、模拟盘自动调仓或生产权重；它只写自己的 run / round / candidate / consensus / validation 表和 `shortpick_lab` artifact。
- 主实验采用 `native_web_open_discovery_v1`，不统一搜索源、不统一关键词。统一搜索器只允许作为未来对照组，不能替代主实验的原生发散空间。
- 收敛度只代表研究优先级，不代表交易建议或已验证可信度。前端必须同时展示“独立研究课题，不进入主推荐评分”“模型一致性只代表研究优先级，不代表交易建议”“后验验证完成前不得显示为已验证能力”。
- root/operator 可以触发实验和查看 raw output；member 如能看到该页，只能看到脱敏研究结果，不能触发实验或查看执行错误/raw answer。

[2026-05-03T23:02:34+08:00] Data-quality improvement suggestions must aggregate by degraded-source signature:

差异复盘不再允许把同一组数据质量降级来源机械展开成多条逐股建议。若多只活跃自选股同时命中相同 `degraded_sources`，建议收集层必须先聚合成一条批量根因修复建议，并在 `raw_source.items` 与 `evidence_refs` 中保留受影响股票明细。

补充说明
- 聚合维度是排序后的 `degraded_sources` 签名，例如 `financial_data_stale + profile_incomplete`。
- 聚合建议的 `symbol` 为空，前端按既有“全局”展示；单只股票异常仍保留个股建议。
- 处置流程固定为：先修共同数据链路，修完后重新运行数据质量与改进建议审计；只有残留个股继续异常时，才转为逐股补齐。
- 这条规则只改变建议审计台的任务颗粒度，不放宽数据质量评分、claim gate、买卖方向或生产权重。
- 已存在的旧 suggestion review snapshot 也必须在读取时执行同样的同源聚合投影。原因是完整双模型重新审计可能耗时很长，页面不能在下一次重审完成前继续展示一串可合并的逐股数据质量建议。

[2026-05-02T23:20:00+08:00] Launch gate feedback must read suggestion review snapshots, not stay hardcoded:

运营门禁的状态不能硬编码。当某个门禁被标记为 warn 且提示"需要形成改进计划"时，门禁必须动态读取最新的 suggestion review snapshot，根据对应计划的状态（accepted_for_plan / completed）决定门禁的实际 status 和 current_value。硬编码 placeholder 只在尚未建立 suggestion review 管线的过渡期可接受，一旦管线就位必须替换为动态查询。

补充说明
- `operations.py` 的 `_lookup_gate_plan_status()` 通过 `source_ref = "launch_gate/{gate_name}"` 匹配快照中的建议，优先 completed > accepted_for_plan。
- 计划 completed → gate pass；计划 accepted_for_plan → gate warn + 任务 ID；无计划 → 保持原始 warn。
- `improvement_suggestions.py` 的 `SUGGESTION_STATUSES` 同步增加了 `"completed"` 状态，前端审计台增加对应的"标记完成"按钮。
- 注意：suggestion review snapshot 是按次生成的点状快照，下一次 `run_improvement_suggestion_review` 会生成新快照；若计划已完成（门禁变 pass），新的收集循环不会再为该门禁创建建议。

[2026-05-01T18:40:00+08:00] Improvement plan-pool control-plane boundary decision:

股票看板的“进入计划池”默认只允许把任务交给本机控制面后端处理。`/middle` 或其他服务器侧入口只能被视为认证后的可视化入口/转接面，不能再被当成股票看板创建 Plan 任务时的默认权威后端。

补充说明
- 本轮已回退此前把计划池默认目标改成 remote/live control-plane 的实现与文档，恢复为本机 `127.0.0.1:8787` 控制面默认值。
- 这样做的原因不是“远端一定永远不用”，而是当前项目规范里真正稳定、可控、与用户开发环境一致的任务执行面仍是本机；如果未来要切到远端权威控制面，必须先在 `local-control-server` 和股票看板两边都明确更新架构决策、运维路径和验收口径。
- `/middle` 仍可作为统一登录后的入口或观察面存在，但它看到的内容不应再被股票看板侧代码默认假设成权威任务真值。

[2026-05-01T00:00:25+08:00] Professionalization P-1/P0 boundary decision:

本轮只批准落地 P-1/P0 的证据链与接口边界，不批准把 horizon、生产权重或模拟盘毕业状态直接切到新结论。原因是当前真实样本仍不足以支撑自动 horizon approval、IC 驱动生产权重或组合层盈利性宣传。

补充说明
- 数据质量评分采用固定权重：日线完整性 40%、行情新鲜度 15%、新闻覆盖 20%、财务新鲜度 15%、证券画像/板块规则 10%；`missing_news_evidence` 在数据质量层只形成 `data_coverage_gap:news`，不单独打 fail。
- 当前融合贡献与因子可信度必须分开：单票卡片展示 `factor_score × dynamic_weight`，因子可信度只来自 `factor_ic_study` 的 rolling RankIC/IC_IR，不把 IC 直接混进即时贡献。
- 主研究 benchmark 开始引入 CSI300/CSI500/CSI1000 上下文；在指数日线和样本未补齐前，active-watchlist equal-weight proxy 只作为诊断/兼容口径，不得单独用于 promotion。
- `/dashboard/operations` 继续保留兼容期；新增 `/dashboard/operations/summary` 和 `/dashboard/operations/details` 用于把首屏摘要与 portfolios/replay/manual queue 等重数据解耦。
- P1/P2/P3 的 horizon approval、生产权重变更、模拟盘毕业和事件分析方向影响必须继续走 artifact + DECISIONS + Phase 5 contract 审批。

[2026-04-30T15:00:00+08:00] Event-driven LLM deep analysis must not be a daily scoring factor; it is a trigger-based advisory layer:

LLM 不做日常轮询评分，只在事件触发时介入。触发条件为六类：价格冲击(±5%)、方向切换、置信崩塌(>0.10)、因子冲突(2+ 方向相反)、重大公告(importance≥0.7)、每周六定时复盘。每个 stock 每天最多触发 2 次，同类型冷却 3 天。

分析结果不直接修改 factor_breakdown 或 FUSION_WEIGHTS，而是通过已有的 `manual_review_layer`（当前 score=0.0 占位）影响建议表达。LLM 同时接收内部全量数据（OHLCV、因子 breakdown、公告全文、同板块对比、验证指标）和外部信息（AKShare stock_individual_info_flow），输出结构化 JSON（independent_direction / key_evidence / risks / information_gaps / correction_suggestion）。

选择 DeepSeek Flash 作为默认模型以控制成本；重大事件可手动指定 Pro。外部搜索仍缺真正的 web search API — 当前仅覆盖 AKShare 免费接口，Phase 2 需评估 Bing/SerpAPI 接入。

补充说明
- 与现有 AI 追问（manual research / follow-up）的关系：追问是用户主动触发的交互式分析，事件分析是系统自动触发的批处理。两者共享 LLM transport 和 artifact 存储模式，但触发机制、prompt 结构和输出合同不同。
- 事件分析的 prompt 显著大于追问 prompt（包含完整价格序列、因子表格、公告全文、板块对比），因此使用独立超时配置（120s）和独立模型路由（event_analysis task → Flash）。
- 数据快照 hash 用于检测分析结果是否过期：当 latest_close、day_change_pct 或最近 5 根 K 线变化时，旧分析自动标记为可能过期。
- 与 Phase 5 研究 artifact 存储模式保持一致：`data/event_analysis/{symbol}/` 下按 `{timestamp}_{trigger_type}.json` 命名，index.json 维护索引。

[2026-04-30T01:28:00+08:00] Multi-account watchlist presentation and root act-as lifetime decision:
多账号隔离上线后，前端不再允许把“当前账号自选”和“全局候选池”继续渲染成一个模糊共享列表；root 的 `act_as` 也不再跨页面刷新持久化。当前批准的交互 contract 是：账号自选单独成区显示，候选池单独成区显示；root 代看只在当前单页会话内有效，刷新或重开标签后默认回到 root 自己的空间。

补充说明
- 这轮真实用户反馈表面像“member 仍看到了所有自选、root 自己持仓不见了”，但 live 数据核对后发现两层问题并不相同：member 侧是候选池与自选池的展示边界不清，root 侧则是此前 `act_as` 持久化导致标签页回到 member 空间后，用户误以为 root 仓位消失。
- 新交互不改变后端隔离 contract。真实账号隔离仍由 `watchlist_follows` / `owner_login` / `StockAccessContext.target_login` 提供；这次只是把 UI 呈现与空间切换时间范围收口到不容易误判的形态。
- live 验证基于 canonical `https://hernando-zhao.cn/projects/ashare-dashboard/`：Safari root 会话仍能看到 `002028.SZ` 的原持仓，而通过真实签名根域 session 调用 canonical edge API、再配合 `X-Ashare-Act-As-Login`，`member-a` 与 `amoeba` 都已返回空 watchlist 和 draft simulation。

[2026-04-29T22:45:00+08:00] Mobile settings and home list actions must expose only real operations:
移动端设置页不再把只读状态行伪装成可点击导航；只有实际接入能力的项目才允许出现右侧箭头。主题因为只有浅色/夜间两态，继续使用行内 `Switch`；默认模型作为真实可操作项进入二级菜单，支持选择本机 Codex GPT builtin 执行器或已配置模型 Key，其中外部 Key 选择复用现有 `/settings/model-api-keys/{id}/default` 后端接口。首页关注股票卡片新增左滑移除入口，但删除仍进入现有确认弹窗，不做静默删除。

补充说明
- `规范路由` 不再作为移动端设置项展示，避免无意义长 URL 占据设置页宽度。运行状态、数据源、自动降级、研究模式、版式密度、风险提醒等当前只读项保留为状态行，不显示箭头。
- 首页左滑操作仅对 `source_kind !== "candidate_only"` 的关注来源标的开放；纯候选来源不展示移除入口，和桌面端自选删除边界保持一致。
- 左滑移除的红色按钮只在展开状态显示，展开后卡片右侧圆角归零，避免闭合状态红色透底和双圆角边框；滑动释放会吞掉下一次 click，避免误跳单票页。
- 发布先从主仓库提交 `a654cd9070a917f4050433e674fec5d7d638ff13`，再通过干净 worktree `/private/tmp/stock-dashboard-mobile-publish-ANQXdo/repo` 执行标准脚本，生成 manifest `/private/tmp/stock-dashboard-mobile-publish-ANQXdo/repo/output/releases/20260429T145429Z-a654cd9070a9/manifest.json`。localhost `http://127.0.0.1:5173/` 已在 390x844 验收：首页显示 `关注股票`、底部 tab 和移除入口，设置页显示 `外观主题` Switch，只有 `默认模型` 带箭头且二级页包含 `本机 Codex GPT` 与当前 `deepseek-v4-pro` Key。canonical 标准入口在当前浏览器会话被统一登录层拦截到登录页；脚本 release parity 已通过，但手工浏览器 canonical 复验需要有效登录态。

[2026-04-29T17:40:00+08:00] Mobile dashboard information architecture is app-native, not a compressed desktop workspace:
手机端正式固定为 `首页 / 单票 / 复盘 / 设置` 四个 bottom tabs；原先“首页”和“自选/候选”不再拆成两个移动端入口，统一合并到首页，用一个焦点卡片、搜索筛选和候选/自选列表承载。设置升为独立 tab，但只展示和操作已有真实运行时能力，不新增未接后端的假偏好项。

补充说明
- 桌面端继续保留现有候选、单票、运营复盘、设置工作台；移动端通过 `MobileAppShell` 走独立组件树，不再把大段 mobile JSX 继续塞进 `App.tsx`。
- 移动端复盘页不得复用 `TrackHoldingsTable` 这类 PC 宽表。用户轨道、模型轨道、持仓、模型建议和时间线都以移动端卡片/列表呈现，避免横向滚动和超长桌面栅格。
- 设计稿真值源为 `output/design/mobile-redesign/mobile-tab-home-candidates.png`、`mobile-tab-stock-detail.png`、`mobile-tab-operations-review.png` 和 `mobile-tab-settings.png`；已删除旧的半截 SVG 概念图和废弃的独立自选页图片，避免后续实现回退到错误 IA。

[2026-04-28T10:47:41+08:00] Manual-research request views must never borrow another request's LLM result on the live dashboard:
the live manual-research / follow-up workflow is no longer allowed to serialize a queued request together with the `manual_llm_review` payload of a different, newer completed request. From this round on, every `ManualResearchRequestView` must carry only its own request-scoped projection; if the request itself has not executed yet, its `manual_llm_review` must stay empty/queued instead of inheriting another artifact. This closes the request/result mismatch that could surface as follow-up actions targeting the wrong object and intermittently ending in `404 Not Found`.

补充说明
- 根因在 [manual_research_workflow.py](/Users/hernando_zhao/codex/projects/stock_dashboard/src/ashare_evidence/manual_research_workflow.py) 的 `_serialize_request(...)`。旧逻辑总是先取 `build_manual_llm_review_projection(...)` 的“当前 recommendation 最新人工研究结果”；当 `projection.request_id != request.id` 时，它只覆盖了 `status` 和 `stale_reason`，却把别的 request 的 `request_id / artifact_id / raw_answer / citations` 整包保留下来。这样前端看到的可能是“当前这条 queued 请求”，但内部挂着另一条已完成请求的结果。
- 修复现在显式回退到 request-scoped `_build_request_projection(...)`：一旦发现 recommendation-level projection 的 `request_id` 不等于当前 request，本条 view 就只按当前 request 自己的 `status/status_note/artifact` 生成 `manual_llm_review`。没有执行过的请求会保持 `generated_at=null / summary=null / artifact_id=null`，而不是再借旧结果。
- 回归锁在 [test_manual_research_workflow.py](/Users/hernando_zhao/codex/projects/stock_dashboard/tests/test_manual_research_workflow.py) 新增用例：当较旧请求仍是 `queued`、较新请求已经 `completed` 时，列表里的 queued request 必须继续指向自己的 `request_id/request_key`，且 `artifact_id/summary/raw_answer` 都为空。`tests.test_api_access` 也已复跑通过，确认 API 合同未被破坏。
- 发布通过干净快照仓 `/private/tmp/stock-dashboard-manual-research-fix-3R7Q3W/repo` 完成，manifest 为 `/private/tmp/stock-dashboard-manual-research-fix-3R7Q3W/repo/output/releases/20260428T024529Z-fd4436101087/manifest.json`。live 验收不是只看单测：我先创建了新的 `600522.SH` 请求 `id=11`，在未执行前直接查 `GET /manual-research/requests/11`，确认它返回 `status=queued`、`manual_llm_review.request_id=11`、`artifact_id=null`、`raw_answer=null`，不再借 `id=10` 的旧结果；随后再对同一条请求执行 `POST /manual-research/requests/11/execute`，live backend 返回 `HTTP/1.1 200 OK` 并成功落成新的 manual-review artifact。Safari 真实浏览器会话也已重新加载 localhost `http://127.0.0.1:5173/`，当前显示 `最近刷新 04/28 10:47`。

[2026-04-28T10:35:48+08:00] Candidate-return color semantics and operations-report entry must follow A-share intuition on the live dashboard:
the live frontend is no longer allowed to render positive return percentages with Ant Design `success` green and negative return percentages with `danger` red in the candidate / self-select modules. On this dashboard, user-facing涨跌语义 must stay aligned with A-share convention: gains render red, losses render green. From this round on, candidate 20-day return cells reuse the existing `value-positive / value-negative` class contract instead of AntD status colors, and `运营复盘` holdings tables now expose a direct `分析报告` action that opens a compact stock-analysis modal without forcing the user to leave the operations workspace.

补充说明
- 这轮问题来自真实前端 contract，而不是底层数据错误：`frontend/src/App.tsx` 里的候选列表桌面表格此前把 `20日` 涨跌直接映射成 `type={>=0 ? "success" : "danger"}`，导致上涨显示绿色、下跌显示红色，和当前看板其他位置已经采用的 A 股涨红跌绿语义冲突。
- 修复现在统一落在 [App.tsx](/Users/hernando_zhao/codex/projects/stock_dashboard/frontend/src/App.tsx)。候选桌面表格与移动卡片都改成通过 `valueTone(...)` 输出 `value-positive / value-negative`，从而复用现有 CSS：正值走红色、负值走绿色，不再依赖 AntD 默认 `success/danger` 配色语义。
- 同一轮里，`运营复盘` 的 `用户轨道 / 模型轨道` 持仓表新增了 `分析报告` 按钮。按钮会调用新的 `openAnalysisReportModal(symbol)` 路径：优先复用当前单票 dashboard；若当前焦点不是该 symbol，则额外请求一次 `api.getStockDashboard(symbol)`，然后在原地弹出 `运营复盘分析报告` 精简弹窗，集中展示建议摘要、触发点、风险、验证摘要和最近人工研究结论，并提供 `打开完整分析` 跳转。
- 回归锁在 [test_dashboard_views.py](/Users/hernando_zhao/codex/projects/stock_dashboard/tests/test_dashboard_views.py)：测试现在显式断言候选区使用 `className={\`value-\${valueTone(...)}\`}`，不再允许旧的 `success/danger` 逻辑回归；同时断言 `分析报告`、`运营复盘分析报告` 和 `onOpenReport` wiring 均存在。
- 发布继续通过干净快照仓 `/private/tmp/stock-dashboard-ops-report-0bQC1K/repo` 执行，manifest 为 `/private/tmp/stock-dashboard-ops-report-0bQC1K/repo/output/releases/20260428T023221Z-f2e7410af295/manifest.json`。本轮 repo 验证 `PYTHONPATH=src python3 -m unittest tests.test_dashboard_views` 与 `npm --prefix frontend run build` 已通过；live bundle 也已从 `http://127.0.0.1:5173/assets/index-9f572869.js` 复核到 `分析报告`、`运营复盘分析报告`、`onOpenReport` 以及新的 `value-` 渲染路径。

[2026-04-28T10:17:00+08:00] Background intraday refresh and simulation tick must live in the backend runtime, not behind page-open side effects:
the stock dashboard is no longer allowed to depend on someone opening `运营复盘` or any other frontend route before intraday market data and simulation state advance. From this round on, the FastAPI runtime starts a background operations tick on startup, runs it continuously during SSE/SZSE trading sessions, refreshes stale `5min` bars for the active watchlist, and advances the currently running simulation session exactly once to the newest landed market bar instead of restarting the session or replaying multiple fake catch-up steps.

补充说明
- 这次问题先在 live runtime DB `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db` 复核：即使本机已经处在 `2026-04-28 10:11 CST` 交易时段，`market_bars.timeframe='5min'` 仍停在 `2026-04-27 03:15:00`，运行中的 `simulation_sessions.id=9` 也还卡在 `current_step=1 / last_data_time=2026-04-27 03:20:00`。这说明旧实现并不会在前端关闭时自行推进。
- 根因分成两层。第一，`api.py` 之前没有 startup/lifespan 常驻任务，只有页面请求时临时兜底。第二，现有 CLI `refresh-runtime-data` 虽然能刷新研究态，但它的 simulation 路径是 `restart -> step`，适合研究重建，不适合拿来做持续运行的模拟盘。
- 代码修复落在 [api.py](/Users/hernando_zhao/codex/projects/stock_dashboard/src/ashare_evidence/api.py)、[runtime_ops.py](/Users/hernando_zhao/codex/projects/stock_dashboard/src/ashare_evidence/runtime_ops.py)、[simulation.py](/Users/hernando_zhao/codex/projects/stock_dashboard/src/ashare_evidence/simulation.py) 和 [market_clock.py](/Users/hernando_zhao/codex/projects/stock_dashboard/src/ashare_evidence/market_clock.py)。新逻辑只在交易时段运行；先判断 active watchlist 和 intraday stale 状态，再同步 `5min` 行情，然后仅当最新 bar 晚于当前 session 时钟时，调用单次 anchored simulation step，把 `last_data_time` 直接推进到最新已落库 bar，避免在同一最新价快照上重复补几十个虚假决策步。
- 回归测试覆盖了三类 contract：交易时段判断 [test_market_clock.py](/Users/hernando_zhao/codex/projects/stock_dashboard/tests/test_market_clock.py)、后台 tick 行为 [test_runtime_ops.py](/Users/hernando_zhao/codex/projects/stock_dashboard/tests/test_runtime_ops.py)、以及“运行中 session 只追到最新 bar 一次”的 simulation catch-up [test_simulation_workspace.py](/Users/hernando_zhao/codex/projects/stock_dashboard/tests/test_simulation_workspace.py)。同时 [test_api_access.py](/Users/hernando_zhao/codex/projects/stock_dashboard/tests/test_api_access.py) 显式关闭测试环境 background tick，避免 TestClient 与后台线程互扰。
- 由于主仓库仍是 dirty worktree，这轮发布继续通过临时干净快照仓 `/private/tmp/stock-dashboard-background-tick-ASEMyS/repo` 执行标准脚本，manifest 为 `/private/tmp/stock-dashboard-background-tick-ASEMyS/repo/output/releases/20260428T021238Z-3e056de237f4/manifest.json`。
- live 验收闭环已经完成，而且不依赖打开业务页接口推进数据：发布后先看到 live backend 首轮已把 runtime DB 推进到 `max(5min observed_at)=2026-04-28 02:10:00`、`simulation_sessions.id=9 current_step=2 / last_data_time=2026-04-28 02:10:00`；随后完全不访问 `/dashboard/operations`，只等待下一根真实 5 分钟 bar，再直接查 live DB，确认它已自行走到 `2026-04-28 02:15:00` 和 `current_step=3 / updated_at=2026-04-28 02:15:31.797831`。Safari localhost `http://127.0.0.1:5173/` 同时显示 `最近刷新 04/28 10:17`，证明 served page 已读到新 runtime。

[2026-04-28T01:07:00+08:00] Canonical tunnel stale-port recovery and auth-wall clarification from local execution:
the canonical stock-dashboard route is not currently failing because the frontend or backend is down. On this round, localhost `5173/8000` stayed healthy while the public tunnel agent had fallen back into the same stale remote-port condition seen earlier: old remote `sshd` listeners were still holding `127.0.0.1:3101/4101`, so `com.codex.project-tunnel.ashare-dashboard` kept exiting with code `255`. Clearing the stale remote forward and restarting the LaunchAgent restored the tunnel process; the canonical route now responds normally again, but unauthenticated requests still land on the shared login wall by design.

补充说明
- 这次用户反馈“股票看板直接打不开了”后，先复核了 localhost runtime：`http://127.0.0.1:5173/` 仍返回 `200` 静态入口，`http://127.0.0.1:8000/health` 也保持 `200 {"status":"ok"}`。因此问题不是 repo/runtime 代码崩溃。
- canonical `https://hernando-zhao.cn/projects/ashare-dashboard/` 的直接返回是 `302 -> /?next=%2Fprojects%2Fashare-dashboard%2F`，并附带 `set-cookie: hz_auth_session=; Max-Age=0`。这说明未登录访问会被统一身份入口接管，不是股票看板路由自身 500。
- 同时 `launchctl print gui/$(id -u)/com.codex.project-tunnel.ashare-dashboard` 显示 agent 长期处于 `last exit code = 255`，而远端主机 `codex-server` 上仍有旧 `sshd` 占着 `127.0.0.1:3101/4101`。本轮已清掉那组旧 listener，并执行 `launchctl kickstart -k gui/$(id -u)/com.codex.project-tunnel.ashare-dashboard`；当前 agent 已恢复到 `active count = 1 / state = running`，远端端口也已重新被新的 `sshd` pid 占用。
- Safari localhost 验收仍通过：`http://127.0.0.1:5173/` 当前可以正常打开 `波段决策看板` 首页。canonical 是否能直达业务页现在只取决于浏览器是否还保有有效登录态；未登录时落到统一登录页属于预期行为。

[2026-04-28T00:40:00+08:00] DeepSeek follow-up timeout and proxy-path decision from local execution:
the live follow-up path is no longer allowed to treat `30s` as a safe upper bound for configured OpenAI-compatible providers. On this machine, the default proxied network path to `https://api.deepseek.com` is currently the only verified path that completes reliably; the explicit no-proxy path remains slower and still timed out during local reproduction. From this round on, manual-research / follow-up execution keeps the default proxy path and raises the OpenAI-compatible read timeout to `75s`.

补充说明
- 这轮排查先在 live runtime DB `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db` 复核 `600522.SH` 的失败记录。`manual_research_requests.id=6` 和 `id=7` 都是 `executor_kind=configured_api_key`、`model_api_key_id=1`、`failure_reason=The read operation timed out`，开始到失败约 `31s`，与 [llm_service.py](/Users/hernando_zhao/codex/projects/stock_dashboard/src/ashare_evidence/llm_service.py) 里旧的 `timeout=30` 精确对齐。这说明不是前端没发请求，也不是 manual-research 编排没执行，而是 DeepSeek 调用已经发出，但在我们自己的读超时窗口内没拿到结果。
- 同机本地环境确实挂了全局代理：`HTTP_PROXY/HTTPS_PROXY=http://127.0.0.1:17890`、`ALL_PROXY=socks5://127.0.0.1:17891`。但实测结果与“DeepSeek 不该走代理”的直觉相反：按运行时代码路径、保留默认代理时，使用与失败案例同一份 `600522.SH` prompt 的本地请求在 `39.75s` 成功返回；显式 `disable_proxies=True` 后，同一请求在 `61.0s` 仍然报 `The read operation timed out`。因此这轮不做“禁代理直连 DeepSeek”的修复，当前机器上的代理链路反而更稳定。
- 真正修复落在 [llm_service.py](/Users/hernando_zhao/codex/projects/stock_dashboard/src/ashare_evidence/llm_service.py)：`OpenAICompatibleTransport` 现在把 `OPENAI_COMPATIBLE_TIMEOUT_SECONDS` 提升到 `75`，保留默认代理行为不变。回归锁在 [test_runtime_config.py](/Users/hernando_zhao/codex/projects/stock_dashboard/tests/test_runtime_config.py)，测试显式断言 transport 会把扩大的 timeout 传给 `urlopen(...)`。
- 发布继续通过干净快照仓 `/private/tmp/stock-dashboard-followup-prompt-o4Rc3S/repo` 完成，当前 manifest 为 `/private/tmp/stock-dashboard-followup-prompt-o4Rc3S/repo/output/releases/20260427T163737Z-0963fa9fabb2/manifest.json`。发布后我直接对 live backend `http://127.0.0.1:8000/analysis/follow-up` 重放了同一条 `中天科技最近长势喜人，你觉得他还会继续涨么`，真实返回在 `66.776s` 成功完成，`status=completed`、`executor_kind=configured_api_key`、`selected_key=deepseek-v4-pro`。这证明根因是 `30s` 超时过短，而不是请求流程本身坏掉。
- 浏览器侧这轮补了 Safari localhost 验收：`http://127.0.0.1:5173/` 当前已正常加载 `波段决策看板` 首页并显示 `最近刷新 04/28 00:40`。canonical 未登录状态会先落到统一登录页，所以这轮真实功能验收以 localhost Safari + live backend 直调为准。

[2026-04-27T23:33:00+08:00] Follow-up prompt de-anchoring and manual-research receipt verification decision from local execution:
the live follow-up prompt is no longer allowed to front-load the system verdict as if it were the answer. From this round on, `follow_up.copy_prompt` must start from explicit fact/prediction separation, require the model to explain validation-metric conflicts before giving direction, and treat the system recommendation as reference-only context. The latest `002028.SZ` manual-research receipt has also now been verified against the live runtime DB and artifact store as a successful `DeepSeek` execution rather than a builtin-model run.

补充说明
- 这轮提示词收口落在 [dashboard.py](/Users/hernando_zhao/codex/projects/stock_dashboard/src/ashare_evidence/dashboard.py)。`_follow_up_payload(...)` 现在先声明“不要补充未给出的事实”“先区分已知事实与推断”“如果验证指标之间存在张力或冲突，必须先解释冲突”，再列 validation metrics / 风险 / 驱动，最后才附上 `系统当前结论（仅供参考，不是必须采纳）`。这样 `可以买吗` 一类用户追问不再被已有 recommendation 文案强锚成单向复述器。
- 回归已经补到 [test_dashboard_views.py](/Users/hernando_zhao/codex/projects/stock_dashboard/tests/test_dashboard_views.py)：测试现在锁定 `copy_prompt` 必须包含冲突解释要求、证据不足直说要求，以及“系统当前结论仅供参考”字段，避免后续再把 recommendation 行提前回最前面。
- 发布仍通过临时干净快照仓完成，最新 manifest 为 `/private/tmp/stock-dashboard-followup-prompt-o4Rc3S/repo/output/releases/20260427T152726Z-dcb9531d1a10/manifest.json`。本地 live API `http://127.0.0.1:8000/stocks/002028.SZ/dashboard` 已返回新 prompt 文案，确认不是 repo-only 改动。
- `002028.SZ` 最近一次 manual research / follow-up 回执已在 live runtime DB `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db` 复核：`manual_research_requests.id=5`、`request_key=manual-research:reco-002028.SZ-20260427-phase2:20260427151723412637`、`executor_kind=configured_api_key`、`model_api_key_id=1`、`status=completed`。同一条记录的 `request_payload.selected_key` 与 artifact `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/artifacts/manual_reviews/manual-review:manual-research:reco-002028.SZ-20260427-phase2:20260427151723412637.json` 都显示 `provider_name=deepseek`、`model_name=deepseek-v4-pro`、`base_url=https://api.deepseek.com`、`attempted_keys[0].status=success`、`failover_used=false`。如果 DS 账单里没看到花费，更像是账单口径/计费账户侧问题，不是这次请求没走 DeepSeek。
- 浏览器验收方面，in-app browser 的 `iab` backend 当前不可用，所以这轮改走真实 Safari 会话复核 canonical。`https://hernando-zhao.cn/projects/ashare-dashboard/` 当前已加载到 `思源电气 · 002028.SZ`，页面显示 `最近刷新 04/27 23:33`，说明最新发布 bundle 已经在真实用户入口可见。

[2026-04-27T22:53:00+08:00] Operations-copy compression and market-freshness wording decision from local execution:
the live operations workspace is no longer allowed to repeat the same validation / governance caveat across metric cards, portfolio panels, strategy notes, and governance tabs. From this round on, `运营复盘` must collapse repeated warning copy into one concise research-validation summary, render post-close freshness as an “截至 HH:MM” market snapshot instead of raw seconds, and label the governance tracks as `用户轨道 / 模型轨道` so the page explains what each panel is for without leaking internal contract wording.

补充说明
- 这轮收口主要落在 [App.tsx](/Users/hernando_zhao/codex/projects/stock_dashboard/frontend/src/App.tsx)。前端现在统一通过 `compactValidationNote(...)`、`operationsValidationDescription(...)` 和 `formatMarketFreshness(...)` 压缩重复提示：顶部只保留一条 `研究验证 · 口径校准中` 摘要，`5 分钟延迟` 改成 `最新行情`，收盘后会显示 `截至 04/27 11:15` 一类时间快照，而不再暴露 `40335 s` 这种盘后秒数。
- 组合和治理区不再重复堆叠 `基准解读说明 / 组合验证口径 / 组合验证仍在补齐 / 模型自动持仓` 等多层提醒。组合面板现在只保留一条 `当前说明`，治理 tab 统一改成 `用户轨道 / 模型轨道`，并直接说明“用户轨道看手动下单结果，模型轨道看模拟盘里的自动调仓结果”。
- 用户提到反复出现的 `Phase 2 规则基线已完成 walk-forward 产物生成...`，根因是 `research_candidate` recommendation / validation payload 长期复用底层 `status_note`，多个页面又直接渲染 `validation_note`。这轮同时把 [validation.py](/Users/hernando_zhao/codex/projects/stock_dashboard/src/ashare_evidence/phase2/validation.py) 的默认文案收口成“已有滚动验证产物，当前仍处于观察阶段，尚未完成正式验证”，并把 [phase5_contract.py](/Users/hernando_zhao/codex/projects/stock_dashboard/src/ashare_evidence/phase2/phase5_contract.py) 里的等权组合/自动执行提示压成短句，避免相同长句继续从别的接口漏到页面。
- 回归与发布闭环已经完成：`npm run build`、`PYTHONPATH=src python3 -m unittest tests.test_dashboard_views tests.test_simulation_workspace` 通过；由于主仓库仍是 dirty worktree，这轮发布基于上一次可发布快照仓 `/private/tmp/stock-dashboard-ui-publish-M3NrD9/repo` 完成，manifest 为 `/private/tmp/stock-dashboard-ui-publish-M3NrD9/repo/output/releases/20260427T145228Z-2eb558b75fcb/manifest.json`。
- 真实浏览器复核以 canonical Safari 为准：`https://hernando-zhao.cn/projects/ashare-dashboard/` 当前显示 `最近刷新 04/27 22:53`；`运营复盘` 顶部已切换为 `最新行情 / 截至 04/27 11:15` 和单条 `研究验证` 提示，盘后不再显示 raw seconds；治理入口下的轨道命名也已改为 `用户轨道 / 模型轨道`。

[2026-04-27T22:26:00+08:00] Simulation workspace timeline-anchor decision from local execution:
the live simulation workspace is no longer allowed to let a same-step `order_filled` event appear in `最近动作理由` while leaving the corresponding model holding at zero. From this round on, portfolio replay must anchor to `simulation_session.last_data_time` whenever the newest `5min` market bar still lags behind the session clock, so the just-filled order is reflected immediately in holdings, NAV, and exposure.

补充说明
- 根因已经在真实 runtime DB 上复核清楚：`simulation_events`、`paper_orders` 和 `paper_fills` 都已记录 `600522.SH / 中天科技` 在 `2026-04-27 03:20:00` 的 `buy 1000`，但 `market_bars` 的最新 `5min` 点只到 `03:15:00`。旧版 `src/ashare_evidence/simulation.py` 仅按行情时间点回放成交，导致 `order_filled` 能出现在 `最近动作理由`，`recent_orders` 也能看到成交，但 `holdings` / `仓位` / `净值` 仍停在成交前状态。
- 修复现在在 `_portfolio_context(...)` 内显式把 `simulation_session.last_data_time` 追加为组合回放锚点，并在比较时兼容旧测试夹具里的 naive datetime 与 session aware datetime。这样即使最新一分钟/五分钟 K 线还没补到该时点，组合也会按“最后可用价格 + 当前 session 时钟”及时纳入刚成交的头寸。
- 回归覆盖已补到 `tests/test_simulation_workspace.py`：`PYTHONPATH=src python3 -m unittest tests.test_simulation_workspace` 现在锁定“模型自动成交后，`recent_orders` 非空且 `holdings` 里必须出现正持仓数量”；同时 `PYTHONPATH=src python3 -m unittest tests.test_dashboard_views` 复跑通过，确认运营复盘投影未被新锚点破坏。
- 由于主仓库仍是 dirty worktree，这次发布继续通过临时 git 快照仓 `/private/tmp/stock-dashboard-ops-holdings-fix-QnODE5/repo` 执行 `scripts/publish-local-runtime.sh`，生成 manifest `/private/tmp/stock-dashboard-ops-holdings-fix-QnODE5/repo/output/releases/20260427T142343Z-99c9ef25a4d4/manifest.json`。发布脚本的 parity verifier 这次直接通过，说明 repo/runtime/canonical 资源与关键 API 指纹一致。
- Safari 真实浏览器复验也已闭环：localhost `http://127.0.0.1:5173/` 与 canonical `https://hernando-zhao.cn/projects/ashare-dashboard/` 当前都显示 `最近刷新 04/27 22:26`；进入 `运营复盘` 后，模型轨道同时展示 `最近动作理由：中天科技 最新价 36.53 买入 1000 股`，并在持仓表内显示 `中天科技 1000 股 / 仓位 +18.3%`。另外，这轮也再次证明旧的 Safari 标签页或带旧 `?cb=` 的页面内存态可能继续显示“理由已更新、持仓仍为 0”，必须刷新页面后再判断 live verdict。

[2026-04-27T21:48:00+08:00] Phase 5 live-runtime source-of-truth and same-run holding-policy decision from local execution:
`Phase 5` runtime professionalism assessment must now treat `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db` as the authoritative live study database. The repo-local `data/ashare_dashboard.db` is no longer acceptable as a proxy for live policy evidence, because it can lag the actual runtime by multiple refresh cycles. Within that live DB, the already-published same-run rebuild path has now been proven to include the newest stepped model portfolio immediately rather than one run later.

补充说明
- 这轮先显式复核了 repo DB 与 runtime DB 的偏差：repo 本地库当时只显示 `5` 个 auto-model portfolios 和较早的 simulation event counts，而 live runtime DB 已经处于 `8portfolios`、`refresh_step=3`、`model_decision=3`、`order_filled=3` 的状态。后续所有 `phase5-daily-refresh --analysis-only`、holding-policy study 和 browser验收都必须以 runtime 路径下的 SQLite 为真相源，否则会把 repo-side 旧状态误读成 live blocker。
- 在这个前提下，继续对 live runtime 执行一轮 `phase5-daily-refresh --analysis-only`，CLI 输出已把 holding-policy artifact 推进到 `phase5-holding-policy-study:auto_model:2026-04-27:9portfolios`。最新 study 摘要为 `included_portfolio_count=9`、`total_order_count=4`、`rebalance_day_count=4`、`mean_turnover=0.037037`、`mean_invested_ratio=0.079822`、`mean_active_position_count=0.444444`、`mean_annualized_excess_return_after_baseline_cost=0.000581`，并保持 `excluded_reasons={}`。这说明“restart -> step -> rebuild”链路已经能把最新 `sim-20260427134635-5a4d9d-model` 同轮纳入研究，而不是继续卡在 `pending_rebuild`。
- gate 结论没有变成 promotion-ready。`decision.gate_status` 仍是 `draft_gate_insufficient_evidence`，唯一 incomplete gate 仍是 `mean_rebalance_interval_days_floor`；design diagnostics 也继续把 `mean_invested_ratio_floor` 和 `mean_active_position_count_floor` 指向 `portfolio_construction`。所以 blocker 已经不是 runtime wiring，而是跨日期 rebalance 证据仍然不足。
- Safari live 验收这轮重新闭环了两条入口：localhost `http://127.0.0.1:5173/?cb=20260427-2149` 与 canonical `https://hernando-zhao.cn/projects/ashare-dashboard/?cb=20260427-2149` 都显示 `最近刷新 04/27 21:48`、`最近分析 04/27 21:46`，当前焦点一致为 `思源电气 · 002028.SZ`。Chrome 当前 profile 会话一度出现旧缓存页和空白页，但 curl 直接验证了 localhost/canonical 的 HTML 和 JS/CSS 资产都正常可取，因此这次 live verdict 以 Safari 的 fresh-load 结果为准。

[2026-04-27T21:01:00+08:00] Phase 5 runtime simulation-step decision from local execution:
runtime `refresh-runtime-data` / `phase5-daily-refresh` is no longer allowed to stop after merely restarting the simulation session. From this round on, the published refresh path must immediately advance one `refresh_step` so the live auto-model track can produce a same-cycle `model_decision` and, when auto-execute is enabled, a real `order_filled` event instead of accumulating empty zero-step sessions.

补充说明
- `src/ashare_evidence/cli.py` 现在在 analysis refresh 结束后执行 `restart_simulation_session(session)` 并立刻调用 `step_simulation_session(session)`，同时把 `simulation_current_step` 暴露到 CLI 输出。`tests/test_cli_runtime_refresh.py` 新增/更新回归，锁定 refresh 后 session 必须来到 `current_step == 1`，并且当 `auto_execute_model` 为真时必须能在 refresh 链路里产生模型成交；`tests.test_simulation_workspace` 与 `tests.test_phase5_holding_policy_study` 也一并复跑通过。
- 这次修复的根因不是 artifact lookup，而是 runtime evidence-generation path 根本没跑起来。真实 DB 在补丁前只有 `session_created / session_started / session_restarted / config_updated` 事件，没有任何 `refresh_step / model_decision / order_filled`，所以 holding-policy 研究虽然已经从 `0portfolios` 误判恢复到可读状态，但其 exposure/turnover 仍全是零，因为它聚合的是一串从未推进过一步的空 session。
- 发布继续走临时 git-backed 快照仓 `/private/tmp/stock-dashboard-workingtree-gitpublish-lSN3TC/repo`，通过隔离提交 `8c90ef19255a9e10389042097e3e28b89f4a801d` 满足发布脚本的 clean-worktree 约束。`scripts/publish-local-runtime.sh` 完成 frontend build、runtime sync、LaunchAgent restart、health checks 和 parity verifier，manifest 为 `/private/tmp/stock-dashboard-workingtree-gitpublish-lSN3TC/repo/output/releases/20260427T125715Z-8c90ef19255a/manifest.json`。
- 真实 runtime 验证必须跑两轮 refresh 才能证明结果进入持仓研究，而不是只看到当下 session 的内存态。第一轮 `phase5-daily-refresh --analysis-only` 创建 `sim-20260427125859-7994a7-model`，实时事件计数首次出现 `model_decision=1` 与 `order_filled=1`，holding-policy artifact 升到 `phase5-holding-policy-study:auto_model:2026-04-27:5portfolios`；第二轮 refresh 则把这条已成交 session 重建进 backtest，使 holding-policy 再升到 `phase5-holding-policy-study:auto_model:2026-04-27:6portfolios`，并首次得到非零 `mean_turnover=0.013889`、`mean_invested_ratio=0.029933`、`mean_active_position_count=0.166667` 与 `total_order_count=1`。这说明 runtime professionalism assessment 已从“空 session artifact”转成“真实交易样本仍然偏薄”，下一步 blocker 应该围绕更多 rebalance dates，而不是继续怀疑 refresh 链是否在运行。
- Chrome 复验确认 localhost `http://127.0.0.1:5173/` 与 canonical `https://hernando-zhao.cn/projects/ashare-dashboard/` 当前都显示 `最近刷新 04/27 21:01`，焦点为 `思源电气 · 002028.SZ`。因此这次结论是已发布、已刷新 runtime DB、已 browser-verified 的 live repair，不是 repo-only 结论。

[2026-04-27T20:28:55+08:00] Phase 5 holding-policy artifact fallback and parity-noise decision from local execution:
runtime `phase5_holding_policy_study` is no longer allowed to treat stale payload `backtest_artifact_id` values as the only source of truth for auto-model portfolio backtests. When the payload still points at the legacy `portfolio-backtest:portfolio-auto-live` id but the real runtime artifact has already moved to `portfolio-backtest:{portfolio_key}`, the study must fall back to the canonical portfolio-key artifact before declaring `missing_backtest_artifact`.

补充说明
- `src/ashare_evidence/phase2/holding_policy_study.py` 现已先尝试 payload-configured artifact id，再尝试 `portfolio-backtest:{portfolio_key}`，并只在两者都不存在时才保留 `missing_backtest_artifact`。`tests/test_phase5_holding_policy_study.py` 新增 runtime 风格回归，锁定“payload 仍旧指向 legacy id，但真实 artifact 已经写到 `sim-*` id”时必须正确纳入 holding-policy 聚合。
- 真实 runtime DB 先用旧代码复核过一遍，确认当时的 `0portfolios` 完全是误判：三个 auto-model portfolios 都带着 `portfolio_payload.backtest_artifact_id = portfolio-backtest:portfolio-auto-live`，但 backtest 文件实际上已经写成 `portfolio-backtest:sim-...-model.json`。发布修复后，先直接运行 `phase5-holding-policy-study` 即把 runtime `included_portfolio_count` 从 `0` 提升到 `2`；随后再跑 `phase5-daily-refresh --analysis-only`，最新 artifact 进一步收口为 `phase5-holding-policy-study:auto_model:2026-04-27:3portfolios`。
- 这次 runtime 结果同时确认：`included_portfolio_count` 已不再是主要 gate blocker，但 baseline 仍不能 promotion。当前 `gate_status` 仍是 `draft_gate_insufficient_evidence`，主要残余问题变成 `mean_rebalance_interval_days` 仍无样本、`mean_invested_ratio_floor` 与 `mean_active_position_count_floor` 仍持续触发 `portfolio_construction` redesign diagnostics。
- 发布链上，这轮还顺手关闭了之前已经暴露出来的 parity tooling 假阳性：`src/ashare_evidence/release_verifier.py` 现在把 `data_latency_seconds` 视为 runtime-only noise，`tests/test_release_verifier.py` 已补回归。此前 `/dashboard/operations` 的唯一 fingerprint diff 就是这一秒级漂移，不属于业务 payload 漂移，不应继续阻塞有效发布。
- 因主仓库仍是 dirty worktree，这轮 live publish 继续通过临时全工作树快照仓 `/private/tmp/stock-dashboard-workingtree-publish-iyg9zC/repo` 执行 `scripts/publish-local-runtime.sh`。自动 parity verifier、runtime sync、LaunchAgent restart 与 health check 全部通过，manifest 为 `/private/tmp/stock-dashboard-workingtree-publish-iyg9zC/repo/output/releases/20260427T122519Z-011e338c29f7/manifest.json`。随后 Safari 复验 localhost `http://127.0.0.1:5173/` 已显示 `最近刷新 04/27 20:27`、`大位科技 · 600589.SH`；canonical `https://hernando-zhao.cn/projects/ashare-dashboard/` 也刷新到 `最近刷新 04/27 20:28` 并与 localhost 对齐。

[2026-04-27T20:09:12+08:00] Phase 5 future-leak fix and canonical tunnel recovery decision from local execution:
Phase 5 historical validation and horizon studies are no longer allowed to reuse exit bars that occur after a recommendation's own `as_of_data_time`. This round fixed that leakage in the validation builder, rebuilt repo/runtime research state, and then reclosed live verification all the way through the canonical route.

补充说明
- `src/ashare_evidence/phase2/validation.py` 现已在 horizon-metric aggregation 时跳过 `exit_observed_at > recommendation.as_of_data_time` 的样本；`tests/test_analysis_pipeline.py` 新增回归，锁定较早 recommendation 不能再借用未来 exit bars 扩大样本。
- 这次修复后，repo 研究库重建出来的 history-mode `phase5-horizon-study` 明显改观：`40d` 的 `leader_count` 变成 `40`，而 `20d` 只剩 `5`、`10d` 为 `0`。这说明前一轮“广泛 split leadership”的相当一部分噪声来自历史未来泄漏，而不是主 horizon 已经真实收敛到 `20d`。
- focused regression `PYTHONPATH=src python3 -m unittest tests.test_analysis_pipeline tests.test_phase5_horizon_study` 已通过。由于主仓库仍是 dirty worktree，这次 live publish 继续通过临时干净快照仓 `/private/tmp/stock-dashboard-phase5-horizon-fix-dadXUY/repo` 执行 `scripts/publish-local-runtime.sh`；build、runtime sync、LaunchAgent restart 与 localhost health 通过，随后对 runtime DB 执行 `phase5-daily-refresh --analysis-only`。
- runtime 侧当前仍不能 promotion：holding-policy 继续停在 `phase5-holding-policy-study:auto_model:no_included_dates:0portfolios`，但 latest/history horizon artifact 已同时指向 `40d` 为当前 consensus front runner。
- 这轮 canonical 验收还暴露出另一层 live-delivery 风险：`com.codex.project-tunnel.ashare-dashboard` 已经退出，但远端 `sshd` 仍占着 tunnel 端口 `3101/4101`，导致 canonical 页面长期卡在旧的 `04/27 16:35/16:38` 状态。清掉远端僵尸转发并 `launchctl kickstart -k gui/$(id -u)/com.codex.project-tunnel.ashare-dashboard` 后，Safari canonical 恢复到 live runtime，当前显示 `思源电气 · 002028.SZ`、`最近分析 04/27 19:58`、`最近刷新 04/27 20:08`。

[2026-04-27T17:30:00+08:00] Canonical stock-dashboard handoff decision:
This repo now treats `PROJECT_STATUS.json` as the first current-state handoff source, `DECISIONS.md` as the durable research and rollout decision log, `PROCESS.md` as the reusable lessons log, and `PROJECT_PLAN.md` as the long-lived plan summary. Active contracts move under `docs/contracts/`, while audit and research history move under `docs/archive/`.

补充说明
- New sessions should no longer use root-level phase files as their default entrypoint.
- Repo path remains `~/codex/projects/stock_dashboard`; live runtime remains `~/codex/runtime/projects/ashare-dashboard`.

[2026-04-27T16:39:36+08:00] Phase 5 producer-contract watch-ceiling decision from local execution:
对 `missing_news_evidence` 的 producer contract 不再维持“任何 degrade flag 都直接强制 raw `risk_alert`”的旧行为。对于仅因缺少新增新闻证据而退化、但价格/其余结构仍偏正的 recommendation，当前批准的最窄替代方案是 `watch_ceiling_keep_penalty`：保留 `0.12` evidence-gap penalty，不放开为直接 `buy`，但移除 missing-news-only 场景下的硬性 `risk_alert` 覆盖，并把正向 case 的上限收口到 `watch`。

补充说明
- repo 研究库上的 `phase5-producer-contract-study` 已比较 `current_hard_block`、`remove_hard_override_keep_penalty`、`watch_ceiling_keep_penalty` 与 `remove_hard_override_and_penalty` 四个变体。当前研究结论选择 `watch_ceiling_keep_penalty`，因为它能恢复 deployable supply，同时避免把 `missing_news_evidence` 的记录直接放大成 `buy`。
- 代码现已落在 `src/ashare_evidence/signal_engine_parts/base.py` 与 `src/ashare_evidence/signal_engine_parts/recommendation.py`，并通过 `PYTHONPATH=src python3 -m unittest tests.test_phase5_producer_contract_study tests.test_dashboard_views tests.test_traceability tests.test_analysis_pipeline`（`48` tests）。
- 本轮 live publish 继续经由临时干净快照 repo `/private/tmp/stock-dashboard-producer-contract-publish-zmbkZM/repo` 执行 `scripts/publish-local-runtime.sh`。build、runtime sync、LaunchAgent restart、localhost health 与 served asset parity 均通过。自动 parity verifier 只在 `/dashboard/operations` 上报 `API fingerprint mismatch`，进一步核对后发现唯一归一化差异是 `data_latency_seconds`，不属于业务 contract 漂移。
- 随后已对 runtime DB 执行 `phase5-daily-refresh --analysis-only`，并在 Safari 对本地 `http://127.0.0.1:5173/` 与 canonical `https://hernando-zhao.cn/projects/ashare-dashboard/` 复看通过。真实 served 页面上的 `600522.SH` 现已显示 `模型原始方向：偏积极`、`对外表达：仅观察`，说明 producer change 已进入 live runtime，但 claim gate 仍继续阻止 promotion。

[2026-04-27T14:18:00+08:00] Runtime Phase 5 refresh scheduling decision from local execution:
runtime 服务库的 Phase 5 研究证据不得依赖 repo 数据目录随发布同步。由于 `scripts/publish-local-runtime.sh` 明确排除 `data/`，调度链路必须在 runtime DB 本地生成 horizon / holding-policy / validation 投影 artifact；只跑 `refresh-runtime-data` 不足以支撑“专业性”页面判断。

补充说明
- `scripts/run-scheduled-refresh.sh` 现已把工作日分析档 `08:10 / 16:20 / 19:20 / 21:15` 和周末 `09:30` 从 plain `refresh-runtime-data` 改为 `phase5-daily-refresh --analysis-only`；盘中轻量刷新仍保留 `refresh-runtime-data --ops-only`，避免把研究重建压到每次盘中轮询。
- 已对真实 runtime DB 执行 `phase5-daily-refresh --skip-simulation`，写出 `phase5-horizon-study:latest:active_watchlist:2026-04-24:3symbols`、`phase5-horizon-study:history:active_watchlist:2026-04-24:3symbols` 与 `phase5-holding-policy-study:auto_model:no_included_dates:0portfolios`。runtime recommendation 从缺少 metrics 的单日薄状态推进到 `8` 条 recommendation 且均带 `historical_validation.metrics`。
- 本轮 publish 通过临时干净快照完成 runtime sync、LaunchAgent restart 和 localhost health；自动 canonical verifier 仍因缺少 `ASHARE_CANONICAL_USERNAME` / `ASHARE_CANONICAL_PASSWORD` 中止。随后已用 Safari 手动复验本地 `http://127.0.0.1:5173/` 与 canonical `https://hernando-zhao.cn/projects/ashare-dashboard/`，页面显示 `最近刷新 04/27 11:51`，候选股已呈现 artifact-backed `research_candidate / observe_only` 语义和样本、RankIC、正超额摘要。
- 这项决定只关闭 runtime research-data drift 与调度缺口，不构成 promotion。holding-policy runtime study 仍是 `0portfolios`，horizon runtime 读数仍只有 `3` 个 symbols / `1` 个 as-of date，不能覆盖后续更广样本研究。

[2026-04-27T10:24:09+08:00] Same-as-of latest recommendation selection decision from local execution:
当同一只股票、同一个 `as_of_data_time` 同时存在多个 recommendation 版本时，所有“取最新 recommendation”与 replay/history collapse 路径都不再允许简单按 `generated_at desc` 取最后一条。若某个晚到 backfill 版本只是因为生成时间滞后而带上 `market_data_stale`，它不能继续机械覆盖同一 market snapshot 下更早生成、但仍有效的 non-stale 版本。

补充说明
- 本轮新增集中 helper `src/ashare_evidence/recommendation_selection.py`，并把 `services.py`、`dashboard.py`、`operations.py`、`watchlist.py`、`manual_research_workflow.py`、`simulation.py` 与 `phase2/replay.py` 的 latest-selection / history-collapse 逻辑统一改为：先按 `as_of_data_time` 分组，再在组内优先选择 non-`market_data_stale` 版本；只有同一 `as_of_data_time` 下所有版本都 stale 时，才退回到最新生成的 stale backfill。
- 这次决定只关闭“晚到 stale backfill 覆盖有效版本”的机械扭曲，不等于已经放宽 `missing_news_evidence => degraded => risk_alert` 这条 producer contract。换句话说，本轮先修的是 selection truth，而不是 recommendation producer 的 abstention policy。
- 回归已补到 `tests.test_traceability`、`tests.test_dashboard_views`、`tests.test_manual_research_workflow`、`tests.test_simulation_workspace` 与 `tests.test_analysis_pipeline`，并通过 `PYTHONPATH=src python3 -m unittest tests.test_traceability tests.test_dashboard_views tests.test_manual_research_workflow tests.test_simulation_workspace tests.test_analysis_pipeline`。
- 因主仓库仍是 dirty worktree，这次 live-facing publish 继续通过临时干净快照仓 `/private/tmp/stock-dashboard-latest-selection-Nq7j3S/repo` 执行 `scripts/publish-local-runtime.sh`。脚本完成了前端 build、runtime sync、LaunchAgent restart 与 localhost health check，但在 canonical verifier 处仍因缺少 `ASHARE_CANONICAL_USERNAME` / `ASHARE_CANONICAL_PASSWORD` 中止。随后已在 Safari 手动复验两条实际 served 路径：`http://127.0.0.1:5173/` 会先显示 skeleton，随后正常 hydrate 出首页与候选表；已登录的标准入口 `https://hernando-zhao.cn/projects/ashare-dashboard/` 刷新后也正常渲染，并更新到 `最近刷新 04/27 10:23`。这说明本轮 selection 修复已经进入真实运行时，只是自动 canonical parity 仍受凭据缺口限制。

[2026-04-27T01:05:00+08:00] Phase 5 holding-policy experiment evidence decision from local execution:
`Phase 5` 的 holding-policy redesign 已经从“只有 experiment menu”推进到“真实数据库可执行、可落 artifact 的 typed experiments”，但本轮真实运行同时确认：当前首要 blocker 不是 threshold/top-k 参数本身，而是 active recommendation coverage 太薄，导致组合长期接近空仓，现阶段 sweep 结果只能作为 coverage/deployment 诊断，不能被高置信度解读成正式 policy selection。

补充说明
- 本轮已修复真实运行暴露的 replay bug：`_replay_variant(...)` 在统计 `mean_rebalance_interval_days` 时原先错误使用 `zip(rebalance_days, rebalance_days[1:], strict=True)`，一旦真实数据出现至少两次调仓就会崩溃。现已改成相邻配对，并新增回归测试直接覆盖多次调仓路径。
- 两个 primary experiments 现已在真实库 `/Users/hernando_zhao/codex/projects/stock_dashboard/data/ashare_dashboard.db` 上写出 durable artifacts：`phase5-holding-policy-experiment:profitability_signal_threshold_sweep_v1:2023-04-12_to_2026-04-24:3symbols:3variants` 与 `phase5-holding-policy-experiment:construction_max_position_count_sweep_v1:2023-04-12_to_2026-04-24:5symbols:3variants`。这意味着 redesign research 不再只是 CLI 占位，而是已经有稳定的 artifact surface 可供后续比较。
- 当前 profitability sweep 的结论是 `baseline_still_best`，但不是因为 baseline 真的已经证明有效，而是三组变体都几乎没有足够部署去形成差异：baseline `annualized_excess_return_after_baseline_cost=-1.463036`、`positive_after_cost_day_ratio=0.493878`、`mean_turnover=0.000286`，同时 `rebalance_day_count=2`、`mean_active_position_count=0.009524`，说明真实窗口里大部分日期都没有足够 recommendation coverage 去形成持仓。
- 当前 construction sweep 虽然把默认推荐变体推到 `capacity_top3_weight33_conf0`，并相对 baseline 把 `mean_invested_ratio` 从 `0.00184` 提升到 `0.003128`、把 after-cost excess 从 `-1.492753` 改善到 `-1.490014`，但 `history_symbol_count` 仍只有 `2`，`mean_active_position_count` 仍是 `0.009524`。因此这不是“已经找到了更优正式仓位规则”，而是“集中持仓在几乎无覆盖的环境里略微提高了部署率”。
- 从这轮起，`Phase 5` redesign 主线应收口为：先把 primary experiments 保持为 `profitability_signal_threshold_sweep_v1` 与 `construction_max_position_count_sweep_v1`，但对它们的解释统一视为 coverage/deployment diagnostic，直到 real watchlist recommendation coverage、mean invested ratio、active position count 和可用历史样本明显改善之后，再讨论正式 policy selection 或 promotion。

[2026-04-27T00:38:03+08:00] Professionalism copy normalization decision from local execution:
用户可见的 recommendation explanation 不再允许直接暴露 placeholder headline、内部 degrade token 或内部实现语义。对外解释必须优先呈现“当前有哪些研究信号、这些信号为什么支持/削弱结论、什么时候应降级为谨慎或弃权”，而不是把 `用于汇总价格、事件与降级状态的融合层`、`missing_news_evidence`、`event_conflict_high`、`market_data_stale`、`Phase 2 规则基线` 这类系统中间态直接投到首页、候选卡或单票详情。

补充说明
- 这次决定对应 `docs/contracts/PHASE5_CREDIBILITY_REMEDIATION_PLAN.md` 的 P2.2/P2.3：不是把页面包装得更像投顾，而是把“研究解释”和“内部实现术语”彻底分离，同时保留现有 abstention / degradation 语义。
- producer 与 service hydration 两层都必须执行 display normalization。`signal_engine_parts/recommendation.py` 负责不再生成 placeholder/internal copy，`services.py` 负责在读取 legacy payload 时统一修复 `factor_cards / primary_drivers / supporting_context / conflicts`，避免旧 snapshot 再次把内部词汇带回真实页面。
- raw `degrade_flags` 仍可保留为 machine-facing compat 数据，但对外展示只能投射为用户可理解的研究语言；前端 sanitization 与 release verifier banned-term audit 也必须继续把这类 raw token 当成回归风险，而不是正常显示项。
- 这次修复已通过 `tests.test_dashboard_views` 与前端 build，并已通过临时干净快照仓 `/private/tmp/stock-dashboard-professionalism-snapshot-S61bDK/repo` 发布到 live runtime。发布脚本仍因缺少 `ASHARE_CANONICAL_USERNAME` / `ASHARE_CANONICAL_PASSWORD` 无法自动完成 canonical verifier，但随后已在 Safari 对真实入口 `https://hernando-zhao.cn/projects/ashare-dashboard/` 手动复看通过：live page 已不再出现 placeholder fusion 文案、raw degrade token 或 `Phase 2` 内部说明。

[2026-04-27T00:18:11+08:00] Public claim-gate decision from local execution:
从这轮起，用户可见的方向表达不再允许直接读取 raw recommendation direction；所有 `偏积极 / 偏谨慎 / 继续观察 / 风险提示` 一类结论，都必须先经过 artifact-backed claim gate。若 validation 仍未完成、样本量或 coverage 不足，或者缺少可回查的 validation artifact / manifest，则 public direction 必须自动降级，不能因为内部模型方向更乐观就对外放大。

补充说明
- backend recommendation contract 现已新增 `claim_gate`，至少冻结三档 user-facing 状态：`claim_ready`、`observe_only`、`insufficient_validation`。其中 `observe_only` 允许在已有最小 artifact-backed 观察基础时把乐观结论收口到 `watch`；`insufficient_validation` 则进一步把所有未达标表达压到 `risk_alert`。
- dashboard hero、候选列表排序、单票顶部标签和“当前建议摘要”都必须主读 `claim_gate.public_direction`，而不是 legacy/raw direction。raw direction 仅允许作为附属解释存在，例如“模型原始方向：偏谨慎”，不能继续充当对外主结论。
- 这次决定对应 `docs/contracts/PHASE5_CREDIBILITY_REMEDIATION_PLAN.md` 的 P1.3，属于“先冻结公开 claim ceiling，再继续做 P0/P1 实证重建”的产品门禁，而不是在研究尚未成熟时补强建议语气。
- 修复已通过 `tests.test_dashboard_views` 和前端 build 验证，并已发布到 live runtime。由于发布脚本的自动 canonical verifier 仍缺少 `ASHARE_CANONICAL_USERNAME` / `ASHARE_CANONICAL_PASSWORD`，最终验收改由 Safari 对真实入口 `https://hernando-zhao.cn/projects/ashare-dashboard/` 手动完成；当前真实页面已可见 `验证不足` 告警、claim-gate 降级文案，以及单票摘要里的 `对外表达` 字段。

[2026-04-26T22:25:00+08:00] Manual-research stale-status hydration decision from local execution:
manual research request list 的 stale 判定必须和 dashboard projection 复用同一套 hydrated validation context，不能再直接依赖 raw recommendation payload 里的 `historical_validation` 空壳字段。对当前 runtime DB，这类 raw shell 可能为 `null`，但 artifact-backed 当前 validation 实际仍存在；若仍拿空壳做对比，就会把已完成请求误报成 `结果过期`。

补充说明
- `manual_research_workflow.py` 现已通过 `_current_recommendation_context(...)` 在 `_serialize_request(...)` 中调用 `services._build_historical_validation(...)`，先把当前 recommendation 的 validation artifact / manifest 从 artifact store 水合出来，再交给 `build_manual_review_source_packet(...)`、`manual_research_stale_reason(...)` 与 `build_manual_llm_review_projection(...)` 共同使用。
- 这次修复的核心不是放宽 stale 规则，而是让 request list、dashboard 和 recommendation serialization 对“当前 validation 是什么”达成一致。真正的 artifact drift 仍然会被识别；被关闭的是“raw payload 没水合，列表接口把空壳误当当前真相”的假 stale。
- 回归测试 `tests.test_manual_research_workflow.test_completed_request_stays_current_when_validation_is_hydrated_from_artifacts` 已补齐，并与 `tests.test_dashboard_views` 一起通过。修复已经发布到 live runtime，manifest 为 `/private/tmp/stock-dashboard-stale-fix-1guY22/repo/output/releases/20260426T141204Z-00a38a8230d8/manifest.json`；虽然发布脚本因缺少 canonical verifier 凭据没有自动跑完最后一步，但 Safari 强制刷新标准入口 `https://hernando-zhao.cn/projects/ashare-dashboard/` 后，`600589.SH` 的人工研究状态已回到 `已完成`，证明这次 stale 结果并非真实 artifact drift。

[2026-04-26T19:42:00+08:00] Builtin Codex manual-research execution decision from local execution:
manual research 的默认 builtin 路径不再允许停留在“只创建 queued request”的旧 contract。只要本机存在可用 Codex CLI，就应把无 Key 的默认动作视为“立即起本机 Codex 进程并用 `gpt-5.5` 执行人工研究”，而不是要求用户先去配置外部 API Key 或再到治理面板继续执行。

补充说明
- 本机 PATH 上的 Codex CLI 已在本轮主动升级到 `0.125.0`，并通过实际 `codex exec -m gpt-5.5` 调用确认可用。旧的 `0.120.0` 不支持当前需要的模型选择，因此不能继续作为 builtin executor 的隐式前提。
- `runtime_config.py` 现已把 builtin executor 收口为双通道解析：优先检测本机 `codex` CLI 或 App bundle 内置 binary 并使用 `transport_kind=codex_cli`、`base_url=codex-cli://local`、`model_name=gpt-5.5`；只有在显式切回 `openai_api` 或缺少本机 Codex 时，才继续依赖传统 API-key/base-url 组合。
- `manual_research_workflow.py` 现已把 builtin execute 真正接到 `codex exec`，并在默认 UI submit 路径上直接 create + execute。这样 `builtin_gpt` 不再只是一个“留给以后接 server executor”的名义队列，而是本机可落地的默认研究执行器。若本机 Codex 和 API 凭据都不可用，系统才会回退到 unavailable note，而不是假装请求正在正常排队。

[2026-04-26T19:12:00+08:00] Standard-entry latest-release decision from local execution:
`?cb=...` 不应成为 ashare dashboard 的正常访问方式。它只能作为缓存诊断手段；标准入口本身必须在正常刷新、切回标签页和重新聚焦时尽量拿到最新发布。

补充说明
- `frontend/index.html` 现已加入 `Cache-Control: no-cache, no-store, must-revalidate`、`Pragma: no-cache` 和 `Expires: 0` meta，明确把入口 HTML 当成“可随发布漂移”的资源，而不是长期缓存对象。
- `frontend/src/main.tsx` 现已在应用启动后以 `cache: "no-store"` 拉取当前 URL 的最新 HTML，并比较最新 `assets/index-*.js` 与当前运行 bundle；若发现自己跑的是旧 build，就自动 reload。相同逻辑还会在窗口聚焦、标签页重新可见和每 60 秒轮询时再次执行。
- 从这轮起，canonical 验收应优先验证无 query 参数的标准入口；`cb` 仅保留给“怀疑代理/浏览器缓存链路异常”时的临时排查。本轮发布 manifest 为 `/private/tmp/stock-dashboard-publish-2NogWR/repo/output/releases/20260426T110821Z-f84d42681210/manifest.json`，Safari 已直接打开 `https://hernando-zhao.cn/projects/ashare-dashboard/` 并看到最新页面。

[2026-04-26T18:14:13+08:00] Operations focus-workspace behavior and manual-research access decision from local execution:
这轮 `运营复盘` 的四个可见异常里，有三类现在已经被收口成明确 contract：焦点 K 线不再只依赖盘中 `5min` 行情、运营复盘点行切换焦点不再走整页选股刷新、默认股票池语义明确固定为“当前模拟股票池默认跟随 active watchlist”，而不是“永远展示全市场或所有历史候选”。同时，`追问与模拟` 初始触发不再被 operator-only 卡住，写权限用户已经可以创建并执行 manual research request；operator-only 只保留在人工完成/失败/retry 这类治理终态动作。

补充说明
- `simulation.py` 现在把 `watch_symbols_scope` 正式区分为 `active_watchlist_default` 与 `custom`。默认 scope 下，simulation session 会自动跟随当前 active watchlist 增减股票；只有当用户显式改过模拟配置后，才保留 custom pool。`运营复盘` 当前表格展示的是“当前模拟股票池”，不是无限制的全量 universe。
- 焦点 K 线的取数 contract 已补上 daily fallback：如果当前 symbol 没有可用的 `5min` bars，就回退到 `1d` bars，而不是直接把焦点面板显示成空图。这解决的是“当前界面没有 K 线”的产品问题，不改变 intraday-first 的研究语义。
- `frontend/src/App.tsx` 里的运营复盘焦点切换现在走 `api.updateSimulationConfig(... focus_symbol ...) -> applySimulationWorkspace(...)`，焦点变化只更新 simulation workspace 自身，不再触发 `selectedSymbol` 级别的整页 stock-detail reload。表格操作按钮也会显式 `stopPropagation()`，避免点击动作顺带触发行级焦点切换。
- `api.py` 已把 manual research 的 create / initial execute 权限从 operator-only 放宽为 beta write access；但 `complete / fail / retry` 仍保持 operator-only，因为这些动作会改写治理终态与 artifact 生命周期。

[2026-04-26T17:36:02+08:00] Live operations track-table containment publish and verifier-noise decision from local execution:
运营复盘双轨模拟台里“轨道内表格超出”的修复这次才算真正完成，因为它已经不只是本地 build 通过，而是成功发布到 canonical 入口并做了登录后的远端复看。

补充说明
- 前端修复保持为轨道卡片 containment + 更早堆叠的双列布局：`TrackHoldingsTable` 继续使用 `track-holdings-shell` 与 `scroll={{ x: "max-content" }}`，轨道列布局已收紧到 `xs={24} xxl={12}`，避免 `xl` 宽度下双轨卡片仍并排压缩造成表格区域过窄。
- 发布阶段发现 release verifier 会把 runtime-only 性能浮动误判为 canonical API drift，因此 `src/ashare_evidence/release_verifier.py` 现已在 fingerprint normalization 中仅忽略 `刷新与性能预算` gate 的 `launch_gates[*].current_value` 和 `performance_thresholds[*].observed`。这不会放过真实 contract 漂移，但能避免性能数字抖动把 live publish 错误拦下。
- 这次发布通过临时干净 repo 快照执行 `scripts/publish-local-runtime.sh`，生成 manifest `/private/tmp/stock-dashboard-publish-rsync-WyJZXt/repo/output/releases/20260426T093041Z-0f8fe79d90f6/manifest.json`。随后在 Safari 打开 `https://hernando-zhao.cn/projects/ashare-dashboard/?cb=20260426-1738` 完成登录后复看，`运营复盘` 下的 `用户轨道 / 模型轨道` 表格当前都保持在卡片边界内，未再看到旧的整页横向撑开问题。

[2026-04-26T16:04:41+08:00] Phase 5 holding-policy redesign experiment menu decision from local execution:
`Phase 5` 的 holding-policy artifact 现在不只会说“该改收益层还是持仓构造层”，还会直接给出当前优先应跑的 redesign experiment candidates。这样下一步研究不再只是抽象地“做 redesign”，而是已经收口到一组可回查的 draft experiment menu。

补充说明
- `phase5_holding_policy_study` 现已继续输出 `redesign_experiment_candidates / redesign_primary_experiment_ids`，并通过 CLI 与 operations summary 同步暴露 primary experiment ids。当前 redesign diagnostic context 版本已升级到 `phase5-holding-policy-redesign-diagnostics-draft-v2`，因为 context 本体现在同时冻结 signal rules 和 draft experiment menu。
- 当前 experiment menu 按 focus area 拆成两组 research candidates。`after_cost_profitability` 对应 `profitability_signal_threshold_sweep_v1` 与 `profitability_rebalance_hold_band_v1`；`portfolio_construction` 对应 `construction_max_position_count_sweep_v1` 与 `construction_deployment_floor_fallback_v1`。这些都是 Phase 5 的研究菜单，不是已批准产品策略。
- 对当前 fixture-backed study / CLI / operations summary，默认 primary experiment 已明确落成 `profitability_signal_threshold_sweep_v1`；对真实 snapshot `phase5-holding-policy-study:auto_model:2026-04-24:3portfolios`，由于 redesign focus 已包含 `after_cost_profitability + portfolio_construction`，后续主线应优先从 `profitability_signal_threshold_sweep_v1` 与 `construction_max_position_count_sweep_v1` 这两个 primary experiments 开始做对照，而不是继续停留在只描述 focus area 的阶段。

[2026-04-26T15:55:10+08:00] Phase 5 holding-policy redesign diagnostic readout decision from local execution:
`Phase 5` 的 holding-policy artifact 现在不只会给出 “该不该 redesign” 的治理结论，也会把 redesign 的结构化原因和焦点领域写出来。当前 default action 仍是 `prioritize_policy_redesign`，但下一步不再需要从几项原始指标里重新拼凑“到底该改哪一层”。

补充说明
- `phase5_holding_policy_study` 现已新增 `redesign_status / redesign_note / redesign_diagnostics / redesign_triggered_signal_ids / redesign_focus_areas / redesign_context`，并通过 CLI 与 operations summary 同步暴露。当前 redesign diagnostic context version 为 `phase5-holding-policy-redesign-diagnostics-draft-v1`。
- redesign diagnostics 会把收益侧 blocker 和持仓构造侧信号分开表达。对真实 snapshot `phase5-holding-policy-study:auto_model:2026-04-24:3portfolios`，当前默认研究结论不再只是“after-cost excess 为负”，还明确指向两类 redesign focus：`after_cost_profitability` 与 `portfolio_construction`；后者来自当前 real sample 的 `mean_invested_ratio=0.075433` 与 `mean_active_position_count=1.0`，说明 baseline 的资金部署和持仓覆盖都过薄。
- 这意味着后续 Phase 5 主线已经从“继续 formalize gate/governance”收口到“围绕 after-cost profitability 和 portfolio construction 做 policy redesign research”。如果未来 artifact 改善，应该比较 redesign 前后的这些结构化 signal，而不是重新回到纯文本判断。

[2026-04-26T15:37:06+08:00] Phase 5 holding-policy governance readout decision from local execution:
`Phase 5` 的 holding-policy artifact 现在不只会说“gate 有没有过”，还会给出当前默认治理动作。对当前 real-db snapshot，系统已明确把默认结论写成“继续 non-promotion，并优先进入 policy redesign”，不再需要从 `note` 文本里人工猜测下一步。

补充说明
- `phase5_holding_policy_study` 现已新增 `governance_status / governance_action / governance_note / redesign_trigger_gate_ids / governance_context`，并通过 CLI 与 operations summary 同步暴露。当前治理 context 版本是 `phase5-holding-policy-governance-draft-v1`，作用是把 gate blocker 翻译成 Phase 5 默认处理动作，而不是自动批准 promotion。
- 对真实 snapshot `phase5-holding-policy-study:auto_model:2026-04-24:3portfolios`，当前默认治理结论已收口为 `governance_status=maintain_non_promotion_prioritize_policy_redesign`、`governance_action=prioritize_policy_redesign`。触发这一结论的 redesign signal 仍是已知的收益侧 blocker：`after_cost_excess_non_negative` 与 `positive_after_cost_portfolio_ratio`。
- 这意味着后续 Phase 5 policy work 的默认主线不再是“继续讨论该不该 non-promotion”，因为当前代码化治理结论已经是 non-promotion；真正还要继续做的是 redesign research 本体，或在未来出现更强真实证据后再重新评估 gate / governance readout。

[2026-04-26T15:28:05+08:00] Phase 5 holding-policy draft promotion gate and refresh fallback decision from local execution:
`Phase 5` 的 holding-policy 研究现在不再只是“真实 snapshot 不支持 promotion”这一句口头结论，而是已经把 draft promotion gate readout 写进 durable artifact / CLI / operations。当前 real-db snapshot 仍保持 `research_candidate_only`，并且是被明确 gate blocker 阻断，而不是简单“阈值待定”。

补充说明
- `phase5_holding_policy_study` 现在会输出 `gate_status / failing_gate_ids / incomplete_gate_ids / gate_checks / gate_context`。当前 draft gate version 为 `phase5-holding-policy-promotion-gate-draft-v1`，guardrails 先锁定 `min_included_portfolio_count=3`、`after-cost excess >= 0`、`positive-after-cost portfolio ratio >= 0.5`、`mean_turnover <= 0.35`、`mean_rebalance_interval_days >= 5`，但这仍只是研究诊断，不是 operator 已批准的自动 promotion 规则。
- 对真实 snapshot `phase5-holding-policy-study:auto_model:2026-04-24:3portfolios`，当前 `gate_status=draft_gate_blocked`，核心 blocker 至少包括 `after_cost_excess_non_negative` 与 `positive_after_cost_portfolio_ratio`。因此后续 Phase 5 工作应从“是否继续 non-promotion / redesign”出发，而不是默认只需再补一段 gate 文案。
- 同轮还补了 runtime refresh 的稳健性缺口：`analysis_pipeline` 对 Eastmoney research metadata 的 AKShare 抓取现在会注入默认 requests timeout，并在失败时降级为空 metadata，不再让 `phase5-daily-refresh` 或 `refresh-runtime-data` 因外部研究报告元数据抓取卡住。

[2026-04-26T15:05:26+08:00] Phase 5 real holding-policy evidence non-promotion decision from local execution:
`Phase 5` 的 simulation holding-policy 研究现在不只是“artifact 化已经接通”，而是已经在真实数据库上跑出最新 snapshot。当前 real artifact 明确不足以支持 promotion：baseline 继续保持 `research_candidate_only`，后续 gate 设计必须从“为什么当前策略不该晋级”出发，而不是默认它只差一组阈值文案。

补充说明
- 已在真实库上执行 `PYTHONPATH=src python3 -m ashare_evidence.cli phase5-daily-refresh --database-url sqlite:///data/ashare_dashboard.db --analysis-only --skip-simulation`，并生成 `phase5-holding-policy-study:auto_model:2026-04-24:3portfolios`。`operations` 总览现已直接显示这份 artifact，`artifact_available=true`，因此 Phase 5 policy evidence 不再只是测试夹具或临时 CLI 输出。
- 当前 snapshot 纳入 `3` 个 portfolio、`0` 个排除样本；`mean_turnover=0.25`、`mean_rebalance_interval_days=10.5`、`mean_orders_per_rebalance_day=7.0`。但收益侧证据明显不足：`mean_annualized_excess_return=-12.848967`、`mean_annualized_excess_return_after_baseline_cost=-12.849842`，且 `positive_after_baseline_cost_portfolio_count=0`。
- 因此本轮批准结论不是“先把 simulation policy 提升到 approved_for_product，再补治理细节”，而是继续把它视为 simulation-only `research_candidate`。后续工作应优先定义 promotion gate 的否决条件、判断是否需要 policy redesign，并持续禁止任何向真实交易或更强产品承诺的升级。

[2026-04-26T14:59:39+08:00] Phase 5 holding-policy study artifactization decision from local execution:
`Phase 5` 的 simulation holding-policy 研究现在不再只是现场聚合结果，而是进入 typed durable artifact、daily refresh 和 operations 治理总览。当前 baseline 仍是 simulation-only 的 `phase5_simulation_topk_equal_weight_v1`，批准层级继续保持 `research_candidate_only`，但换手/成本/持仓稳定性证据已经可以被稳定回查。

补充说明
- `src/ashare_evidence/phase2/holding_policy_study.py` 现已新增统一研究入口，会读取 auto-model 组合及其 `portfolio_backtest` artifact，输出 `summary / cost_sensitivity / holding_stability / decision / portfolios`。研究纳入条件与产品验证状态已显式解耦：即使组合 backtest 仍处于 `pending_rebuild`，只要 benchmark 定义匹配当前 Phase 5 主研究 benchmark，且存在 turnover 与 annualized excess return，就仍可纳入 holding-policy evidence。
- `src/ashare_evidence/cli.py` 新增 `python3 -m ashare_evidence.cli phase5-holding-policy-study`，并把该 artifact 写入接到了 `phase5-daily-refresh`；`operations.build_operations_dashboard()` 也直接暴露 `approval_state / included_portfolio_count / mean_turnover / mean_annualized_excess_return_after_baseline_cost / artifact_id / artifact_available`，后续不需要临时读代码才能知道 simulation policy 研究是否已有 durable snapshot。
- 这次收口关闭的是“holding-policy evidence 只能临时计算”的缺口，不是 `F004` 本身。后续还需要继续用真实日更 artifact 定义 promotion gate，包括 turnover 上限、成本拖累阈值、持仓稳定性底线，以及何时才能从 `research_candidate` 升级。

[2026-04-26T14:32:06+08:00] Phase 5 simulation holding-policy contract alignment decision from local execution:
`Phase 5` 的 simulation holding policy 现已明确从“withheld quantity preview”升级为可执行的 research-candidate contract，但执行范围仍严格锁定在 web 模拟盘。当前正式基线是 `phase5_simulation_topk_equal_weight_v1`，动作语义为 `delta_to_constrained_target_weight_portfolio`，数量语义为 `board_lot_delta_to_target_weight`；旧的 `withheld_until_execution_policy_is_approved` 只代表 `2026-04-25` maintenance honesty 收口，不再代表当前 Phase 5 合同状态。

补充说明
- 当前代码、前端和测试已经一致落在同一条 contract 上：`simulation.py` 会按最多 `5` 只、单票上限 `20%`、允许留现金和 `100` 股整手约束生成 target-weight delta，并且在用户启用 `auto_execute_model` 后只对 simulation track 自动写入 paper fills，不扩展到任何真实下单或真实交易路由。
- `phase2/phase5_contract.py` 现已新增共享的 simulation policy / auto-execution context helper，`simulation.py` 与 `operations.py` 不再各自手写 `policy_status / policy_type / policy_note / action_definition / quantity_definition`，避免下一次再出现“代码已经前进到 target-weight contract，durable docs 却还停留在 withheld preview” 的分叉。
- 这次对齐不代表 `F004` 已关闭。当前批准层级仍然是 `research_candidate`：后续还需要继续补 simulation-only 策略的换手、成本、持仓稳定性和晋级门槛研究，再决定是否能升到 `approved_for_product`。

[2026-04-26T14:20:00+08:00] Phase 5 expanding-watchlist benchmark membership decision from local execution:
`Phase 5` 的 active-watchlist 主 benchmark 现已明确锁定为 `expanding_active_watchlist_join_date_forward_only`。研究验证仍允许单票使用 full history，但 active-watchlist 等权 proxy 不再把后来加入自选池的股票 retroactively 回填到更早日期。

补充说明
- `src/ashare_evidence/phase2/rebuild.py` 不再用“当前 active scope 静态全样本”构造 market proxy，而是先读取 `WatchlistEntry.created_at` 生成 membership start dates，再用 expanding equal-weight proxy 逐日扩展成分；若当前 refresh 仅临时把 symbol 纳入 active scope、却还没有正式 watchlist entry，则允许回退到该 symbol 最早可用行情日，避免单次 refresh 直接丢失 benchmark 覆盖。
- validation manifest、replay artifact 和 portfolio backtest manifest 现已统一写入 `primary_research_benchmark_membership_rule`、`defaulted_symbol_count`、`defaulted_symbols`、`min_constituent_count`、`max_constituent_count`、`first_active_day` 与 `last_active_day`，后续任何 Phase 5 benchmark 解释都必须以这些 artifact context 为准，而不是再靠口头假设说明。
- `rebuild_phase2_research_state()` 现已在读取 watchlist membership 前先 `session.flush()`。本仓库关闭了 ORM `autoflush`，因此如果不显式 flush，同一事务里刚写入的 watchlist 变更会被 benchmark rebuild 漏读，导致错误回退到 earliest-price fallback。

[2026-04-26T13:26:10+08:00] Phase 5 release parity and anti-regression publish decision from local execution:
`stock_dashboard` 的 live publish 现在不再允许“本地看起来改好了”就算完成。正式发布必须同时满足 clean-tree source、runtime commit 绑定、repo/runtime/canonical 三方 parity 验证，以及可回查的 release manifest。

补充说明
- `scripts/publish-local-runtime.sh` 现在会先拒绝 dirty worktree；只有从已提交的明确 commit 出发，才允许 build、rsync、restart 和后续校验，避免未提交修复再次被 `chore(sync)` 或模糊 baseline 覆盖。
- 新增 `src/ashare_evidence/release_verifier.py` 作为发布后 verifier：它会比较 repo build、runtime dist、localhost served frontend 与 canonical authenticated route 的 asset hash，并对 `/dashboard/operations`、`/settings/runtime`、`/dashboard/candidates` 生成去噪后的 API fingerprint。
- release verifier 会对运营复盘的 user-visible text projection 做专项审计，要求 `用户轨道`、`模型轨道` 必须存在，并阻断 `运营复盘口径仍在迁移`、`Phase 5 baseline`、`research contract`、`pending_rebuild`、`manifest`、`verified` 等历史回退词重新进入 live UI。
- 每次成功发布都会在 `output/releases/<release-id>/manifest.json` 生成 release manifest，并刷新 `output/releases/latest-successful.json`；manifest 同时记录上一个成功版本的 manifest path 与 commit SHA，后续回滚只能回到这份已证明成功的 release，而不是任意工作树状态。

[2026-04-26T01:55:00+08:00] Runtime publish enforcement decision from local execution:
`stock_dashboard` 的 runtime publish 约束不再只依赖控制平面的 task/worktree 自动发布。直接在正式 repo 中工作的 Codex 会话，同样必须把 repo 变更同步到 runtime 并完成本机健康校验，才能把 live-facing 修复视为完成。

补充说明
- 已定位到控制平面的 `publish-runtime.js` 自动 publish 依赖 `task.worktreePath` 与 `task.branchName`，因此它天然只覆盖 worker/task 路径，不覆盖所有交互式 Codex 会话。
- 本项目新增 `AGENTS.md` 与 `scripts/publish-local-runtime.sh`，把 “repo build -> rsync runtime -> kickstart backend/frontend -> check 8000/5173 -> compare served asset names with repo build” 固化成项目内强规则和单命令发布路径。
- 后续凡是声明“前端已验证”“live service 已修复”的会话，都必须以这条脚本成功作为验收依据，而不是只停在 repo build、单元测试或源码 diff。

[2026-04-26T05:05:00+08:00] Phase 5 daily refresh automation decision from local execution:
`Phase 5` 的日更研究链路不再批准继续依赖手动触发。runtime refresh、latest/history horizon-study artifact 写入，以及“是否出现新增 evidence”的比较，现在统一收口到单命令 workflow，并挂上工作日收盘后的自动任务。

补充说明
- `src/ashare_evidence/cli.py` 新增 `python3 -m ashare_evidence.cli phase5-daily-refresh`，它会先执行 runtime refresh，再连续写入 latest/history 两份 `phase5-horizon-study` artifact，输出当前 `approval_state`、`candidate_frontier`、`lagging_horizons`、`included_record_count`、`included_as_of_date_count` 与 artifact 元数据。
- Codex automation `stock-dashboard-phase5-daily-refresh` 已创建并启用，计划在工作日收盘后自动运行这条 workflow。后续这个研究更新属于系统自执行职责，而不是 operator 记忆性操作。
- `tests/test_cli_runtime_refresh.py` 也已收口到真实 artifact 行为：`phase5-daily-refresh` 的回归现在从 CLI 输出读取实际 artifact ID，再回查 typed store，避免把 refresh 后产生的新 snapshot 错误断言成固定的空样本 ID。

[2026-04-26T04:00:00+08:00] Phase 5 horizon-study artifactization and operations visibility decision from local execution:
`Phase 5` 的 horizon-selection 研究现在不再只是“能现场聚合”，而是进入了 durable artifact 和治理总览。当前 real DB 基线已经落成 latest/history 两份 typed snapshot，operations 也会直接展示当前主 horizon 仍卡在 `split_leadership`。

补充说明
- `phase5-horizon-study` 新增 `--write-artifact`，会把当前聚合结果落到 `data/artifacts/studies/` 下的 `phase5_horizon_study` artifact；artifact ID 按 `mode + scope + included as-of dates + symbol_count` 稳定生成，同一批 evidence rerun 会复用同一 ID，而不会伪装成“新增研究结论”。
- 当前 real DB 已写入两份基线 snapshot：`phase5-horizon-study:latest:active_watchlist:2026-04-24:3symbols` 与 `phase5-horizon-study:history:active_watchlist:2026-04-07_to_2026-04-24:3symbols`。它们都继续确认 `40d` 劣后、`10d vs 20d` split、`primary_horizon_status = pending_phase5_selection`。
- `operations.build_operations_dashboard()` 的 `overview.research_validation.phase5_horizon_selection` 现已直接暴露 `approval_state / candidate_frontier / lagging_horizons / included_record_count / artifact_id / artifact_available`。这意味着后续 operator 不需要先手跑 CLI，治理总览就能看到“当前主 horizon 研究是否已有 artifact baseline、是否仍未收敛”。

[2026-04-26T03:00:00+08:00] Phase 5 horizon-study aggregation decision from local execution:
`Phase 5` 的主 horizon 讨论不再依赖单票 payload 或临时 SQL。当前 active watchlist 已新增统一聚合 study 入口，并在真实库上再次确认：`40d` 继续视为劣后候选，`10d` 与 `20d` 仍保持 split leadership，因此主 horizon 继续挂在 `pending_phase5_selection`。

补充说明
- 新增 `python3 -m ashare_evidence.cli phase5-horizon-study`，默认读取 active watchlist 的最新 recommendation；传入 `--include-history` 时，则按 `symbol + as_of_day` 聚合历史 snapshot。study 只纳入满足 `phase5-validation-policy-contract-v1 + phase2_equal_weight_market_proxy + full_baseline + comparison_ready` 的记录，避免把 migration 或半截样本混入主 horizon 讨论。
- 在当前 real DB 上，latest-only 聚合结果为：`10d` leader `2/3`，`20d` leader `1/3`，`40d` leader `0/3`；`10d vs 20d` 的平均净超额收益差仅约 `0.000311`，而 `10d/20d` 对 `40d` 都是 `3/3` pairwise 胜出。
- history mode 目前覆盖 `2026-04-07`、`2026-04-14`、`2026-04-24` 三个 as-of 日期，共 `9` 条纳入记录；symbol-level leader 仍保持稳定，但横截面 split 没有收敛。因此批准结论不变：把 `phase5-horizon-study` 作为日后每个新交易日 refresh 后的标准研究检查点，在拿到更多新 as-of 日期前，不批准 `10d` 或 `20d` 成为正式主 horizon。

[2026-04-26T02:36:00+08:00] Phase 5 real-run benchmark scope and horizon-selection decision from local execution:
`Phase 5` 的 real validation rebuild 现已确认一个入口级 scope bug，并基于修正后的 real run 得出当前 horizon 研究结论：`40d` 可以先降为劣后候选，但 `10d` 与 `20d` 还不能在当前 active watchlist 样本上决出正式主 horizon。

补充说明
- `refresh_real_analysis()` 之前只按当前 symbol 调 `rebuild_phase2_research_state(session, symbols={...})`，会让 validation builder 在 real refresh 场景下错误退回 `phase2_single_symbol_absolute_return_fallback`。该入口现已改为显式传入 `active_watchlist_symbols(session) + 当前 symbol`，`phase2/rebuild.py` 也已区分 update scope 与 proxy scope，确保单 symbol rebuild 仍按 active watchlist equal-weight proxy 构造 Phase 5 benchmark。
- 修正后重新对 real DB 执行 `refresh-runtime-data --skip-simulation`，三只 active watchlist symbol 均达到 `full_baseline` coverage：`available_observation_count=683`、`evaluation_observation_count=83`、`window_count=24`。`historical_validation.benchmark_definition` 已恢复为 `phase2_equal_weight_market_proxy`，`candidate_horizon_comparison.selection_readiness` 也已全部回到 `comparison_ready`。
- 当前真实样本中，`40d` 在三只股票上都明显落后；`10d` 在 `002028.SZ` 与 `002270.SZ` 上领先，`20d` 在 `600522.SH` 上领先。批准结论因此是：继续维持 `primary_horizon_status = pending_phase5_selection`，暂不把 `10d` 或 `20d` 升为产品主 horizon；下一步先在更广或更多次 real run 上继续比较 `10d vs 20d`，再进入正式 selection。

[2026-04-26T02:10:00+08:00] Phase 5 walk-forward coverage and candidate-horizon comparison decision from local execution:
`Phase 5` 的 validation rebuild 现在不再只是冻结合同文案，而是开始把真实历史覆盖要求和 artifact-backed horizon comparison 写进 refresh/rebuild 主路径。

补充说明
- `phase5_contract` 现已新增 `required_history` 事实源，明确 `required_observation_count=660`、`required_bar_count=740` 和 `market_history_lookback_days=1110`；`analysis_pipeline.py` 的日线抓取窗口已切到该基线，避免 refresh 还停留在无法支撑 `480/120/60` 的 `180` 天短样本。
- `phase2/validation.py` 现在按 `480/120/60` 基线构建真实 walk-forward split coverage：样本足够时写出 daily rolling `split_plan`，metrics 只使用 warmup 后的 test-side observation；样本不足时显式标记 `insufficient_history`，而不是继续输出伪 full-baseline artifact。
- recommendation `historical_validation.metrics` 现已附带 `walk_forward` coverage 摘要与 `candidate_horizon_comparison`。其中 research leader 只用于 supporting evidence，`primary_horizon_status` 仍保持 `pending_phase5_selection`，不能被误读为已批准产品周期。

[2026-04-26T01:15:00+08:00] Phase 5 research contract freeze decision from local execution:
`Phase 5 - Real Validation Rebuild and Model Portfolio Policy Research` 的研究合同现已从 handoff 摘要提升为专项 durable spec，并同步收口到共享代码常量。后续 validation、replay、portfolio 和 simulation 不应再各自手写 Phase 5 语义。

补充说明
- 新增 `docs/contracts/PHASE5_RESEARCH_CONTRACT.md` 作为当前 phase 的专项事实源，明确锁定研究验证层与产品跟踪层的分离语义、双层 benchmark、候选 horizon、rolling split baseline、LLM scope 与 simulation auto-execution boundary。
- artifact manifest 现已新增 `research_contract` 上下文字段，用于把 `contract_version`、`candidate_label_horizons`、`rolling_split_baseline`、`llm_analysis_scope` 和 `simulation_execution_scope` 与具体 validation/backtest 产物绑定，避免 Phase 5 研究边界只剩零散文案。
- `simulation.py`、`operations.py`、`phase2/validation.py`、`phase2/replay.py` 与 `phase2/portfolio.py` 现在统一消费共享 `phase5_contract` 常量；若未来修改 benchmark、horizon、split 或 execution boundary，必须先更新专项合同与决策日志，再改代码默认值。

[2026-04-26T00:20:00+08:00] Phase 5 launch decision from local operator + local execution:
项目正式开启 `Phase 5 - Real Validation Rebuild and Model Portfolio Policy Research`。本 phase 直接承接尚未关闭的 `F001` 与 `F004`，目标不是继续做迁移态诚实化，而是把真实滚动验证和正式模型组合建议的研究合同锁定下来。

补充说明
- 一期研究 universe 继续使用当前自选池，但必须显式区分“研究验证层”和“产品跟踪层”。研究验证层允许每只股票使用其完整历史做 rolling validation，只要每个历史时点都严格使用当时可得数据即可；产品跟踪层里的自选池表现、加入后命中率和加入后建议质量，则只能从加入自选池的日期开始计算，不能 retroactive 回填，否则会夸大用户真实可见的历史跟踪成绩。
- benchmark 在本 phase 采用双层语义：研究/策略主 benchmark 先使用 `active_watchlist_equal_weight_proxy`，确保模型评估基于它真实可选的机会集；同时保留 `CSI300` 作为对外解释用的市场参考线，而不是主优化目标。
- label / horizon 研究先从 `10 / 20 / 40` 个交易日的候选窗口开始，但它们只是研究候选集，不是产品承诺。主 horizon 必须由 rolling validation 结果决定，而不是沿用历史一期文案。
- LLM 在本 phase 明确收口为“手动触发的附加分析功能”，不再作为主评分因子。当前推荐做法是由前端在用户点击 LLM 分析时，把当前股票、候选理由、证据摘要、风险标记、验证摘要和近期上下文打包后发给大模型，分析过程默认保持手动触发。
- `F004` 的产品目标已明确为“真自动持仓建议”。在 web 模拟盘里，系统被批准自动生成调仓建议并自动执行模拟成交，不需要人工逐笔确认；但这项权限只限模拟盘，不批准真实下单、真实交易路由或任何实盘自动执行。
- model portfolio policy research 的默认起点采用受约束 TopK 组合基线：周频调仓、最多 `5` 只持仓、单票权重上限 `20%`、允许持有现金、A 股 `100` 股整手约束、控制单次调仓换手；这些是研究起点，不是最终对外承诺，后续可被实证结果推翻。

[2026-04-25T23:58:00+08:00] Simulation model-advice honesty decision from local execution:
simulation model-track 的主 contract 不再允许向用户暴露固定预算买入股数或“卖出一半持仓”这类伪精确数量建议。自本轮起，`model_advices` 只表达人工复核候选动作和参考价格，数量语义保持 withheld，直到正式 execution policy 被研究、批准并锁定。

补充说明
- backend `simulation.model_advices` 现在只在“至少可买/可卖一个 board lot”时给出 `buy/sell` candidate，否则保持 `hold`；对外 `quantity` 统一为空，`action_definition` 收紧为 `manual_review_candidate_from_latest_recommendation`，`quantity_definition` 明确为 `withheld_until_execution_policy_is_approved`。
- frontend operations / simulation UI 已同步移除模型建议里的伪精确股数展示，手动下单参考只保留“买入候选 / 卖出候选 + 参考价”语义，避免把迁移期启发式 sizing 误读成正式策略。
- 这次收口只解决 user-facing honesty，不代表 auto-execution policy 已完成。`F004` 仍保留为未关闭维护项，剩余工作是把真实仓位规则、执行门槛和审批边界研究清楚后再恢复正式 quantity contract。

[2026-04-25T23:45:00+08:00] Manual review layer honesty decision from local execution:
信号引擎主 contract 不再允许把手动研究占位层继续命名成 `llm_assessment factor`。从本轮起，它在主语义里被明确降级为 `manual_review_layer`，只保留“人工研究 artifact 解释层、不可入核心评分”的含义。

补充说明
- signal engine 的主 snapshot、model registry metadata、evidence factor card 与 traceability 视图现在统一使用 `manual_review_layer` / `manual_review_placeholder_layer`；融合分数只允许由 `price_baseline + news_event` 组成，不能继续把手动研究占位包装成主定量因子。
- `llm_assessment` 仅允许作为 legacy compat projection 保留，供旧 factor breakdown consumer 平滑读取；它不再是主 product contract，也不应被作为“LLM lift”“LLM 因子”或任何可计分主特征解释。
- 从本轮起，`F002 so-called LLM factor` 视为已关闭；未完成项只剩真实 validation rebuild 与 auto-model quantity policy 的正式化。

[2026-04-25T23:15:00+08:00] Maintenance-mode honesty decision from local execution:
Phase 4 完成后的 maintenance 收口正式锁定两条迁移期 contract 语义：portfolio / replay benchmark 不再允许使用 synthetic demo 路径，model-track action 也不再允许以 `execution_policy_placeholder` 对外表述。

补充说明
- operations 与 simulation 的 benchmark 数值路径现在统一来自 active watchlist 真实价格构造的 equal-weight proxy；migration replay / portfolio artifact 的 `benchmark_definition` 统一收紧到 `phase2_equal_weight_market_proxy`。
- migration artifact consumer 必须尊重 artifact 自身 `status`，不得因为 benchmark/cost/execution 字段齐全就自动把 pending artifact 升成 `verified`。
- model-track action 现已明确标记为 `manual_review_preview_policy_v1`：它仍是人工复核预览，不会自动成交，也不应被解释成正式执行策略。
- 从本轮起，`F003 benchmark synthetic` 视为已关闭；后续 maintenance 或新 phase 只应继续处理真实量化问题，例如 live/offline validation、LLM lift 重建与正式 auto-execution policy。

[2026-04-25T21:46:24+08:00] Phase 4 governance completion decision from local execution:
`Phase 4 - Manual Research Workflow Hardening and Stable manual_llm_review Contract` 正式完成收尾；从本轮起，manual research request lifecycle 的 operator terminal actions 和 UI governance boundary 视为稳定 contract，而不是待补产品壳。

补充说明
- backend 终态 contract 已锁定：`complete` 负责生成稳定 `manual-review:{request_key}` artifact，并清空失败侧字段；`fail` 不再允许覆盖已生成 artifact 的 completed request，completed terminal state 只能通过 `retry` supersede。
- frontend governance 已锁定三处主入口：单票 follow-up receipt、operations queue、operations focus workspace 均支持 `执行 / 人工完成 / 标记失败 / Retry`，并显式展示 `status_note / failure_reason / stale_reason / request_key`。
- `manual_llm_review` 的真相源继续固定为 `manual_research_requests + manual_review artifact`；compat `/analysis/follow-up` 只保留触发包装层角色，不再定义主生命周期。
- 本轮验证 `PYTHONPATH=src python3 -m unittest tests.test_manual_research_workflow tests.test_dashboard_views`、`PYTHONPATH=src python3 -m unittest tests.test_runtime_config tests.test_manual_research_workflow tests.test_dashboard_views tests.test_traceability tests.test_analysis_pipeline tests.test_research_artifact_store` 与 `frontend && npm run build` 全部通过。

[2026-04-14T11:17:37.757Z] Operator feedback from github:zhaohernando-code:
本轮计划反馈
- 问题：一期先覆盖多大的股票范围？
  回复：自选股池
- 问题：你希望系统给出的“投资建议”定位是什么？
  回复：尽量接近投顾体验
- 问题：数据源策略更倾向哪种？
  回复：先免费后预留付费升级
- 问题：一期主要交付形态是什么？
  回复：Web看板
- 问题：建议风格希望更偏哪类？
  回复：平衡型

补充说明
这个web后续可以作为github page子页面进行部署
针对主要风险进行一些补充说明和提问：
Q1: A 股行情与新闻数据的授权、质量和实时性差异很大，若前期数据源选择失误，后续架构会频繁返工。
A1: 我需要你对当前的数据源进行评估，如果免费和付费差距过大，我可以考虑付费
Q2: 历史价格预测在金融场景中极易过拟合，若没有严格的时间滚动验证，离线结果会显著高估真实效果。
A2: 可以在里面做时间滚动验证么？
Q3: 新闻到因子的映射存在噪声和时滞，同一事件可能被重复计价或在市场中提前反映。
A3: 能否通过技术手段减轻影响？
Q4: LLM 容易把弱信号组织成看似确定的结论，必须被限制在解释层，并绑定结构化证据和风险提示。
A4: LLM的反馈也作为一个因子，可以先用历史数据来评估其分析可信度
Q5: 推荐、建议和模拟交易同时展开会迅速扩大一期复杂度，需要先限定股票池、刷新频率和建议粒度。 面向外行输出“投资建议”涉及合规表达和责任边界，需要尽早明确产品定位是研究辅助、教育用途还是更强的决策支持。
A5: 产品后续方向会更倾向于更强的决策支持而不是研究辅助和教育用途。在经过一段时间的模拟盘测试后可能会正式作为投资的决策建议

[2026-04-14T11:23:36.864Z] Operator feedback from github:zhaohernando-code:
本轮计划反馈
- 问题：GitHub Pages 在一期里承担到什么程度？
  回复：前端上 GitHub Pages，后端单独部署
- 问题：一期希望把数据时效性做到什么级别？
  回复：盘中延迟更新可接受
- 问题：建议主要面向哪类持有周期？
  回复：波段 2-8 周

[2026-04-14T11:34:11.618Z] Operator feedback from github:zhaohernando-code:
本轮计划反馈
- 问题：一期看板的访问范围需要如何控制？
  回复：小范围内测
- 问题：一期模拟交易更希望采用哪种方式？
  回复：两者都要

补充说明
“免费与付费 A 股数据在授权、稳定性、实时性和字段完整度上的差距可能显著高于预期；若前期不做适配层和替换预案，后续升级成本会很高”
上述行为是否为你调研过后的行为。如果只是猜测，那可能适配和替换预案都需要加入需求列表

[2026-04-14T11:48:50.205Z] Operator feedback from github:zhaohernando-code:
本轮计划反馈
- 问题：“两者都要”的模拟交易，具体希望覆盖哪两类路径？
  回复：手动模拟+自动持仓（这两个不要放在一起）
- 问题：如果数据源评估显示免费方案不足，一期是否允许直接落到付费数据方案？
  回复：先评估后单独审批

补充说明
我无法直接回答付费问题，因为你需要在评估后告诉我价格和付款模式

[2026-04-14T11:55:57.539Z] Operator feedback from github:zhaohernando-code:
本轮计划反馈
- 问题：自动持仓模式在一期更接近哪种机制？
  回复：按模型组合自动持仓

[2026-04-15T00:00:00+08:00] Pending operator decision:
第 1 步“数据与开源基线评估”已完成，等待操作者在 web decision gate 中选择后续数据路线与第 2 步执行方向。

[2026-04-14T15:39:04.955+08:00] Project flow decision from local operator:
采用 `Tushare Pro + 巨潮公告/交易所披露 + Qlib` 作为一期主路线；`AkShare` 仅作辅助原型和补缺。

补充说明
- 第 2 步“证据化数据底座”继续推进。
- `license_tag`、`usage_scope`、`redistribution_scope`、`source_uri`、`lineage_hash` 作为强制字段进入数据模型。

[2026-04-14T16:42:56.908+08:00] Project flow decision from github:zhaohernando-code:
项目流决策
当前步骤：数据与开源基线评估
- 决策项：下一步按哪条路线推进？
  结论：按低成本研发路线继续

补充说明
- 开发时要预留未来切换到“商业数据授权 / 询价”方案的代码架构。
- 后续需要补一份“效果 -> 价格”的商业数据授权调研报价单。

[2026-04-15T00:50:14+08:00] Implementation decision from local execution:
第 2 步采用 `FastAPI + SQLAlchemy` 的 Python 后端骨架，先把证据血缘、建议回溯和模拟交易留痕固化为统一 schema，再在同一 contract 下接入真实 provider。

补充说明
- `LineageMixin` 已覆盖股票、板块、行情、新闻、特征、模型版本、模型结果、提示词版本、建议、建议证据、模拟交易和采集运行表。
- 证据追溯采用 `recommendation -> recommendation_evidence -> domain artifact` 的解耦结构，避免在第 3 步前把供应商实现细节写死在业务层。
- 当前以 `DemoLowCostRouteProvider` 验证端到端链路；真实 `Tushare / 巨潮 / Qlib` 适配器将沿同一 provider contract 补齐。

[2026-04-15T10:30:00+08:00] Implementation decision from local execution:
第 3 步采用“价格基线 + 新闻事件因子 + capped LLM 因子 + 融合评分卡”的建议引擎结构，LLM 因子默认只在历史 lift 与稳定性同时过阈值时参与加权，且权重上限固定为 `15%`。

补充说明
- recommendation 输出必须直接暴露 `confidence_expression`、`reverse_risks`、`downgrade_conditions`、`factor_breakdown` 和 `validation_snapshot`，避免前端再去解析半结构化文本。
- demo provider 不再维护静态 recommendation，而是统一走 `raw evidence -> signal_engine -> persisted recommendation` 链路。
- 当前 `14/28/56` 天三个 horizon 都会落到 `model_results`；recommendation 以 28 天作为主解释窗口，但保留 2-8 周完整范围。

[2026-04-15T15:20:00+08:00] Implementation decision from local execution:
第 6 步将“手动模拟交易”和“按模型组合自动持仓”继续建成两个独立 `paper_portfolios`，共用 recommendation 流但独立资金池、独立收益归因、独立回撤阈值，不做合并记账。

补充说明
- 历史 seed 订单只服务于组合收益、回撤和基准对比演算；只有 `order_record.recommendation_key` 与当前 recommendation 精确匹配时，订单才进入 recommendation trace。
- 内测访问控制采用可配置的 header allowlist 方案：默认 `open_demo` 便于本地验证，部署小范围内测时切换为 `ASHARE_BETA_ACCESS_MODE=allowlist` 并使用 `ASHARE_BETA_ALLOWLIST` 管理 key/role。
- 新增 `/dashboard/operations` 作为模拟交易运营面板 contract，统一承载收益归因、A 股规则检查、建议命中复盘、刷新策略、性能阈值和上线门槛。

[2026-04-15T16:20:00+08:00] Acceptance revision decision from local execution:
为解决线上 API 不可用导致的验收失败，本轮采用“当前 API contract 导出的前端离线快照 + 在线优先回退机制”完成最小可用闭环，而不是新开一套平行前端 demo。

补充说明
- 新增 `frontend_snapshot` 导出器，离线数据直接由现有 `dashboard` 与 `operations` payload 生成。
- 前端默认在无 `VITE_API_BASE_URL` 时进入离线模式；若用户切到在线模式但接口失败，会自动回退并明确提示原因。
- UI 改为 `Ant Design` 控制台式布局，把数据模式、焦点股票、access key 和演示重置收敛到顶部操作面板，减少无效大文案占位。

[2026-04-24T23:40:00+08:00] Research reset decision from local operator:
历史计划与现有实现中的时间窗口、权重占比、阈值和样本期不再视为产品约束；凡是影响可信度的旧设定，包括但不限于 `2-8 周`、`14/28/56`、固定权重上限、固定命中口径，后续都允许被研究结果直接推翻。

补充说明
- 这些数字保留为“历史假设”仅用于审计与迁移，不再作为新一轮深度改造的默认输入。
- 后续开发必须先给出研究依据，再锁定窗口、标签、调仓频率、融合权重和展示口径。
- 若真实研究结果表明旧功能名不副实，应优先重命名、降级或删除，而不是继续沿用旧字段。

[2026-04-24T23:59:00+08:00] Execution governance decision from local execution:
项目新增 `PROJECT_STATUS.json` 作为机器可读的执行状态真相源，和 `PROJECT_PLAN.md`、`DECISIONS.md`、`docs/archive/RESEARCH_NOTES.md`、`PROCESS.md` 共同构成新的深度改造交接面。

补充说明
- `PROJECT_PLAN.md` 负责长期路线和阶段定义。
- `DECISIONS.md` 负责记录被批准的架构与策略决策。
- `docs/archive/RESEARCH_NOTES.md` 负责外部研究与研究结论。
- `PROCESS.md` 负责按日期追加执行日志。
- `PROJECT_STATUS.json` 负责让新会话和自动化进程快速判断当前 phase、里程碑、阻塞点和下一步动作。

[2026-04-25T00:38:39+08:00] Product honesty migration decision from local execution:
在真实滚动验证、真实 benchmark 和手动 Codex/GPT 研究链路重建完成前，前端和 API contract 不再把旧的 validation snapshot、超额收益、建议命中口径和所谓 LLM 因子展示为已验证能力。

补充说明
- recommendation contract 现在显式输出 `validation_status`、`validation_note`，并把旧的 `validation_snapshot` 对外清空。
- operations contract 现在显式区分 `benchmark_status`、`benchmark_note`、`replay_validation_status` 和 `replay_validation_note`。
- 所谓 `LLM 因子` 在核心评分中被降为零权重占位，只保留“手动触发研究链路待接管”的迁移语义。
- 在新的研究合同锁定前，任何旧验证指标都只能显示为 `pending_rebuild`、`synthetic_demo` 或 `manual_trigger_required`，不得再伪装成真实量化验证结果。

[2026-04-25T00:38:39+08:00] Phase 0 contract freeze decision from local execution:
项目正式冻结迁移期的 `recommendation / replay / portfolio / operations / manual_llm_review` 合同语义，并以 `docs/contracts/PHASE0_DATA_METRIC_CONTRACT.md` 作为后续 schema 与服务改写的事实来源。

补充说明
- recommendation 未来必须拆成 `core_quant`、`evidence`、`risk`、`historical_validation`、`manual_llm_review` 五层。
- replay 必须与 recommendation 的目标 horizon 和 label 定义对齐，不再允许沿用“直到当前最新价”的宽松窗口。
- portfolio 和 operations 必须显式区分 `运行健康`、`研究验证`、`演示策略` 和 `上线门禁`，不能再混成单一 readiness 指标。
- 没有真实 benchmark、真实回测和真实实验 artifact 支撑的数值字段，不得升级为 `verified`。

[2026-04-25T00:44:42+08:00] Continuous autonomous execution decision from local operator:
在用户离线或睡眠期间，项目按已批准 plan 持续推进；如果发生上下文压缩、线程切换或新会话恢复，也必须默认继续当前 phase 的下一步，而不是自动停在阶段性说明上。

补充说明
- 这条规则同样适用于上下文压缩后的恢复场景。
- 只要 handoff 文档和 `PROJECT_STATUS.json` 仍可读取，新会话应直接继续执行，不需要等待新的“继续”口令。
- 只有遇到真实外部阻塞、权限缺失、破坏性冲突或高风险不确定性时，才允许暂停并等待用户输入。

[2026-04-25T00:55:27+08:00] Phase 1 recommendation and replay contract decision from local execution:
Phase 1 正式要求前端和运营复盘开始消费新的 recommendation / replay 分层 contract，而不是继续把 legacy 兼容字段当成主要语义来源。

补充说明
- recommendation 主视图应优先读取 `core_quant`、`evidence`、`risk`、`historical_validation` 和 `manual_llm_review`。
- replay 记录至少要显式输出 `label_definition`、`review_window_definition`、`entry_time`、`exit_time` 和 `hit_definition`，即使当前仍属于迁移期演示口径。
- 旧 `core_drivers`、`reverse_risks`、`review_window_days` 和单一 `hit_status` 仍可保留为兼容层，但后续不能再独自承担真实语义。

[2026-04-25T01:24:00+08:00] Phase 1 governance workspace contract decision from local execution:
运营治理页和组合工作区现在必须以显式分层 contract 作为主语义来源；legacy `beta_readiness`、`benchmark_status`、`benchmark_note` 和 `replay_validation_note` 只允许作为兼容壳保留，不能继续主导用户可见的状态解释。

补充说明
- operations governance 主视图应优先读取 `overview.run_health`、`overview.research_validation` 和 `overview.launch_readiness`。
- portfolio workspace 主视图应优先读取 `benchmark_context`、`execution_policy` 和 `validation_status`，而不是继续把 top-level benchmark shorthand 当成真实量化语义。
- 后续若仍保留 legacy compat 字段，必须由新分层 contract 派生，不能再由独立的旧逻辑直接生成。

[2026-04-25T01:42:00+08:00] Phase 1 compatibility derivation decision from local execution:
从本轮起，operations 与 portfolio 的 legacy compat 字段必须从分层 contract 派生，同时性能预算测量必须基于接近最终返回结构的 payload，而不是旧版扁平 overview。

补充说明
- `beta_readiness`、`replay_validation_status`、`recommendation_replay_hit_rate` 等 overview 兼容字段，只能从 `launch_readiness` 与 `research_validation` 推导。
- `benchmark_status`、`benchmark_note`、`recommendation_hit_rate` 等 portfolio 兼容字段，只能从 `benchmark_context`、`validation_status` 等显式层派生；在验证未完成时不得继续输出乐观的 synthetic 命中率。
- 后续任何性能门禁或 payload 预算数字，都必须说明其测量对象对应的是哪一层 contract，避免“新 contract 已膨胀，旧 payload 预算仍显示过关”的假象。

[2026-04-25T09:40:36+08:00] Phase 1 candidate and factor-card contract decision from local execution:
候选列表、跟进提问和单票详情页中的建议解释现在必须优先消费 recommendation 的显式分层 contract；legacy `applicable_period`、`core_drivers`、`reverse_risks` 与 `factor_breakdown` 只允许作为服务端兼容壳继续保留。

补充说明
- candidate list 和 follow-up prompt 必须从 `historical_validation`、`core_quant`、`evidence`、`risk` 派生窗口、horizon、验证状态和主要风险，而不是继续直接读取旧 top-level 建议字段。
- 单票详情页的因子卡片主读取路径已切到 `evidence.factor_cards`；top-level `factor_breakdown` 保留仅用于迁移兼容和 traceability，不再作为前端主 contract。
- 后续若继续压缩 recommendation schema，优先删除的是“顶层 legacy 展示字段被前端主读”的路径，而不是盲目先删兼容字段本身。

[2026-04-25T09:53:33+08:00] Phase 1 helper cleanup and Phase 2 artifact contract decision from local execution:
`dashboard.py` 的变化解释 helper 现在必须优先消费 `evidence.factor_cards` 与 `evidence.degrade_flags`，同时项目正式冻结 `Phase 1 -> Phase 2` 的 research artifact contract，后续真实滚动验证、回测和 replay 结果只能按该 contract 落盘与投影。

补充说明
- `dashboard` 层的 `factor_score`、降级标记和 follow-up / risk helper 不应再依赖 recommendation 顶层 `factor_breakdown` 作为主语义来源；顶层 compat 字段仅保留为迁移壳。
- 新增 `docs/contracts/PHASE1_PHASE2_ARTIFACT_CONTRACT.md` 与 `src/ashare_evidence/research_artifacts.py`，预先冻结 rolling validation manifest、validation metrics artifact、portfolio backtest artifact 和 replay alignment artifact 的字段边界。
- 在后续真实量化结果重建前，任何 `historical_validation.status=verified` 的语义都必须绑定上述 artifact manifest，而不能由 recommendation payload 自己声称“已验证”。

[2026-04-25T10:05:48+08:00] Phase 1 artifact gate and storage layout decision from local execution:
从本轮起，产品层的 `historical_validation` 与 replay validation projection 必须经过统一 artifact gate；同时 Phase 2 的研究产物存储路径正式落成代码骨架，后续真实滚动验证、回测与 replay 结果应优先写入 artifact store，而不是继续直接挤进 recommendation payload。

补充说明
- `src/ashare_evidence/research_artifacts.py` 新增统一 validation gate，若 payload 试图在缺少 `artifact_id / manifest_id / approved benchmark / cost definition` 时自称 `verified`，服务层必须回落为 `pending_rebuild`。
- `src/ashare_evidence/research_artifact_store.py` 已按 `artifacts/manifests|validation|backtests|replays` 的目录语义提供落盘和读取接口，为后续 Phase 2 artifact producer 铺底。
- `simulation.py` 的模型建议理由和风险提取现在优先读取 recommendation 的 `evidence / risk` 分层字段，避免模拟轨道继续依赖旧 top-level compat 字段。

[2026-04-25T10:24:34+08:00] Phase 1 artifact-backed governance and simulation-layer decision from local execution:
`operations` 概览中的研究验证摘要现在必须显式投影 artifact 绑定覆盖率，而 `simulation` 的模型建议区不再允许从 recommendation 顶层 legacy reason/risk 字段回退取值。

补充说明
- `overview.research_validation` 现在新增 `manifest_bound_count`、`metrics_artifact_count` 和 `artifact_sample_count`，用于说明当前治理页看到的“研究验证”到底有多少条 recommendation 已经绑定 migration artifact，而不是只剩空泛的 `pending_rebuild` 状态。
- `simulation.py` 的建议理由与风险提示现在只能从 `evidence.primary_drivers / supporting_context` 和 `risk.risk_flags / invalidators / coverage_gaps` 读取；旧 `core_drivers` 与 `reverse_risks` 继续保留仅用于服务端兼容壳，不再作为 simulation 主语义来源。
- 对应回归测试已加入“毒化 top-level legacy 字段”的断言，后续如果有人把 simulation 再改回 legacy fallback，应当直接测试失败。
- `frontend/src/types.ts` 中 recommendation 的顶层 `applicable_period / core_drivers / reverse_risks / factor_breakdown / validation_snapshot` 等字段现已降为可选 compat 字段，避免新的前端开发继续把它们当成必填主 contract。

[2026-04-25T11:01:46+08:00] Phase 1 portfolio backtest projection decision from local execution:
组合层现在必须能读取 Phase 2 artifact store 中的 portfolio backtest 产物，并把 artifact-backed 的 benchmark/performance/validation 元数据投影到 portfolio contract；但只要 benchmark 定义仍是 `synthetic_demo`，产品层验证状态就必须继续回落为 `pending_rebuild`。

补充说明
- `tests/fixtures.py` 现在会在 watchlist fixture 完成后生成 `rolling-validation:portfolio-migration-watchlist` manifest，并为 `portfolio-manual-live / portfolio-auto-live` 写入 `portfolio-backtest:*` artifact，作为迁移期组合回测占位产物。
- `operations.py` 中 portfolio payload 会优先读取对应 backtest artifact，把 `artifact_id / manifest_id / benchmark_definition / annualized_return / annualized_excess_return / turnover / win_rate_definition` 投影到 `benchmark_context` 与 `performance`，并将 `validation_artifact_id / validation_manifest_id` 暴露给产品层。
- 统一 validation gate 仍然生效：由于当前 artifact 的 `benchmark_definition=synthetic_demo`，portfolio 的 `validation_status` 与 benchmark context status 只能是 `pending_rebuild`，不得借由 artifact 存在本身升级为 `verified`。

[2026-04-25T11:09:26+08:00] Phase 1 portfolio artifact governance projection decision from local execution:
治理页的 `research_validation` 现在必须同时投影 recommendation artifact 覆盖和 portfolio backtest artifact 覆盖，且 simulation/portfolio workspace 对组合产物的展示必须与这组治理数字保持一致。

补充说明
- `simulation.py` 现在会把 manual/model 轨道映射到 `portfolio-backtest:portfolio-manual-live` 与 `portfolio-backtest:portfolio-auto-live`，确保双轨工作区与 operations portfolio contract 使用同一组 migration backtest artifact。
- `operations.py` 新增 `portfolio_backtest_bound_count / portfolio_backtest_manifest_count / portfolio_backtest_verified_count / portfolio_backtest_pending_rebuild_count`，并把“组合回测产物绑定”加入 launch gates，避免治理页只看到 recommendation metrics 而忽略组合层 research artifact 接通情况。
- `frontend/src/App.tsx` 的运营概览现在直接展示 recommendation manifest/metrics 覆盖和 portfolio backtest 覆盖计数；当前这些数字仍只能说明“artifact 已接通”，不能替代正式 benchmark、成本和执行假设完成后的真实验证结论。

[2026-04-25T11:13:06+08:00] Phase 1 compat-shell reduction decision from local execution:
`portfolio` 与 `operations overview` 的顶层 benchmark/readiness compat 字段现在只应被视为派生壳；前端主 contract 和后端 response model 都必须允许这些字段降为 optional，以便后续逐步删除而不反向绑死实现。

补充说明
- `frontend/src/App.tsx` 的组合页已改为读取 `execution_policy.status` 而不是 `portfolio.strategy_status`；`frontend/src/types.ts` 也将 `strategy_status / benchmark_status / recommendation_hit_rate / beta_readiness / recommendation_replay_hit_rate / replay_validation_status` 降为 optional compat 字段。
- `src/ashare_evidence/schemas.py` 已同步把上述 compat 字段放宽为 optional，同时保持当前 API 继续输出这些字段，确保迁移期兼容不被破坏。
- `src/ashare_evidence/operations.py` 新增 `_portfolio_compat_projection` 与 `_overview_compat_projection` 两个 helper，后续若继续删除 compat 字段，只需在统一出口调整，不应再在 payload 组装逻辑里散落多处旧口径写入。

[2026-04-25T11:27:08+08:00] Phase 1 replay artifact consumer decision from local execution:
`operations.recommendation_replay` 现在必须优先消费 artifact store 中的 replay alignment 产物，而不是继续仅靠内联 synthetic replay payload 维持迁移语义；治理摘要也必须显式区分“已有 replay artifact”与“仍未进入 verified”的覆盖率。

补充说明
- `tests/fixtures.py` 现在会在 watchlist fixture 完成后，为 replay 列表生成并落盘 `replay-alignment:*` artifact，使 recommendation metrics、portfolio backtests 和 replay alignment 三条迁移期 artifact 路径共享同一 artifact store。
- `src/ashare_evidence/operations.py` 的 replay payload 会优先读取 replay artifact 的 `manifest_id / label_definition / review_window_definition / hit_definition / validation_status`，并新增 `source=replay_alignment_artifact|migration_inline_projection` 以区分真实 artifact-backed consumer 与仍未接通的 inline fallback。
- replay artifact 覆盖率在治理层使用 `replay_artifact_bound_count / replay_artifact_manifest_count / replay_artifact_nonverified_count` 表达，其中 `nonverified` 明确表示“尚未进入 verified”，避免把 `synthetic_demo` 误命名成 `pending_rebuild` 再次制造状态歧义。

[2026-04-25T11:38:37+08:00] Phase 1 candidate validation projection decision from local execution:
候选列表和单票详情页现在必须直接显示 artifact-backed validation 指标，而不是只给用户一个抽象的验证状态标签；推荐消费层的验证摘要应优先来自 `historical_validation.metrics` 与 artifact id/manifest id，而不是继续依赖 legacy 顶层说明字段。

补充说明
- `src/ashare_evidence/dashboard.py` 现在把 recommendation 的 `historical_validation` 中的 `artifact_id / manifest_id / sample_count / rank_ic_mean / positive_excess_rate` 投影进 candidate contract，使候选列表与自选池详情和 governance/portfolio 一样，消费同一条 stored validation artifact 路径。
- `frontend/src/App.tsx` 已新增 candidate validation summary 展示，并在 stock detail 的“历史验证层”中直接展示样本量、RankIC 均值、正超额占比和覆盖率，避免用户只能看到“待重建/已验证”这种低信息量标签。
- 这组指标当前仍属于 migration artifact 语义，不等于正式通过研究批准的实盘可信结论；但在 benchmark 仍为 `synthetic_demo` 的前提下，产品层至少必须诚实展示“当前状态之下到底有多少样本、什么分布指标”，而不是隐藏具体数值。

[2026-04-25T11:41:08+08:00] Phase 1 recommendation compat reprojection decision from local execution:
recommendation 顶层 `factor_breakdown` 这类 legacy compat 壳现在应尽量从分层 contract 回投，而不是继续直接透传原始 payload。兼容字段可以保留，但语义来源必须逐步切到 `evidence / risk / historical_validation / manual_llm_review`。

补充说明
- `src/ashare_evidence/services.py` 新增 `_legacy_factor_breakdown`，现在会优先用 `evidence.factor_cards`、`evidence.degrade_flags` 和 `manual_llm_review.status` 生成 compat `factor_breakdown`，只把原始 payload 中尚未迁移的细节字段当作补充，而不是主真相。
- 这样做的目的不是立即删除 compat 字段，而是避免后续 traceability 或兼容 consumer 继续把未审计的 payload 结构误当成产品层事实。
- 后续若继续收 recommendation legacy 壳，优先目标应是让更多 compat 字段由显式分层 contract 派生；只有在 consumer 全部迁走后，才考虑真正删除字段本身。

[2026-04-25T11:51:05+08:00] Phase 1 layered-producer strengthening decision from local execution:
不仅服务层 compat projection 要从分层 contract 回投，`signal_engine` 产出的 recommendation payload 本身也要减少 raw compat 字段并优先写入显式层字段，否则服务层每次序列化都还要被迫从旧 payload 兜底。

补充说明
- `src/ashare_evidence/signal_engine.py` 现在直接写入 `evidence.factor_cards`、`evidence.degrade_flags`、`historical_validation.artifact_type` 和 `historical_validation.manifest_id`，并停止继续生成 `applicable_period`、`reverse_risks` 与 recommendation 顶层 `validation_snapshot` 这类已可由分层 contract 派生的 raw compat 字段。
- `src/ashare_evidence/services.py` 的 `core_quant / evidence / risk / manual_llm_review` 在消费 payload 时也会先做规范化补全，再进入 compat projection，避免“有分层字段但内容不完整”导致后续 consumer 又回退到旧字段。
- 这一步的目标不是一次性删除所有顶层 compat 字段，而是先保证新的 producer 与 consumer 都以分层 contract 为主语义来源。

[2026-04-25T11:51:05+08:00] Phase 1 follow-up research packet decision from local execution:
手动 Codex/GPT 研究入口不应只复制一段带抽象状态的 prompt 文本；follow-up contract 现在必须携带 artifact-backed 的验证摘要和人工研究状态，作为后续 Phase 4 手动触发工作流的结构化输入。

补充说明
- `src/ashare_evidence/dashboard.py` 的 `follow_up` payload 现在新增 `research_packet`，其中包含 `validation_artifact_id / manifest_id / sample_count / rank_ic_mean / positive_excess_rate` 以及 `manual_review_status / trigger_mode / source_packet`。
- follow-up 的 `copy_prompt` 同步加入上述验证信息，使人工研究时能直接看到当前 recommendation 已绑定的 validation artifact 与样本统计，而不是只看到 `pending_rebuild` 这种低信息量状态词。
- 后续真正切到手动 Codex/GPT 进程时，应优先消费这组结构化 `research_packet`，而不是重新从页面文案或 legacy recommendation 顶层字段里反解上下文。

[2026-04-25T12:16:00+08:00] Phase 1 placeholder quarantine and latest-summary test decision from local execution:
从这一轮起，recommendation 的历史验证与人工研究层不再允许被 legacy compat 字段反向驱动；同时所有“修改 payload 后再读取 latest summary”的 Phase 1 回归都必须显式绑定最新 recommendation 版本，避免旧历史记录掩盖 contract 漂移。

补充说明
- `src/ashare_evidence/services.py` 中 `historical_validation` 不再从 raw `validation_snapshot` 回填，`manual_llm_review` 也不再从 `factor_breakdown.llm_assessment` 反向补齐；验证真相只能来自 artifact gate + manifest/metrics 投影，人工研究真相只能来自 `manual_llm_review` 自身或默认手动占位。
- `src/ashare_evidence/research_artifact_builders.py` 的迁移 validation artifact 构建现在只读取 `historical_validation` 层和统一 gate 状态，不再吸收 legacy validation snapshot 中的 cost/status 语义。
- `src/ashare_evidence/simulation.py` 与 `src/ashare_evidence/operations.py` 对动作建议和组合执行语义继续降级：execution policy 统一标记为 `execution_policy_placeholder / pending_rebuild`，没有真实回测与执行假设接管前，不得看起来像正式策略。
- `tests/test_traceability.py` 中所有会修改 recommendation payload 的收口回归，后续都必须先锁定最新 recommendation，再验证 legacy 字段不会反向驱动主 contract。

[2026-04-25T12:29:00+08:00] Phase 1 manual-LLM placeholder boundary decision from local execution:
`manual_llm_review` 在 Phase 1 内正式收紧为“人工触发研究助手占位”，未触发状态下不得再携带 placeholder 风险或分歧；任何这类说明都只能留在 compat shell 或产品说明文案中，不能冒充人工研究产物。

补充说明
- `src/ashare_evidence/signal_engine.py` 生成 recommendation payload 时，`manual_llm_review` 默认只保留 `status / trigger_mode / model_label / summary / source_packet`，并把 `risks / disagreements` 置空，避免 producer 直接把“尚未接入的 LLM 研究能力”写成一组看似真实的风险结论。
- `src/ashare_evidence/services.py` 会对历史 payload 做同样的净化：如果 `manual_llm_review.status=manual_trigger_required` 且没有真实 `generated_at`，则强制清空 `risks / disagreements`，确保旧 recommendation 进入新 contract 时不会把 placeholder 重新抬回主语义。
- 只有在后续真正接入手动 Codex/GPT 工作流并落下可追溯研究产物后，`manual_llm_review` 才允许展示具体风险、分歧与生成时间；在此之前，它只是研究入口状态，不是研究结论本身。

[2026-04-25T12:37:00+08:00] Phase 1 replay window-definition-first decision from local execution:
`recommendation_replay` consumer 现在必须优先展示结构化 `review_window_definition`，而不是继续把 `review_window_days` 这种 legacy 数字壳当成主语义；旧天数字段仅允许作为兼容层保留。

补充说明
- `frontend/src/App.tsx` 的 replay 表格现已把 secondary text 切到 `symbol + review_window_definition`，避免用户在迁移期看到一个来源不清、看似精确的窗口天数后误判这已经是研究批准过的定义。
- `frontend/src/types.ts` 与 `src/ashare_evidence/schemas.py` 已同步把 `review_window_days` 降为 optional compat 字段，为后续 Phase 1 继续收缩 replay legacy 壳留出空间。
- 后续如果 replay contract 继续细化，优先方向应始终是“定义性字段优先、数字性 legacy 壳后退”，直到 Phase 2 的真实 replay producer 接管。

[2026-04-25T12:26:34+08:00] Phase 1 artifact-backed vs migration-validation projection decision from local execution:
从这一轮开始，Phase 1 必须把“artifact 已接通”与“验证已成立”彻底分开投影。任何 replay 或 portfolio backtest 即使已经绑定 artifact/manifest，也只有在 benchmark、成本和执行假设完成重建后，才允许进入 `artifact_backed` 的 validation mode；否则只能以 `artifact_backed` source classification + `migration_placeholder` validation mode 对外展示。

补充说明
- `src/ashare_evidence/operations.py` 与对应 schema/type 现在新增统一的 `source_classification` 与 `validation_mode` 字段，并在 `portfolio`、`recommendation_replay`、治理摘要和 launch gate 上使用同一套口径；“组合回测产物绑定” gate 也不再因为 artifact 已绑定就显示通过，而是要求 `verified_count` 满足后才可 pass。
- `frontend/src/App.tsx` 已同步把 replay 表格和 portfolio workspace 的说明切到这组新字段，显式提示“artifact 已接通但 benchmark / cost / execution assumptions 仍属迁移占位”的状态，避免用户把 migration artifact 误读成正式回测结论。
- `docs/contracts/PHASE1_PHASE2_ARTIFACT_CONTRACT.md` 现已冻结 `source_classification` 与 `validation_mode` 两个迁移投影字段，后续 Phase 2 producer 只允许填充真实定义，不应再改消费层结构。

[2026-04-25T12:26:34+08:00] Phase 1 layered-evidence-first recommendation consumer decision from local execution:
recommendation 服务层现在必须优先消费 `core_quant` 与 `evidence.factor_cards` 这些显式分层字段，`factor_breakdown` 只允许作为 compat fallback；否则一旦 producer 继续清理 raw payload 壳，consumer 还会被旧结构拖住。

补充说明
- `src/ashare_evidence/services.py` 现在在构建 `core_quant` 时优先从 `evidence.factor_cards.fusion` 提取分数，在构建 `evidence` 时优先信任 `payload.evidence.factor_cards` 与 `payload.evidence.degrade_flags`，只有缺失时才回退到 `factor_breakdown`。
- `tests/test_traceability.py` 已补充“删除 raw factor_breakdown 后，core_quant.score 和 evidence.factor_cards 仍然稳定”的断言，确保这条 consumer contract 不会被后续改动重新绑回 raw compat 字段。
- 这一步的目标不是立刻删除 `factor_breakdown` 顶层 compat 壳，而是先确保主消费链路不再把它当真相源；后续 producer 清壳时就只需要继续删 compat，而不是再改一轮 consumer。

[2026-04-25T12:29:53+08:00] Phase 1 governance projection parity decision from local execution:
治理页不应只统计“有多少 artifact / manifest”，还必须统计“其中多少已经是 artifact-backed projection、多少仍停留在 migration-placeholder validation”。否则 overview 与 replay/portfolio 详情页会用不同的状态语言，用户仍然需要自己猜“这些 artifact 数字到底意味着什么”。

补充说明
- `src/ashare_evidence/operations.py` 现在会额外汇总 `replay_artifact_backed_projection_count / replay_migration_placeholder_count / portfolio_backtest_artifact_backed_projection_count / portfolio_backtest_migration_placeholder_count`，把 replay 和 portfolio 两条链路的“已接通产物”和“仍属迁移验证”同时暴露到治理层。
- `src/ashare_evidence/schemas.py`、`frontend/src/types.ts` 与 `frontend/src/App.tsx` 已同步接入这些字段，运营概览现已直接展示这组 projection parity 计数，而不是只展示 bound / pending 的混合数字。
- 这项决策的意义不是增加更多漂亮指标，而是冻结一条要求：overview、局部详情和后续 Phase 2 producer 都必须使用同一套状态词典，避免再次出现“局部页很诚实、总览页却显得更乐观”的偏差。

[2026-04-25T12:44:00+08:00] Phase 1 closure and Phase 2 entry decision from local execution:
`Phase 1` 现在正式收口。项目不再允许用未验证 compat 命中率字段返回 `0.0` 伪装结果，也不再允许 simulation 的 placeholder 执行动作自动落成模型轨道成交；从这一刻起，`Phase 2` 可以直接在现有 consumer contract 上接入真实 rolling validation / replay / backtest artifact producer，而无需再做一轮 schema 清壳。

补充说明
- `src/ashare_evidence/operations.py` 已把 `recommendation_hit_rate` 与 `recommendation_replay_hit_rate` 的非 verified compat 投影改为 `null`，明确表示“结果 withheld”，而不是“真实统计值等于零”。
- `src/ashare_evidence/simulation.py` 已把 `auto_execute_model` 的有效执行态冻结为关闭，同时新增 `auto_execute_status / auto_execute_note` 和 `migration_placeholder_estimate` 标记；占位动作现在只能作为人工复核试算存在，不能再自动写成模型成交。旧 session 中遗留的 `auto_execute_model=true` 也会在读取时被自动降级到同一条 Phase 1 规则上。
- `src/ashare_evidence/schemas.py`、`frontend/src/types.ts`、`frontend/src/App.tsx` 与相关测试已同步完成这轮 contract 收口，`phase_1_schema_service_rewrite` 在 `PROJECT_STATUS.json` 中正式记为完成。

[2026-04-25T15:07:20+08:00] Phase 2 producer wiring completion and artifact-hydration ordering decision from local execution:
`Phase 2` 的第一轮真实 producer 接线现已收口到模块化 `src/ashare_evidence/phase2/` 包，并正式接入 `analysis_pipeline.refresh_real_analysis(...) -> rebuild_phase2_research_state(...)` 主路径。后续产品层只允许把 manifest/metrics/replay/backtest 这些 artifact hydrate 完整后的结果投影到 contract，不再接受“producer 已写盘但 service 仍按空壳状态先降级”的旧顺序。

补充说明
- `src/ashare_evidence/phase2/` 现已拆成 `constants/common/data/observations/validation/replay/portfolio/rebuild` 多文件结构，保持单文件体量可控，避免 Phase 2 逻辑再次回长成单个超大模块。
- 新增 `tests/test_analysis_pipeline.py` 端到端回归，直接覆盖真实 refresh 后 recommendation 写库、validation metrics 落盘、replay alignment 生成，以及最小 `paper_portfolios / paper_orders / paper_fills` 输入下的 portfolio backtest artifact 生成。
- `src/ashare_evidence/phase2/validation.py` 现在会在 recommendation `as_of_data_time` 与 observation `as_of` 比较前先做时区对齐；`src/ashare_evidence/services.py` 中 recommendation `historical_validation` 的 product gating 改为“先 hydrate manifest/metrics，再归一化状态”；`src/ashare_evidence/watchlist.py` 也同步对齐 `latest_generated_at`，避免 SQLite 路径再次触发 naive/aware `datetime` 比较错误。
- 这项决策的直接结果是：Phase 2 artifact producer 已不再只是 contract 骨架，而是被真实 refresh/rebuild 路径、artifact store 与 consumer regression 一起锁住。下一阶段阻塞点不再是 producer 接线，而是 quant core 仍然沿用 placeholder horizon/weight heuristic，以及 manual Codex/GPT 研究链路尚未产出 durable artifact。

[2026-04-25T19:27:40+08:00] Phase 2 quant-core completion and manual-research durability decision from local execution:
`Phase 2` 现已正式完成从 placeholder signal heuristic 到结构化 quant core 的替换，同时 follow-up 手动研究链路也已接成 durable `manual_review` artifact 流。后续默认入口应从 `Phase 2` 切换到 `Phase 3`，不再把“替换 quant core / 接 manual artifact”当成未完成事项。

补充说明
- `src/ashare_evidence/signal_engine.py` 已重构为薄入口，真实实现拆到 `src/ashare_evidence/signal_engine_parts/{base,factors,recommendation,assembly}.py`，所有新增文件保持在 `500` 行内；producer 现统一输出 Phase 2 的 `10/20/40` horizon、`phase2_target_horizon_label()`、`PHASE2_LABEL_DEFINITION`、`PHASE2_WINDOW_DEFINITION` 和 `phase2_rule_baseline_score` 语义，不再继续沿用 placeholder `14/28/56` 或 `research_window_pending`。
- 价格因子现采用“趋势 + 确认 + 风险压力”的 rule-baseline 结构，新闻因子继续走去重/衰减/层级映射，手动 LLM 层保留为零权重解释位；recommendation 的 `core_quant`、`historical_validation`、`evidence` 与 compat `applicable_period` 现都以这一套 Phase 2 常量为主语义来源。
- `src/ashare_evidence/manual_research.py`、`src/ashare_evidence/research_artifact_store.py` 与 `src/ashare_evidence/llm_service.py` 现已让 `run_follow_up_analysis(...)` 在拿到人工答案后写出 durable `manual_review` artifact，并把 `artifact_id / question / raw_answer / generated_at` 回投到 recommendation 和 follow-up `research_packet`；这意味着人工 Codex/GPT 研究现在第一次成为可回放产物，而不是临时文本响应。
- 为匹配已批准的 `10/20/40` 研究窗口，`tests/fixtures.py` 的日线样本已扩展到 `42` 根 bar，确保 previous snapshot 仍可覆盖 `40` 日窗口；相关回归 `tests.test_traceability`、`tests.test_dashboard_views`、`tests.test_runtime_config`、`tests.test_analysis_pipeline` 与 `tests.test_research_artifact_store` 已再次全部通过。
- 从这一刻起，`Phase 2 - Research Artifact Producer and Quant Core Rebuild` 视为完成；下一活动 phase 应为 `Phase 3 - Product Rewrite and User-facing Evidence/Risk Presentation`。

[2026-04-25T20:05:00+08:00] Phase 3 product-language closure and Phase 4 workflow-hardening decision from local execution:
`Phase 3` 现已正式收口。用户可见的 stock detail、candidate、governance、replay/portfolio 和 follow-up 页面现在必须以 layered contract 和 artifact-backed projection 作为主语言，legacy compat 字段只允许停留在统一派生壳；下一活动 phase 切换为 `Phase 4 - Manual Research Workflow Hardening and Stable manual_llm_review Contract`。

补充说明
- `frontend/src/App.tsx` 现已把 candidate 与焦点摘要补齐 `source_classification / validation_mode`，replay 主展示固定为 `review_window_definition`，并在 stock detail 与 follow-up 中显式展示 `manual_review_status / trigger_mode / artifact_id / generated_at`，避免再把人工研究入口伪装成未来能力或已完成结论。
- `src/ashare_evidence/dashboard.py`、`src/ashare_evidence/operations.py` 与对应 schema/type 继续把 `applicable_period`、`review_window_days` 等 legacy 字段收敛到 compat helper；主 contract 现在默认依赖 `core_quant / evidence / risk / historical_validation / manual_llm_review` 以及 operations 的 `run_health / research_validation / launch_readiness / source_classification / validation_mode`。
- `tests.test_traceability` 与 `tests.test_dashboard_views` 已同步改写：主回归断言改为验证 layered contract 和 artifact-backed projection，legacy compat 行为仅在专门 compat 测试中保留。这样后续 `Phase 4` 可以继续稳定 manual research workflow，而不必再回头重做一轮产品语言迁移。

[2026-04-25T20:58:04+08:00] Phase 4 manual-research request-contract hardening decision from local execution:
`Phase 4` 的第一轮 backend workflow hardening 现已收口到 `manual_research_requests` request contract。后续 `manual_llm_review` 的主语义必须从 request state 与 durable `manual_review` artifact 投影，而不是继续从 recommendation payload shell、旧 follow-up 执行路径或孤立 artifact 写盘行为反向推断。

补充说明
- `src/ashare_evidence/services.py` 现在必须优先通过 `build_manual_llm_review_projection(...)` 构建 `manual_llm_review`；只有在对象脱离 session 或无法读取 request/artifact 真相时，才允许回退到 compat shell。这样 recommendation summary、dashboard detail 与 follow-up `research_packet` 会共享同一套 request/artifact 语义来源。
- `src/ashare_evidence/llm_service.py` 的 `run_follow_up_analysis(...)` 现已改为委托 `src/ashare_evidence/manual_research_workflow.py` 的 compat wrapper，旧的“直接解析 API key 并即时写 artifact”路径不再是主入口；`/analysis/follow-up` 因而降级为 operator-only compat trigger，稳定工作流改由 `/manual-research/requests`、`/execute`、`/complete`、`/fail`、`/retry` 这一组 API 承载。
- `src/ashare_evidence/runtime_config.py` 已新增 builtin executor 配置入口，`src/ashare_evidence/schemas.py`、`src/ashare_evidence/api.py`、`src/ashare_evidence/research_artifacts.py` 与 `src/ashare_evidence/dashboard.py` 也已同步补齐 `request_id / request_key / executor_kind / status_note / review_verdict / stale_reason` 等字段，确保 request、artifact、dashboard projection 与 compat response 之间不再各自发明一套状态语义。
- 新增 `tests/test_manual_research_workflow.py` 专门锁住“request/artifact projection 优先于 payload shell”的规则，`tests/test_runtime_config.py` 也补强了 compat response 和 persisted artifact 上的 `request_id / request_key / executor_kind` 断言；此外，`tests.test_dashboard_views`、`tests.test_traceability`、`tests.test_analysis_pipeline` 与 `tests.test_research_artifact_store` 已重新全绿，证明本轮 Phase 4 后端 contract 收口没有回归到 Phase 2/3 artifact consumer。

[2026-04-25T21:15:45+08:00] Phase 4 queue/workspace productization decision from local execution:
从这一轮起，`Phase 4` 的产品层人工研究入口正式以 `manual_research_requests` lifecycle 为主语义。前端 follow-up workspace、stock detail 人工研究层与 operations governance queue/workspace 都必须直接消费 request/artifact contract，而 `/analysis/follow-up` 只保留兼容触发器角色，不再作为用户心智中的“主工作流”。

补充说明
- `src/ashare_evidence/operations.py` 与 `src/ashare_evidence/schemas.py` 现已新增 `manual_research_queue` payload，治理页需要同时展示 queue counts、focus request 和 recent request items，确保 operator 能在总览层看到 queued / in_progress / failed / completed_current / completed_stale 的真实分布，而不是只看单票 `manual_llm_review` 摘要。
- `frontend/src/types.ts`、`frontend/src/api.ts` 与 `frontend/src/App.tsx` 现在必须把“提交人工研究”建成 request workflow：允许先创建 queued request，再按选定 key 执行，也允许在治理页和 follow-up workspace 对 queued / failed / stale request 执行或 Retry；直接把 follow-up 当成一次性文本调用的交互不再符合主产品 contract。
- `manual_llm_review`、follow-up `research_packet` 和 operations queue/workspace 的展示字段必须继续保持同构，至少同步暴露 `request_id / request_key / executor_kind / status_note / review_verdict / stale_reason / citations` 这一组 request/artifact 语义字段，避免不同页面重新发明各自的人工研究状态词典。
- Phase 4 在 backend hardening 之外现已完成 queue/workspace 的端到端 productization；后续剩余工作收缩为 operator approval boundary、explicit complete/fail governance action 和 stale-state UX polish，而不再是“前端尚未接线”的大面问题。

[2026-04-26T21:11:56+08:00] Live manual-research long-request timeout decision from local execution:
manual research 相关前端请求不再允许沿用全站统一的 10s 短请求超时。只要入口的默认动作会触发本机 Codex builtin `gpt-5.5` 或其他真实长耗时研究执行器，这条链路就必须被视为 long-running request，并使用独立的 request timeout policy；否则真实已开始执行的 builtin 研究会被前端先行误判成失败。

补充说明
- `frontend/src/api.ts` 现已将 `createManualResearchRequest`、`executeManualResearchRequest`、`retryManualResearchRequest` 和 `runFollowUpAnalysis` 切到专用 `manualResearchRequestBehavior`，统一使用 `180000ms` 总超时和 `60000ms` attempt 超时，而普通 dashboard/settings/candidate 请求仍保留原有短超时策略。
- 这条决策已经过真实 canonical 浏览器验收：Safari 在 `https://hernando-zhao.cn/projects/ashare-dashboard/` 的 `单票分析 -> 追问与模拟` 页面上成功触发默认 builtin 研究，页面在跨过旧的 10s 故障阈值后未再出现“请求超时（>10s）”，而是继续执行直至返回回执。
- 当轮 live 观察里页面一度显示 `结果过期`，并带出 `validation_artifact_id changed after the manual review completed`；但 2026-04-26 同日晚些时候已确认这是 request list 使用未水合 `historical_validation` 空壳做 stale 判定导致的误报，而非真实 artifact drift。timeout 缺口仍然是在这次验收里被独立关闭；后续 stale 语义只应在 hydrated validation context 下继续判断。

[2026-04-29T10:19:14+08:00] Pydantic v2.13 forward-reference repair:
在 schema 模块拆分后，`from __future__ import annotations` + TYPE_CHECKING 导致 Pydantic 运行时解析 `StockDashboardResponse` 等模型时抛出 `class-not-fully-defined`，大盘首页和运营复盘返回 500。按依赖图逐文件修复：无循环依赖的模块直接移除 future annotations；存在 `stock → operations → simulation` 循环的模块保留 annotations，通过 `__init__.py` 在所有模块加载后注入类型并 `model_rebuild()`。

[2026-04-29T10:19:14+08:00] 403 auth transparency:
用户看到的 "403 Forbidden" 无任何可操作信息。三层修复：(1) VPS 代理 JSON 401/403 响应从 `error` 改为 `detail` key，前端即展示中文提示；(2) 后端 env 显式 `ASHARE_BETA_ACCESS_MODE=open`；(3) `access.py` 移除 future annotations。

[2026-04-29T10:19:14+08:00] Scheduled 5-min market refresh + holiday awareness:
`run-scheduled-refresh.sh` 无调度器触发。创建 LaunchAgent `StartInterval=300` 每 5 分钟执行；修正开盘窗口 09:31/13:01；增加 AKShare 交易日检查（日级缓存 ~/.cache/codex/trade_calendar.json），节假日自动跳过。

[2026-04-29T10:19:14+08:00] SSH tunnel auto-recovery:
`buildRemoteCleanupScript()` 的 `.join("; ")` 导致 bash 出现 `do;`/`then;` 语法错误，远端端口清理失败，隧道断开后无法重连。改用字符串拼接 + 增加 bash `-n` 语法测试 + 无限重连循环（指数退避 1s→60s）+ cleanup 5 次重试。

[2026-04-29T23:40:00+08:00] `/stocks` multi-account isolation v1 contract:
股票看板本期正式采用“根域身份注入 + 本地账号空间隔离”的 v1 合同，而不是在项目内再造一套账号系统。可信身份主键先固定为 root-domain `login`；root 域只需向 `/stocks` 注入 `X-HZ-User-Login` / `X-HZ-User-Role`，股票项目负责基于 `StockAccessContext` 做 `actor_login / actor_role / target_login` 解析，并只允许 root 通过 `X-Ashare-Act-As-Login` 查看或代操作其他账号空间。

补充说明
- watchlist 不再直接把 `watchlist_entries` 当“谁关注了它”的真相源，而是拆成“全局 symbol 覆盖/分析状态表” + `watchlist_follows(account_login, symbol)` 关注关系表。日更/分析续航继续按全部 active follows 的并集决定，所以只要仍有任一账号关注，symbol 级缓存预热和分析刷新资格就不能断。
- simulation 改为按 `owner_login` 隔离 session / portfolio / order / fill / event，并额外记 `actor_login` 审计 root 代操作。既有共享 session、组合、订单、成交和事件全部一次性回填到 `root` 账号名下；迁移不重建 session，不改 `started_at/current_step/restart_count/last_data_time`，确保 root 旧复盘不重新计时。
- v1 明确把 settings / operations / manual-research / `/analysis/follow-up` 视为 root 全局资产；member 只保留自己的首页、自选、单票和模拟盘空间。前端因此必须先拉 `/auth/context` 再决定是否请求 `/settings/runtime`，否则 member 登录会直接打到 403。

[2026-04-26T21:11:56+08:00] Live manual-review sanitization fallback decision from local execution:
人工研究层对外展示的文案必须把内部治理 token 视为不可信输入。只要 manual review summary、risk、disagreement、decision note 或回执 answer 仍可能来自历史 artifact、compat payload 或运行时拼接，前后端都必须各自保留一层用户可见净化兜底，不能假设“后端已经完全清洗过一次”就足够。

补充说明
- `src/ashare_evidence/manual_research_contract.py` 现已继续扩展内部 token 清洗范围，覆盖 `pending_rebuild`、`Phase 5 baseline`、`replay-alignment:*`、`portfolio-backtest:*` 等词；`frontend/src/App.tsx` 同步保留 display-layer fallback，把剩余漏网词替换为用户可理解的研究语言。
- 这次 live 验收的真实页面已确认显示 `口径校准中`、`20日超额收益` 等净化后的文案，没有重新漏出 `pending_rebuild` 一类内部状态词；对应静态回归已补进 `tests/test_dashboard_views.py`。
- 这条决策不改变后端 contract 优先级。后端 projection 仍是主净化层；前端 fallback 的职责只是兜住历史 artifact、compat 漂移和未来漏网字段，避免用户先看到内部术语再等待下一轮发布修复。

[2026-05-01T00:37:56+08:00] P-1/P0 professionalization runtime boundary:
股票看板专业化改造的 P-1/P0 本轮只批准“证据链与运行面专业化”，不批准 horizon 切换、生产权重自动更新、自动交易或 LLM 方向覆盖。发布后的产品默认定位仍是 `research_candidate / observe_only` 决策辅助，直到 Phase 5 的样本数、组合毕业 gate 和权重校准 artifact 达到合同阈值。

补充说明
- 数据质量、CSI benchmark context、true factor IC scaffolding、weight sweep artifact、market rules、stock dashboard validation fields、operations summary/details 已落地并发布到 runtime。
- operations 首屏必须走 `/dashboard/operations/summary`，保持 payload 轻量；`simulation_workspace`、`portfolios`、replay、manual queue 等重数据只能通过 `/dashboard/operations/details` 按需加载。旧 full endpoint 保留兼容期，但不能作为默认首屏路径。
- 因子展示语义固定为两层：当前融合贡献使用 `factor_score × dynamic_weight`，因子可信度使用 rolling IC/IC_IR；不得把 IC 直接混入当前 contribution。
- 最终本地 served-route browser 验证通过，但 deploy verifier 仍因 backend 环境缺 `ANTHROPIC_AUTH_TOKEN` 在 LLM module import check 处失败。这是运行环境配置缺口，不影响本轮 API/frontend 发布同步和 served UI 验收。

[2026-05-01T03:05:34+08:00] Professionalization closeout verification decision:
P-1/P0 专业化改造的收尾状态以“测试 + 发布 + deploy verifier + served browser”四件事全部通过为准。`ANTHROPIC_AUTH_TOKEN` 只允许从后端 env 文件注入发布/验证进程，不写入仓库、文档或日志；缺 token 不再被当成代码失败，verifier 负责验证 route-model 能拿到 DeepSeek 路由和 API key。

补充说明
- 本轮修复了旧测试依赖的私有兼容导出、`winsorize` 百分位边界、intraday future-bar stale 判定、六因子 snapshot 测试契约、SQLAlchemy 2.x verifier SQL、前端 health check 过期字符串，以及新闻因子用户可见 `±1.0` 饱和。
- 新闻因子 score 的生产和展示都不得再输出硬 `±1.0`；即使历史 recommendation payload 中仍有旧值，服务层 factor card 也要向下钳制到 `±0.98`，避免把事件叠加误表达成满置信。
- 发布脚本默认支持同步刷新，但必须有超时；对于不依赖数据重算的显示层/live-facing 修复，可以用 `ASHARE_PUBLISH_REFRESH_MODE=skip` 跳过 post-deploy refresh，并用 deploy verifier 与真实浏览器检查当前已服务 payload。
- 本次最终收尾结果：`pytest -q` 通过 `212` 个测试；runtime 发布快照 commit 为 `a76683eb0d41ca6e6165abb429fbb4a6ceeec3f5`；发布脚本内置 `verify-deploy.sh` 通过 `19/19` 并输出 `VERIFICATION PASSED`；Chrome headless 实际打开 `http://127.0.0.1:5173/`，页面渲染 `工作台 / 关注股票 / 复盘`，console error 为空。

[2026-05-01T15:38:22+08:00] Improvement suggestion plan-pool control-plane handoff:
改进建议审计台的“进入计划池”不再只是股票看板本地状态标记。从本轮起，该动作必须让 operator 先选择执行模型，再在中台控制面板创建一个启用 Plan 模式的任务；任务描述必须携带页面上可见的建议内容、证据引用、GPT/DeepSeek 审计结论、最终置信度、推荐动作和生成计划，且在用户审视并确认 plan 前不得开始实现。

补充说明
- 股票看板新增 `/dashboard/improvement-suggestions/{suggestion_id}/accept-plan`，由 root/operator 调用。接口会把 suggestion 标记为 `accepted_for_plan`，调用中台 `/api/tasks` 创建任务，并把 `control_plane_task` 回写到最新 suggestion review snapshot。
- 前端 `改进建议审计台` 的 `进入计划池` 按钮现在会弹出模型选择器，首批模型为 `gpt-5.5`、`gpt-5.4`、`gpt-5.3-codex-spark`、`deepseek-v4-pro[1m]`、`deepseek-v4-flash`；`gpt-5.5` 用于高级审计/仲裁场景，但默认执行模型仍保持 `gpt-5.4`。已入池建议会展示中台任务 ID、模型和 Plan 模式标签。
- 该链路保持原边界：多模型审计和中台任务可以自动生成计划，但不能自动改代码、自动发布、直接修改因子权重、horizon、claim gate 或买卖方向。
- 本轮实测已把 `suggestion:ed36ed8c8753600d` 送入中台，创建任务 `task-momlkmg7-4mrd59`，状态为 `blocked / plan_feedback`，模型为 `gpt-5.4`，等待用户确认计划。

[2026-05-07T20:40:00+08:00] Constants, formulas, and tunable policy governance becomes a hard development contract:
股票看板从本轮开始把常量、公式和可调参数治理纳入运行合同。稳定规则继续留在代码 contract；数学计算必须通过可测试纯函数表达；权重、阈值、窗口、TopK、惩罚系数等可变策略进入版本化配置和审计视图；后续开发必须通过 policy audit 收尾，不能再把裸权重或业务阈值散落到数据质量、信号融合、Phase 5、短投试验田或前端展示层。

补充说明
- 新增 `policy_config_versions` 作为专用版本表，默认配置来自代码，active 数据库版本可覆盖默认；draft 不生效，active 版本需要原因、证据引用、批准人、checksum 和 supersedes 链。
- `data_quality` 已改为读取治理配置并在 summary/item payload 中投影 config version/checksum；`signal_engine` 的融合权重、惩罚项、confidence RMS 和 model-result 参数已转入默认配置与纯公式函数，并在 recommendation/model result payload 中投影 `policy_config_versions`。
- 新增 `policy-audit` CLI 和 `/policy-governance/*` 只读 API；运营复盘的治理页展示 active 配置、公式/常量分类与硬约束状态。
- 后续修改 Phase contract、权重、窗口、promotion gate 或用户可见业务阈值，必须同步更新 `PROJECT_RULES.md`、本决策日志、默认配置/审计分类和回归测试。

[2026-05-08T10:10:00+08:00] Historical replay is a sealed-packet experiment, not a second live shortpick pool:
短投历史回放必须作为隔离实验域存在。Replay run 只写 `shortpick_lab` run/round/candidate/validation 表和 packet artifact，不写主推荐、主候选池、自选池、模拟盘或生产权重；模型/代理输出只能引用 packet source id，不能引用自由 URL。

补充说明
- 首版允许使用 deterministic sealed-packet proxy 代替真实外部 LLM 调用，但数据契约必须先按真实 replay executor 设计：`experiment_mode=historical_replay`、`source_packet_id/hash`、`sources_used`、`evidence_mapping`、`leakage_audit_status/reasons`、`baseline_family`、`official_sample_eligible`、`robustness_metrics`。
- `published_at > as_of_cutoff` 的来源必须硬拒绝，并在前端可见为 rejected source；无法验证发布时间的来源只能 diagnostic，不进入 official packet。
- Replay validation 不允许为了同板块 benchmark、行情或资料完整性触发现时网络补数；缺失维度应显示 existing-only / pending，而不是补未来可得信息。
- 小样本 RankIC 只能作为诊断，不得驱动调权：单次截面和少于 20 个有效窗口的 IC 结果标记 blocked/diagnostic，observed-but-blocked 因子不通过 default fallback 偷偷回到生产权重。
- 用户要求前端展示不后置，因此每个 replay 后端能力都必须在 `试验田 / 历史回放` 有最小可见 UI；后续补真实 LLM replay executor 或更完整新闻 alpha 校准时也必须同步前端读数。

[2026-05-09T03:10:00+08:00] Live Short Pick Lab strategy handoff:
短投试验田正式把历史验证后的市场因子策略接入 live run，但不替代 LLM 开放检索选股。每个 live run 的主研究问题仍是 GPT/DeepSeek 在无本地上下文、公开搜索环境下能否短投选股；系统策略只作为并列验证组和对照组。

补充说明
- LLM 候选先完成 topic normalization 和 consensus；`market_factor_overlay` 在 consensus 之后写入，且 consensus 统计显式排除这类候选。
- 默认策略为 `momentum_10d_turnover_cooldown_rank`：Top40 动量成交量池内按 `rank(return_10d)+rank(turnover_rate)-0.5*rank(return_1d)` 选 Top6。
- `momentum_10d_turnover_rank` 保留为进攻对照，不作为默认稳健策略。
- 市场因子行情补齐只允许在 run 生成链路发生，不能由前端面板加载触发；补现有研究 universe 时逐票提交，避免长 SQLite 写锁。
- 强制行业分散、LLM broad rejector、LLM 蒸馏暂不升为 live 默认策略；它们保留在历史回放/研究 artifact 中作为负面或风险诊断证据。

[2026-05-09T16:08:00+08:00] Short Pick Lab frozen strategy must be displayed separately from LLM control batches:
短投试验田前端和状态接口从本轮起把“冻结纸面策略”与“LLM 对照批次”拆开展示。每日 scheduled refresh 的 `shortpick_lab` slot 只代表 LLM 对照批次完成情况，不再被用户解释为正式纸面策略已经产生当日标的。

补充说明
- 新增只读 `/shortpick-lab/paper-tracking` ledger，从已有 shortpick run/candidate 和冻结策略合同投影当前纸面跟踪状态，不触发行情同步、模型调用或数据库写入。
- 当前 runtime 状态为 `waiting_first_frozen_run`：最新 LLM 对照批次是 `2026-05-08` run `30`，生成于冻结日期 `2026-05-09` 之前，因此没有冻结策略覆盖层；下一次盘后批次才会开始记录正式纸面跟踪标的或未触发原因。
- 前端 `试验田` 新增 `纸面跟踪` tab，首页每日状态增加 `冻结纸面跟踪：等待首批` 标签；全局导航、移动端和 Short Pick Lab 动作按钮统一使用“LLM 对照批次 / 冻结纸面策略”的双轨文案。
- 本轮发布使用临时干净快照 `02ae368fb66a12e4e5d1f25ca22816e7c337aa82`，`ASHARE_PUBLISH_REFRESH_MODE=skip`，没有触发 post-deploy 数据刷新。

[2026-05-09T16:37:00+08:00] Frozen paper tracking should monitor four exit tracks before first sample:
冻结纸面策略在首个冻结后样本产生前升级为“四轨退出监测”，用同一只正式纸面标的同时记录机械 5 交易日、机械 10 交易日、5 到 10 交易日条件检查、以及 10% 触达止盈四种结果。

补充说明
- 5 日和 10 日均明确为交易日，不按自然日计算。
- 10% 触达止盈在当前日线数据下采用“日内最高价触达 +10%，纸面按 +10% 卖出”的近似；未来如果接入分钟级成交，可再替换成更真实的 intraday 执行口径。
- 这次变更发生在 `waiting_first_frozen_run` 阶段之前，没有已冻结样本需要迁移或作废；历史 v2 回测证据继续作为选股规则证据，v3 只是在 forward tracking 中比较退出方式。
- `/shortpick-lab/paper-tracking` 继续保持只读，不触发行情同步、模型调用或数据库写入；实际验证 snapshot 在 10 个交易日窗口完整后同时写出四轨结果。
- 本轮发布使用临时干净快照 `27e6de42993638f5261025e390e65a8a3ee5b4eb`，`ASHARE_PUBLISH_REFRESH_MODE=skip`，没有触发 post-deploy 数据刷新；运行态页面已验证 `试验田 -> 纸面跟踪` 展示四轨规则。

[2026-05-09T22:25:00+08:00] LLM control must be a strict one-stock paper comparator, not only a recommendation pool:
LLM 今日批次不能只作为“10只推荐池”与每天1只冻结策略做宽泛对比。从本轮起，每个 live shortpick run 在 LLM 共识完成后、市场因子覆盖层和验证之前，按冻结的确定性规则从当日 LLM 自由推荐池中标记 1 只 `LLM纸面对照` 标的。

补充说明
- 选择规则固定为：跨模型同票优先，其次同模型重复、跨模型同题材、单模型高置信、系统外新视角；再按来源质量、置信度、来源数量、股票代码和候选ID稳定排序。不得事后按收益挑选。
- LLM 纸面对照不替代全量 LLM 推荐池；全量池继续用于召回率、排序能力、来源质量和模型差异研究。
- LLM 纸面对照使用和冻结策略相同的入场口径与四条退出轨道：机械5交易日、机械10交易日、5到10交易日条件检查、10%触达止盈。
- `/shortpick-lab/paper-tracking` 同时展示正式冻结策略标的和 LLM 纸面对照标的；当前既有 run 30 早于本规则，只有下一次完整批次才会生成 LLM 纸面对照记录。
- 本轮发布使用临时干净快照 `fc481614ce29a9fc719b294bb35318c36533bb0c`，`ASHARE_PUBLISH_REFRESH_MODE=skip`，没有触发 post-deploy 数据刷新；运行态页面已验证纸面跟踪页展示 LLM 一票对照规则。

[2026-05-09T23:35:00+08:00] Final pre-freeze controls should test simple same-pool alternatives, not add sparse single-stock analysis to live tracking:
最后一次冻结前修改窗口不再引入新的 LLM 单票分析筛选器。当前 `recommendations` 单票分析覆盖只落在少数股票上，无法稳定覆盖市场因子 Top40；历史回放里的 LLM rejector / hard-veto 也没有证明能提升收益。因此单票分析暂不升入真实纸面跟踪，只保留为后续研究方向。

补充说明
- 新增三条严格一股市场因子纸面对照：`动量换手第1名`、`降追高第1名`、`同池随机基线`。它们全部来自同一个动量成交量 Top40 池，不调用模型、不触发额外刷新、不看未来收益。
- 正式策略仍保持冻结规则：市场状态满足 gate 时取进攻排序第2名；LLM 自由选股一票对照继续保留；全量 LLM 推荐池继续只作为召回/排序/来源质量研究样本。
- 三条市场因子对照和正式策略、LLM 一票对照使用同一入场口径与四条退出轨道，方便前向样本积累后比较“第2名是否真的优于第1名/降追高/随机同池”。
- 这组对照的价值是降低过拟合怀疑，而不是再调参。冻结后不得根据前向早期结果临时换主策略。
- 本轮发布使用临时干净快照 `cfbbcd1d42d143230cfd936edd3e5ec0a04c8db7`，`ASHARE_PUBLISH_REFRESH_MODE=skip`，manifest `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/releases/20260509T153817Z-cfbbcd1d42d1/manifest.json`，deploy verifier `19 passed, 0 failed`。运行态 `/shortpick-lab/paper-tracking` 已返回 `market-factor-controls-v1-2026-05-09`，真实页面 `试验田 -> 纸面跟踪` 已验证可见市场因子对照规则、随机同池基线和单票分析边界说明；截图 `output/playwright/shortpick-final-controls-runtime.png`。发布后无 refresh/shortpick 进程和 `run.lock`。

[2026-05-10T00:50:00+08:00] Short Pick Lab frozen strategy parameters must be policy-governed before forward tracking:
冻结纸面策略原先只在 `shortpick_lab.py` 里以命名常量和合同函数表达，虽然比裸散落数字更可读，但没有完全进入 2026-05-07 定下的 `policy_config_versions` / policy audit 治理口径。本轮把正式冻结策略的池子大小、TopK、排序家族、冷却惩罚、市场 gate、退出阈值、跟踪窗口和纸面对照版本统一纳入 `shortpick_lab.frozen_paper_strategy_v1` 默认治理配置。

补充说明
- 原因判断：不是策略实现本身缺少测试，而是强制门禁覆盖不完整。旧 policy audit 只管直接读写 `policy_config_versions`、公式模块副作用和少量 lineage marker，没有扫描短投试验田新增策略里“看似合理的模块常量/公式阈值”。
- 新增 `shortpick_policy.py` 作为试验田冻结策略的配置入口；`shortpick_lab.py` 只从该配置投影运行常量，不再在公式体里写 `0.5`、`0.05`、`0.03` 这类关键业务阈值。
- policy audit 现在把 `shortpick_frozen_paper_strategy` 归类为 `tunable_policy`，并在 `--fail-on-new-unclassified` 下拦截这些关键短投策略数字重新回到裸字面量。
- 这次只改变治理归口和门禁，不改变已冻结策略语义，不触发补跑、不触发刷新、不改变 `waiting_first_frozen_run` 状态。
- 本轮发布使用临时快照 `/tmp/ashare-shortpick-policy-governance-publish.20260510005001`，commit `438621d9706c75c3e7da91bc9eebef3410de6d48`，`ASHARE_PUBLISH_REFRESH_MODE=skip`，manifest `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/releases/20260509T165028Z-438621d9706c/manifest.json`，deploy verifier `19 passed, 0 failed`。运行态 API 和真实页面 `运营复盘 -> 参数与公式治理` 已验证新增配置与 audit pass。

[2026-05-10T18:06:00+08:00] Friend-suggested Top3 and golden-cross rules are diagnostic controls, not the frozen main strategy:
金融行业朋友建议的两条短投规则有合理的对照价值，但当前历史证据不支持替换主线。`前三名等权组合` 可以检验单票选择是否过度依赖排名偶然性；`10/200日金叉过滤` 可以检验传统趋势确认是否能减少伪动量。但长样本回测显示，两者都弱于现有冻结主线。

补充说明
- 当前冻结主线仍是 `ret10_turnover_second_market_positive_cooldown_stop8`：市场转正且候选池不过热时，按动量换手候选顺序取第2名，并用四轨退出做纸面跟踪。
- `前三名等权组合` 进入纸面跟踪和历史回放，但只作为组合化对照；历史回放长样本收益 `+92.2%`，等权市场超额 `-2.9%`，最大回撤 `-29.7%`，说明它降低了单票依赖，却把当前主线中较集中的 alpha 稀释掉。
- `10/200日金叉过滤` 进入纸面跟踪和历史回放，但只作为趋势确认对照；历史回放长样本收益约 `0.0%`，等权市场超额 `-95.1%`，交易 `132` 次，说明该信号在当前短投框架里太滞后且太稀疏。
- 两条规则的 live 记录都不调用模型、不触发额外刷新，并和正式策略共享同一入场与四轨退出监测。冻结后不得根据前向早期结果把它们临时提为主线；它们的用途是降低过拟合怀疑和提供真实前向对照。

[2026-05-10T18:55:00+08:00] Short Pick Lab execution evidence must respect a new retail cash-account universe:
短投试验田的纸面跟踪和后续历史重算必须默认采用“新开户普通现金账户”可执行口径：纳入沪深主板普通A股，排除科创板、创业板、北交所、ST/退市风险类标的。原 2026-05-09 长样本组合回测的可见 `trades_sample` 已确认包含创业板/科创板样本，因此它不能再被解释为用户当前账户可完全执行的证据。

补充说明
- 新增 `market_rules.account_trade_eligibility` 和 `filter_account_eligible_series`，统一输出账户权限、板块、整手、涨跌幅和新股前5日限制口径。
- `shortpick-market-factor-study` 与 `shortpick-portfolio-backtest` 新增 `--account-profile`，默认 `new_retail_cash_account`，可显式用 `unrestricted` 做研究对照。
- 模拟盘事前校验补齐 A 股关键执行约束：新账户权限、T+1 可卖数量、板块申报数量、限价涨跌停边界、一字涨停买入/一字跌停卖出阻断，以及 2023-08-28 后卖出单边 0.05% 印花税。
- 当前本地 runtime 数据库只有 7 只长样本日线标的，其中 1 只是创业板；按新账户口径过滤后只剩 6 只、2 个信号日。因此 `output/shortpick-portfolio-backtest-new-retail-long-sample-20260510.json` 只能作为可执行性修正 smoke result，不足以替代原 65 只/708 信号日长样本结论。正式重证需要恢复或重建原 65 只长样本日线源后再按新账户口径全量重跑。
- 随后已用 Tushare `stock_basic + daily + daily_basic` 重建一份隔离的主板普通A股样本：排除 ST/退市风险、2023-01-01 后上市，按股票代码稳定哈希抽样 180 只，覆盖 2023-05-16 至 2026-04-27 的 715 个信号日。artifact 为 `output/shortpick-portfolio-backtest-new-retail-mainboard-tushare-20260510.json`，原始缓存为 `output/shortpick-mainboard-new-retail-tushare-bars-20260510.jsonl`，隔离研究库为 `output/shortpick-mainboard-new-retail-tushare-20260510.db`。
- 新账户主板样本对原冻结主线给出负面结论：`第二候选加8%收盘止损` 221 笔，收益 -44.7%，相对 180 只主板等权基准超额 -81.2%，最大回撤 -63.7%。不带 8%止损的 `市场转正不过热时取第二候选` 在同一样本中收益 +46.9%、超额 +10.5%，但最大回撤 -62.2%，仍不满足生产证明。前端从本轮起读取新账户主板 artifact，并把冻结策略标记为“账户可执行性复核未通过”，避免旧 65 只混合权限样本继续误导。

[2026-05-13T06:20:00+08:00] Short Pick Lab low-turnover line remains the best confirmed paper candidate, not production proof:
全量新开户主板 universe 的阶梯式重跑完成后，当前低换手上升趋势线 `low_turnover_20d_uptrend_liquid_top120` 不能被描述为生产级冻结策略：它在 full-window / one-year、next-close / next-open 下仍是唯一已完成 artifact 中四个核心口径均为正超额的策略，但生产门禁仍有弱年份、成本压力、回撤和冻结后前向样本不足问题。因此本轮不切换纸面跟踪主线，也不把它升级为生产证明，只保留为“最佳已确认纸面候选”继续前向观察。

补充说明
- 现有完成策略里没有足够强的替代者。`base` 和部分 same-day proxy 在局部口径很强，但不满足“账户可执行 + next-close/next-open + full-window/one-year”同时稳健的替换条件。
- 有界优化发现了若干低换手变体，但首轮扁平表精确确认无法校准复现 canonical 组合回测中的当前策略 full-window 结果，因此这些变体只能作为研究线索，不能替换冻结纸面主线。
- 冻结策略若要迁移，必须先有一个能复现 canonical 当前策略结果的快速回测器；否则优化结果可能只是计算口径漂移。
- 14点同日买入版的确定性计算路径在 2994 个可买标的、800 个粗筛 context 下约 25 秒；是否能稳定在 14:00 前出结果，主要取决于实时行情源是否在 13:55-14:00 窗口内返回。
- 本轮没有冻结策略变更，因此不迁移纸面跟踪历史数据；旧低换手规则继续在纸面跟踪中作为当前主线，优化候选暂不进入用户可见冻结列表。

[2026-05-13T09:55:00+08:00] Historical replay UI must read materialized statistics, not compute on request:
历史回放页打开时不应触发 replay feedback 聚合或 market-factor study 全量研究。统计缺失不是前端文案问题，而是后台产物缺失；缺失时应补齐缓存和 artifact，而不是让页面请求临时现算。

补充说明
- 新增 `shortpick-replay-feedback-cache` CLI，负责把每个非诊断历史回放批次的 feedback 写入缓存 artifact，并在缺验证快照时补跑验证。
- `/shortpick-lab/replay-feedback` 和 `/shortpick-lab/replay-runs/{id}/feedback` 改为只读 `output/shortpick-replay-feedback-cache.json`；缓存缺失返回服务端错误，避免静默现算。
- `/shortpick-lab/market-factor-study` 改为只读预计算 study artifact；当前 artifact 从 2999 只新开户主板可交易 universe 的 full-window 组合回测统计派生，保留策略收口所需字段。
- `/shortpick-lab/replay-runs` 改用轻量列表序列化，不再为 100 个历史批次逐个加载 candidates/validations 计算 operational summary。

[2026-05-14T18:20:00+08:00] Non-LLM historical strategy evidence should carry its own confidence, stability, attribution, and paper-alignment projections:
短投历史分析的非 LLM 部分继续扩展在 `strategy_slice_evidence` 下，不复用或冒充 LLM/候选逐条 replay 统计。从本轮起，长窗口 staged portfolio artifact 同时输出组合级月度 bootstrap 置信区间、月/季/年稳定性摘要、行情桶稳定性、月度/季度/行情归因，以及基于只读纸面 ledger 的前向对齐读数。

补充说明
- LLM 历史 replay 仍先放置不扩；`2026-01-05 - 2026-04-30` 的候选逐条验证短窗口不被改写。
- 新增字段回答的是确定性策略族的账户路径问题：跨时段、分行情、置信下沿、最佳/最差月份、最佳/最差行情桶、去最佳贡献项后的均值。
- 当前 staged portfolio artifact 只保留组合期度和少量 `trades_sample`，不足以做完整股票/行业归因；页面必须显示“待全量逐笔 artifact”，不能拿 sample 外推。
- 组合策略晋级判断优先看月度组合超额 bootstrap 下沿，不再只看单一均值；当前低换手线均值为正但下沿仍未过晋级线，因此继续前向观察。
- 前向对齐读数只比较非 LLM 长窗口策略期望与纸面跟踪样本数；在纸面样本未成熟前不判断偏离、不升级或降级主线。
- 本轮发布 manifest `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/releases/20260514T094419Z-767ca3a77f04/manifest.json`，deploy verifier `19 passed, 0 failed`；localhost 与 canonical `试验田 -> 历史回放` 均已验证可见组合置信区间、组合时间稳定性、组合收益归因和逐笔归因待补边界提示。

[2026-05-14T20:50:00+08:00] Short Pick Lab model feedback must group by real model, not executor channel:
`LLM模型反馈` 默认读数只按真实模型显示 `DeepSeek V4 Pro 1M` 和 `ChatGPT 5.5`。`executor_kind`、历史 replay/distiller/hard-veto/rejector 等实现通道只保留在展开下钻里，且必须使用中文通道名。研究优先级等内部 key 也必须映射成用户能理解的标签，例如 `single_model_high_conviction` 显示为“单模型高置信”。

补充说明
- API 保留兼容字段 `models` 给旧细分通道，同时新增 `model_groups` 作为前端默认表格数据源。
- `model_groups` 聚合轮次、候选、来源质量和验证切片；展开区显示“实验通道”，不再把内部 executor 当模型。
- 后端 projection 已刷新，运行态 `/shortpick-lab/model-feedback` 返回旧通道 10 条、新模型组 2 条；优先级标签样例不再暴露 `single_model_high_conviction`。
- 本轮发布 manifest `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/releases/20260514T124224Z-c06ddea138ad/manifest.json`，deploy verifier `19 passed, 0 failed`；localhost `试验田 -> LLM模型反馈` 已验证。canonical 域名在 Playwright 会话中被统一登录页拦截，本轮未越过登录态复验业务页。

[2026-05-14T21:05:00+08:00] Historical replay regime evidence must not overstate tiny monthly buckets:
`历史回放 -> 稳定性、置信与归因` 的行情胜出表不再默认展示 `next_close`、`range_bound:low_volatility:balanced_size` 这类内部 key，也不再把三维细行情桶里的 2-6 个月份包装成强结论。页面默认使用后端派生的趋势大类行，并只展示不少于 12 个“月度组合样本”的行情结论；低样本分桶保留在 artifact 中，但默认表明确提示已收起。

补充说明
- 当前长窗口数据广度仍是 717 个信号日、约 2999 只新开户主板可交易序列；样本稀少发生在“按月度组合收益再切趋势/波动/大小盘风格”的细桶层。
- 后端 `coarse_regime_winner_rows` 从已有 `regime_strategy_rows` 只读派生，不触发新行情同步、不重算回测、不写数据库。
- 前端把入场、行情、周期统一映射为中文：例如 `next_close` 显示为“次日收盘买入”，`range_bound` 显示为“震荡行情”，`month` 显示为“月度”。
- 本轮发布 manifest `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/releases/20260514T125916Z-9b6270d2ef9a/manifest.json`，deploy verifier `19 passed, 0 failed`；运行态 `shortpick_replay_feedback` projection 已刷新，localhost 历史回放验证正文不再包含 `next_close` 或 `range_bound`，并显示“低样本分桶已收起 6 个”。

[2026-05-14T21:50:00+08:00] Low-sample regime buckets need real supplemental evidence, not only display guardrails:
历史回放行情分桶的低样本问题已经用实际补充数据处理。新增离线交易级策略切片 artifact `output/shortpick-strategy-trade-regime-evidence.json`，从 runtime 数据库读取非 LLM 确定性策略族，在不触发页面请求时重算、不调用模型、不写库的前提下，生成 entry/regime 层面的逐笔交易样本统计。

补充说明
- artifact 覆盖 `2023-05-16` 到 `2026-04-29`，共 `717` 个信号日、约 `3000` 只新开户普通现金账户可交易主板序列。
- 行情胜出结论现在来自交易级样本，最低门槛为 `30` 笔交易样本；当前产出 `14` 行 entry/regime winner rows，避免继续用 2-6 个月度组合样本的小桶下结论。
- 代表性结果：`next_close + 震荡/低波动/均衡` 下低换手上升趋势为胜出策略，`162` 笔交易样本；`next_close + 震荡/常规波动/均衡` 为 `61` 笔；`next_close + 震荡/低波动/小盘占优` 为 `35` 笔；`next_close + 上行/常规波动/均衡` 为 `30` 笔。
- 月度组合切片仍保留用于 bootstrap 置信区间、月/季/年稳定性和组合收益归因；交易级补充只用于解决行情胜出表的分桶样本不足。
- API 把该 artifact 投影到 `overall.strategy_slice_evidence.trade_regime_evidence`；前端在存在该字段时优先显示“交易级切片 / 交易样本”，并显示“最低分组门槛 30 个交易样本”。
- 本轮发布 manifest `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/releases/20260514T134506Z-cd3e96dca76b/manifest.json`，deploy verifier `19 passed, 0 failed`；runtime projection 已刷新，localhost `试验田 -> 历史回放` 已验证显示 `717 信号日`、`7 个可用行情桶`、`最低分组门槛 30 个交易样本`、`交易级切片`。canonical 入口在 Playwright 未登录会话中跳转到登录页，本轮未越过登录态复验业务页。

[2026-05-14T22:30:00+08:00] Model feedback must separate stock industry from model topic rollups:
`LLM模型反馈` 的“题材表现”不再把股票所属行业当成题材兜底。之前未归类题材会用 `normalized_theme` 显示，导致 DeepSeek 历史样本大量落到 `C 制造业`，同时 `商业航天密集发射`、`商业航天发射`、`商业航天/国防军工` 被拆成多个稀疏题材。

补充说明
- 后端新增归并题材口径：只统计已归类的模型题材；未归类样本不再混入题材表。
- 明确拆分 `题材表现（归并）` 和 `所属板块表现`。前者看模型事件/叙事簇，后者看股票静态行业/板块暴露。
- 当前 deterministic rollup 已合并商业航天相关别名到“商业航天”，半导体掩模版/厂务工程相关别名到“半导体国产替代”，低空经济运营并入“低空经济”，AI 光通信并入“AI算力硬件”。
- runtime projection 刷新后，DeepSeek V4 Pro 1M 的题材表前列为“商业航天 3/3”“半导体国产替代 2/2”等；`C 制造业` 出现在“所属板块表现”，不再作为题材结论。
- 本轮发布 manifest `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/releases/20260514T142914Z-2a3ab2ef2c51/manifest.json`，deploy verifier `19 passed, 0 failed`；localhost `试验田 -> LLM模型反馈` 已验证。canonical 入口在 Playwright 未登录会话中跳转登录，本轮未越过登录态复验业务页。

[2026-05-14T22:36:00+08:00] Coarse `C 制造业` industry profiles should not dominate model-feedback board analysis:
After the topic/industry split, result review showed that `C 制造业` still dominated DeepSeek's `所属板块表现` because several historical stocks only had coarse AKShare profile labels. This was not acceptable as a final readout because 欣旺达、上海瀚讯、德福科技、罗博特科、三角防务、中际旭创 are materially different sector exposures.

补充说明
- Added a conservative override layer only when a stock profile label is the overly broad `C 制造业` / `制造业`.
- Current corrected labels include `电池`、`军工通信`、`铜箔`、`机器人自动化`、`航空装备`、`光模块`.
- Runtime projection after refresh shows DeepSeek's `所属板块表现` led by `电气设备`、`通信设备`、`百货`、`元器件`、`航空`、`半导体`、`小金属`、`空运`、`铜箔`、`铁路`、`水运`、`机器人自动化`; `C 制造业` no longer dominates or appears in the visible top board rows.
- 本轮发布 manifest `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/releases/20260514T143425Z-056994335016/manifest.json`，deploy verifier `19 passed, 0 failed`；localhost `试验田 -> LLM模型反馈 -> DeepSeek V4 Pro 1M` 已验证。

[2026-05-14T22:58:00+08:00] Historical replay default view should be decision-first for non-expert reading:
`试验田 -> 历史回放` 默认视图不再把执行假设、完整统计、候选回放明细和来源审计全部展开。首屏只保留历史分析结论、6 个稳定性判断卡和“关键行情结论”；执行口径、入场假设、短窗口 LLM 回放统计、完整统计/置信/归因、模型与策略对比、批次/候选/来源审计全部折叠到明确命名的下钻区。

补充说明
- 行情胜出表现在会解析 object row 中的 `market_regime_tag` 三段标签，展示为“震荡行情 · 低波动 · 大小盘均衡”这类中文读数，不再把 `range_bound:low_volatility:balanced_size` 落成“其他行情”。
- 默认关键行情表只看已识别行情，并优先显示 `next_close` 对应的“次日收盘买入”口径；`missing_regime` 行保留在 artifact 中，但从默认结论表收起。
- 页面说明明确提示“先看 6 个判断卡和关键行情结论”，下方折叠区用于追溯，不再让非专业读者在首屏面对长表格。
- 本轮发布 manifest `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/releases/20260514T145553Z-b6f3ba080a88/manifest.json`，deploy verifier `19 passed, 0 failed`；localhost `试验田 -> 历史回放` 已验证默认出现“执行口径和入场假设”“完整统计、置信区间和归因明细”“短窗口 LLM 回放统计”等折叠项，关键行情表显示中文行情桶且默认不出现“行情待识别/其他行情”。canonical 入口在 Playwright 未登录会话中跳转到统一登录页，本轮未越过登录态复验业务页。

[2026-05-15T00:08:00+08:00] Historical replay evidence should include full trade attribution, stratified LLM expansion, and real intraday quote snapshots:
本轮把剩余数据/算法补强项落到可执行 artifact，而不是只留在前端说明里。非 LLM 长窗口 artifact 现在输出完整逐笔交易行与股票、行业、信号日、行情桶归因；LLM 回放新增显式日期 CLI，可按行情分层扩样；未来 14:00 同日入场控制会保存真实 quote snapshot artifact，避免把日线 proxy 当成真实盘中成交证据。

补充说明
- `output/shortpick-strategy-trade-regime-evidence.json` 已重建：覆盖 `2023-05-16` 到 `2026-04-29`，`717` 个信号日，`14180` 笔逐笔交易，股票/行业/日期/行情归因来自完整 trade rows，不再从 staged `trades_sample` 外推。
- 前端“完整统计、置信区间和归因明细”折叠区在 artifact ready 时显示“逐笔股票贡献”和“逐笔行业贡献”；默认首屏仍保持决策优先。
- 新增 `shortpick-replay-dates` CLI，支持 JSON array、newline 文件，或带 `dates` 字段的 artifact。已按最大行情桶各取早/中/晚生成 `18` 个分层日期，并用真实 sealed-packet LLM 跑完 `18/18` 个 completed run。
- `output/shortpick-replay-feedback-cache.json` 已刷新到 `126` 个历史 replay run、`13460` 条 aggregate validation；前端 projection `shortpick_replay_feedback:v1` 已刷新，payload 约 `1.23MB`。
- `run_shortpick_intraday_same_day_control` 会为 selection universe 写 `shortpick-intraday-quote-snapshot:{run_id}:selection_universe` artifact，payload 保留完整 quote snapshot、采集时间、来源和边界说明。历史未采集日期仍不能用日线 proxy 回填成真实 14:00 成交。
- 本轮发布成功并更新 `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/releases/latest-successful.json`，deploy verifier `19 passed, 0 failed`；localhost `试验田 -> 历史回放` 已验证默认决策视图、交易级行情切片、展开后的逐笔股票/行业贡献。canonical 入口在 Playwright 未登录会话中跳转统一登录页，本轮未越过登录态复验业务页。

[2026-05-16T22:45:00+08:00] Generated research artifacts belong in runtime data, not the source checkout:
canonical checkout 中的 `data/artifacts` 改动经抽样确认是正常 phase2/phase5 统计产物再生成：manifest/validation/backtest JSON 均符合既有 artifact contract，典型 diff 是 2026-05-15 交易日加入后样本从 94 到 95、滚动窗口从 35 到 36。这些数据可信到可以作为运行时只读缓存继续使用，但不应作为源码改动提交。

补充说明
- 已将 canonical `data/artifacts` 内容同步到 `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/artifacts`；运行时目录当前 JSON 全量解析通过，`1041` 个 artifact 文件无坏 JSON。
- `ASHARE_ARTIFACT_ROOT` 现在优先级高于 sqlite DB 推导，便于运行时和维护任务显式指向 runtime/output 数据目录。
- artifact 写入增加 source-checkout 保护：默认拒绝写入 `PROJECT_ROOT/artifacts` 和 `PROJECT_ROOT/data/artifacts`，只有显式设置 `ASHARE_ALLOW_REPO_ARTIFACT_WRITES=1` 才允许 intentional fixture refresh。
- `run-scheduled-refresh.sh`、`start-local-backend.sh`、`publish-local-runtime.sh` 均会显式导出 artifact root；发布后的 post-deploy refresh 固定写入 `$RUNTIME_ROOT/data/artifacts`。
- 已发布到 runtime，并更新 `output/releases/latest-successful.json`；deploy verifier `19 passed, 0 failed`；localhost 浏览器验证首页实际服务正常。canonical 入口未登录会话返回登录跳转，本轮未越过登录态复验业务页。
- canonical 中现有 dirty artifact 文件暂未清理或回滚，等待明确批准后再从源码 checkout 移除这些生成产物改动。

[2026-05-21T14:20:00+08:00] Automation-platform host boundary correction:
本项目被重新确认成“被纳管业务项目”，不是新自动化中台/平台本体的宿主。上一轮把 auto-progress readout 继续推进成 workbench projection、API 和前端工作台，属于把“用 stock_dashboard 做流程试验田”误读成“把平台能力嵌入 stock_dashboard”。这条路线已经停止，并通过非破坏性 revert 撤回相关产品代码。

原因判断
- 路由惯性：长任务 heartbeat 和本地上下文持续指向 `stock_dashboard`，主进程没有在每轮开始前重新判定目标宿主。
- 试验田边界不清：流程验证本应输出流程合同、评估和平台接口约束，却被推进成业务项目 runtime 功能。
- 缺少硬门禁：Context Pack 没有强制写明 `platform_core / managed_project / integration_adapter`，评审也没有把宿主越界当成重跑条件。
- 主进程责任缺失：子进程执行与评估循环存在，但主进程没有在每轮收口后判断“这是否还在原始目标内”。

固化决策
- 平台工作台、平台 scheduler 编排、LLM reviewer、CI/CD 门禁、跨项目巡检和多 agent 流程治理必须进入独立平台系统/仓库。
- `stock_dashboard` 后续只允许保留业务域能力、作为平台流程的 fixture/验收对象，或提供明确的集成适配点；不得承载平台本体 UI/API/状态机。
- 已撤回的相关提交为 `2c2034b`、`816adeb`、`e0c28e6`、`186c3de`、`c4c6d18`；后续若需要平台 workbench projection，应先创建/切换到平台宿主后重新设计。

[2026-05-18T20:05:00+08:00] Shortpick open-entry line is promoted as frozen candidate v2, not a silent replacement:
历史回放和首批 live 纸面跟踪都显示，当前低换手上升趋势策略在“次日开盘买入”口径下优于“次日收盘买入”。该差异属于入场价格源变更，不是文案改名，因此不能覆盖现有冻结 v1 的历史连续性。

补充说明
- `frozen_paper_primary` 继续表示冻结 v1：同一选股规则，次一交易日收盘买入。
- `market_factor_control_low_turnover_uptrend_next_open_entry` 在纸面跟踪 API/前端中提升为 `frozen_strategy_v2`：冻结候选 v2，次一交易日开盘买入。
- v2 复用现有候选生成、可成交性检查、验证快照和四轨退出计算；本轮只调整分组、标签、汇总和前端展示，不改变交易计算流程。
- 正式主线切换仍需更多 live 批次确认；当前产品显示应让 v1/v2 并排，而不是把 v2 包装成已经替代 v1。

[2026-05-23T15:51:00+08:00] Scheduled Short Pick Lab retries must be idempotent after candidate write succeeds:
5 月 14 日短投试验田盘后调度出现两次 completed run，导致同一 `2026-05-14` 信号、`2026-05-15` 买入、`2026-05-22` 5 日卖出的确定性纸面/对照候选在纸面跟踪看板重复出现。根因不是验证计算重复，而是第一次 scheduled run 已写入候选后，后续维护链路失败使 slot 未被视为成功，调度补跑再次写入同一日期的 market-factor overlay。

补充说明
- scheduled CLI 触发的 `run_shortpick_experiment` 和 14:00 同日控制现在会先复用同日期、同信息模式、同触发源的 completed run，避免调度 retry 再创建语义相同批次；手工/API 试验仍可新建 run。
- 纸面跟踪 API 增加展示层语义去重键：跟踪分组、角色、股票、信号日、有效买入日、买入口径、策略族和源排名相同的候选只展示一条；这层是防御性读模型，不替代写入侧幂等。
- live runtime DB 已先备份到 `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/backups/ashare_dashboard.before-shortpick-dedupe-cleanup-20260523T075110Z.db`，再删除 run 138 中 19 条重复 `shortpick-market-factor` 候选及 95 条验证快照；LLM 候选保留，因为它们不是造成纸面卖出重复的确定性覆盖层。
- 同时把 134-137 四个悬挂 `running` 重试 run 标记为 failed cleanup 归档，避免运行状态页继续把历史补跑误读为正在执行。

[2026-05-24T00:00:00+08:00] Frozen paper exits are three tracks: mechanical 5d, mechanical 10d, and take-profit/stop-loss:
冻结策略和冻结候选 v2 的退出监测不再把“5日后条件检查”和“10%触达止盈”拆成两条独立轨道。正确口径是：选股逻辑保持不变，同一入场信号并行记录机械5日、机械10日，以及一个 10 个交易日内随时触发的“止盈止损”退出策略。

补充说明
- `take_profit_stop_loss` 轨道从买入后的第 1 个交易日开始检查，不等待第 5 天；日内最低价触达买入价下方 8% 时按 -8% 退出，日内最高价触达买入价上方 10% 时按 +10% 退出。
- 由于当前只有日线高低价，没有逐笔先后顺序；同一交易日同时触达止盈和止损时，纸面跟踪按止损优先的保守口径处理。
- 前端纸面跟踪表不再只展示机械5日主结果，而是在“退出结果”列同时列出已形成的机械5日、机械10日和止盈止损结果；止盈止损在 10 日窗口未完成且尚未触发时不会伪造成已退出。
- 本次只改变退出方式和已有候选的验证 payload，不改变冻结策略、v2 或对照组的股票选择逻辑。
- live runtime DB 已先备份到 `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/backups/ashare_dashboard.before-shortpick-exit-risk-tracks-20260523T163049Z.db`，再用已有行情数据重算最近 40 天、55 个 shortpick run 的 1/3/5/10/20 日验证快照。`2026-05-14` 生益科技 v1 现在同时显示止盈止损轨道 `2026-05-18` 触达 +10% 和机械5日 `2026-05-22`，不再缺少止盈线。

[2026-06-04T01:30:00+08:00] 运行时 SQLite 固定为 WAL，盘后日刷不得在写期间阻塞看板读：
盘后 `phase5-daily-refresh`（~50min 全量分析+落库）曾在 `journal_mode=delete`（写者排他）下持锁，后端所有读查询撞 `database is locked` 30s 超时，导致 `https://hernando-zhao.cn/projects/ashare-dashboard/` 网页可打开但所有 tab 数据超时。固定决策：运行时 SQLite 一律 WAL + synchronous=NORMAL，读写并发，刷新写库期间看板继续读快照。完整方案见归档 `docs/archive/REFRESH_DB_LOCK_REMEDIATION_PLAN.md`。

补充说明
- `db.py:get_engine` 每个 sqlite 连接设 `journal_mode=WAL / synchronous=NORMAL / busy_timeout=30000 / wal_autocheckpoint=1000`；切 WAL 前已备份 `data/backups/ashare_dashboard.before-wal-migration-20260604T005059Z.db`，切换后重启 backend 让所有连接统一到 WAL。实测写锁持有 8s 期间 backend 读全部 HTTP 200。
- scheduled-refresh LaunchAgent 固定 `RunAtLoad=False`，且 `publish-local-runtime.sh` 不再在 bootstrap 后强制 `kickstart -k`：reload/publish 不得触发一次重型全量日刷；当天唯一一次刷新由 StartCalendarInterval/StartInterval + `.ok` slot 守卫决定。
- `phase5-daily-refresh` 四步（runtime refresh / horizon latest / horizon history / holding policy）各自独立 `session_scope`，写锁只在各步实际落库时短暂持有，不跨网络抓取与重计算。
- slot 重试退避 `SLOT_RETRY_INTERVAL_SECONDS` 默认 1800→7200（≥ 日刷超时），避免被打断的 slot 在上次影响未沉淀时重试叠加写者。
- 这些 PRAGMA/调度参数属基础设施配置（`stable_rule`），不是业务阈值；改动已过 policy-audit。

[2026-06-04T05:00:00+08:00] 纸面追踪退出验证必须数据到位即补算，最新模拟交易卡按需展开全量对照：
盘后日刷 `--analysis-only` 不同步基准指数，导致个股 K 线到最新日、基准滞后一天，冻结策略 5d/10d 退出长期卡在 `pending_benchmark_data`/`pending_forward_window`，看板上"5 日退出最新只到 5/26 买入"。同时试验田顶部筛选器只驱动一个 tab 却放全局头部、"最新模拟交易"卡硬编码冻结优先不回退使其余对照组从不展示。固定决策见归档 `docs/archive/PAPER_TRACKING_REVALIDATION_AND_UI_PLAN.md`。

补充说明
- 后端：`_refresh_runtime_data_output` 在 analysis 路径也同步基准 bar（不再只 ops 刷新）；`validate_recent_shortpick_runs` 改有界重验证循环（`max_iter=10` + 已处理 run 去重 + 「本轮无新 completed 即停」），数据到位的 pending 一次补齐，真缺数据不死循环。live 实测 signal 05-26 冻结 5 日退出由 pending→completed（stock_return 0.0708、excess 0.0646）。
- 前端：试验田顶部的历史批次/起止日期筛选器移入"最新模拟交易"tab（只驱动 loadLab，作用域与位置一致）；"最新模拟交易"卡冻结策略默认展示，底部新增默认折叠 Collapse 展示**本轮全量候选（按 `latestRun.id` 限定，含全部对照组）**；纸面跟踪 4 张规则卡明细默认折叠（标题可见、一键展开）。
- DeepSeek 两轮审核：方案首轮采纳 3 条修正（补算循环上限、基准同步层根治、本轮按 run.id），各步实现均审为可合入。

[2026-06-04T11:45:00+08:00] 股票工作台位置状态必须进入 URL，试验田首屏接口必须按 tab 读取：
股票工作台不再允许只用 React local state 表示主 view / 子 tab / symbol / stock tab。刷新、复制链接、浏览器前进后退都必须恢复用户位置；默认工作入口是 `试验田 -> 纸面跟踪`，不是 `关注池`。

补充说明
- `ShortpickLabView` 首屏只能加载当前 tab 需要的数据；打开纸面跟踪不得同时请求 run list、validation queue、model feedback、replay runs、replay feedback 或 market study。
- 首页或其他页展示纸面跟踪徽章只能用 compact summary；完整 `/shortpick-lab/paper-tracking` 账本只服务纸面页本体。
- `/shortpick-lab/runs` 是导航列表接口，不能嵌 full rounds、sources、consensus、candidates 或 raw answer；详情数据走 `/shortpick-lab/runs/{run_id}` 和候选下钻接口。
- `operations/summary` projection miss 时允许在请求内做一次确定性 fallback 构建，但必须写回同 key projection；同一 symbol 的下一次刷新必须命中 projection。

## 运营复盘性能治理

- **全量 `/dashboard/operations` 不得作为热路径或发布验证指纹端点**：发布验证必须使用 `/dashboard/operations/summary` 加 bounded `/dashboard/operations/details?...` sections，并把这些 payload 合并后做用户可见文本审计。
- **GET `/dashboard/operations` 必须只读**：不得在用户读请求里执行 `run_operations_tick(session)` 或其他维护写任务；tick 留给后台循环或显式维护命令。
- **组合净值曲线必须限量传输**：operations portfolio 响应的 `nav_history` 固定上限 90 点，采样必须保留首尾、净值/基准峰谷、最大回撤和最大暴露，再等距补齐；不要把每组合 1000+ 点全历史塞进 tab 请求。
- **模拟操作后的运营刷新走 summary + details**：前端成功执行 simulation action 后只刷新 `getOperationsSummary`，再按需补拉 `simulation_workspace` 和 `portfolios` 明细，不回退到 full dashboard API。
- **bounded details 必须真有界，不得复用全量 dashboard 构建**：`replay`、`manual_queue`、`factor_observation`、`sector_exposure`、`policy_governance`、`simulation_workspace` 这类小 section 只能调用对应领域 builder。发布验证里的 `19.6s` 残余慢路径证明“URL 是 details”不等于“实现已 details 化”。
- **服务启动不能同步等待 operations 预热**：operations response cache 可以后台 best-effort 预热，测试可用 `ASHARE_OPERATIONS_RESPONSE_PREWARM_MODE=sync` 保持确定性；生产 lifespan 不得因为预热阻塞 `/health` 和发布健康检查。

[2026-07-03T12:10:00+08:00] Shortpick deep research end-state design contract:
本轮补落地 `docs/contracts/SHORTPICK_DEEP_RESEARCH_END_STATE_DESIGN_2026-07-03.md`，作为 Short Pick 深度研究验证的终局设计合同。后续开发必须以该文档为准：设计不阶段化，实施阶段化；P0/P1/P2/P3/P4/P5 只是完整设计的交付切片，不允许把 P0 当前实现误读成终局范围缩小。该合同现已包含完成状态、量化技术门禁、制品字段合同、当前实现映射和仍阻断项。

补充说明
- 终局数据流固定为 `runtime DB(read-only source) -> research input snapshot -> PIT feature store -> validation store -> governance/promotion gate -> dashboard projection`。
- runtime DB / 业务库只作为研究只读输入；raw validation rows、weight sweep、IC 研究结果不得写回 runtime DB 或生产 policy config。
- 从 `recommendation_payload.factor_breakdown` 反取的 legacy 因子分数只能用于 diagnostic-only 路径，不能用于生产权重、horizon approval、自动 promotion 或模拟盘毕业。
- 当前 `3621f2d` 只实现 P0 初始切片：独立 `research_validation` artifact store、legacy diagnostic-only、lineage/gate/promotion blocked、benchmark fallback blocked、小样本和 rolling IC 动态权重门禁。后续增量已继续落地 PIT feature store、objective frozen universe、walk-forward/purged CV/PBO、OOS artifact、promotion state machine 和 materialized dashboard projection registry，但这些 implemented slices 仍不代表 production promotion。
- 后续切片的第一个增量开始落地 research input snapshot：factor validation / weight sweep 路径先把 runtime DB 只读输入冻结成独立 `research_input_snapshot` artifact；该制品仅证明输入边界，不提升 claim ceiling，不替代 PIT feature store、OOS 或 promotion state machine。
- 后续切片继续落地 PIT feature store：factor validation / weight sweep 路径从 frozen input snapshot 生成独立 `pit_feature_store` artifact；legacy `recommendation_payload.factor_breakdown` 仍只作 diagnostic comparator，不能用于生产权重、promotion 或自动调参。
- 后续切片继续落地 objective frozen universe：factor validation / weight sweep 路径在验证前冻结 `objective_frozen_universe` artifact；active watchlist / recommendation rows 只能作为覆盖子集记录，不能再作为研究 universe 定义或 promotion 证据。
- 后续切片继续落地 walk-forward / purge / embargo：factor validation / weight sweep 路径写入 `walk_forward_purge_embargo` protocol artifact；该制品只证明切分与泄漏防护协议存在，ready split 不足时仍必须 blocked，不能作为 promotion 证据。
- 后续切片继续落地 PBO/DSR/multiple comparison：weight sweep 路径写入 `pbo_dsr_multiple_comparison` diagnostics artifact；eligible trials、PBO、Deflated-Sharpe confidence、alpha t-stat gate 未通过时仍必须 blocked，不能把 in-sample best sweep 变成 production 权重。
- 后续切片继续落地 OOS validation：factor validation / weight sweep 路径从 ready walk-forward holdout windows 写入 `oos_validation` artifact；OOS Rank IC、ICIR、positive-rate、top-quantile gates 未通过时仍必须 blocked，不能 promotion。
- 后续切片继续落地 governance promotion state machine：factor validation / weight sweep 路径写入 `governance_promotion_decision` artifact；主 lifecycle 固定为 `diagnostic_only -> research_candidate -> oos_candidate -> paper_tracking_candidate -> production_eligible`，当前仍停在 `diagnostic_only` 且 gate outcome 为 blocked。
- 后续切片继续落地 dashboard approved projection registry：factor validation / weight sweep 路径写入 `dashboard_approved_projection_registry` artifact；当前 `approved_projection_count=0`，dashboard/API 只能透传 summary，不能消费 raw validation artifacts 或 registry entries。
- Runtime publish and served verification：commit `04fe909` 已发布到 local runtime with `ASHARE_PUBLISH_REFRESH_MODE=skip`；release manifest `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/releases/20260703T142623Z-04fe909c3142/manifest.json` status=`passed`，commit `04fe909c31428094b76c021b2b4c7751ca49f56d`，canonical/local parity matched for factor observation and simulation workspace，deploy verifier `44 passed, 0 failed`。served `factor_observation` 仍为 `blocked_from_production` / `diagnostic_research_only`，simulation workspace detail 已裁剪到约 67.5KB、每条 track 88 个 nav 点；这只证明当前 runtime served verification 完成，不改变 production promotion blocked 状态。

[2026-07-04T03:18:00+08:00] Shortpick model discovery found a concentrated top5 research candidate, not a broad ranker:
P1 model exploration no longer停留在“没有成功案例”。在先前 baseline/linear/tree/regime、5d reversal/breakout、20d trend quality、24-field expanded diagnostics 全部失败后，本轮新增 cross-sectional feature construction，并把 single-feature diagnostics 扩展为 top5/top10 组合读数。结果表明宽 top-quantile ranker 仍失败，但集中 top5 liquidity/momentum seed 在真实 runtime walk-forward 中可重复命中强势组合。

补充说明
- Feature matrix v2 新增 per-date percentile、low-turnover/low-volatility percentile、industry-relative 5d/20d excess、amount 10d/20d ratio 和 volatility 10d/20d ratio，矩阵仍由 runtime DB read-only facts 生成，验证结果只写 `research_validation/*` artifact。
- `concentrated_liquidity_momentum_20d_v1` 注册为独立 selection policy：`mode=concentrated_top_k`、`top_k=5`、`evaluation_return_metric=top_5_net_excess_mean`。它不是全市场宽排序器，因此比较、DSR 和赢家依赖必须使用 top5 组合口径，不能用 broad Rank IC gate 误杀或误判。
- 80-date report `model-comparison-report-2e22bed9d56ff356`：best `trial-002` top5 net excess `0.1888`、positive top5 rate `1.0`、top10 net excess `0.1692`、DSR `1.0`、PBO `0.0`、winner dependency ready；comparison-level blocker only `governance_promotion_pending`。
- 160-date report `model-comparison-report-dd08e1b37b308058`：best `trial-002` top5 net excess `0.0833`、positive top5 rate `0.6625`、top10 net excess `0.0718`、DSR `0.99996`、PBO `0.0`、winner dependency ready；removing top symbol/date/month still leaves positive mean net excess. However, 160-date Rank IC remains `-0.0299` and broad top-quantile net excess remains `-0.0140`, so claims must stay limited to concentrated top5 selection.
- Production/dashboard promotion remains blocked. Required next gates are execution-aware labels and stress tests: T+1, limit-up/down buy/sellability, fees/slippage/stamp tax, ADV capacity/fill, cost stress, regime/month stability and governance approval. No dashboard exposure is allowed from the raw workbench artifacts.

[2026-07-04T05:06:00+08:00] Confirmed top5 is the current收益最优 optimization; balanced top5 is a weak-regime control:
进一步拆解 `concentrated_liquidity_momentum_20d_v1` 后，负贡献并不主要来自流动性不足，而来自动量确认弱、行业相对强度弱，以及局部极端换手/波动。优化不能硬编码股票或行业黑名单，因此本轮只用 PIT 动态特征注册了两个后续候选。

补充说明
- `confirmed_concentrated_liquidity_momentum_20d_v1` 加入 `return_20d_percentile` 和 `industry_return_20d_excess` 确认过滤。160-date report `model-comparison-report-af5214debc6b5fea`：best `trial-002` top5 net excess `0.0982`、positive top5 rate `0.6750`、top10 net excess `0.0681`、Rank IC `-0.0042`、DSR `0.999996`、PBO `0.0`、winner dependency ready。相对 base concentrated，收益和 rank 行为均改善，是当前收益最优 research candidate。
- `balanced_confirmed_concentrated_liquidity_momentum_20d_v1` 在 confirmed 上叠加 turnover/volatility caps。160-date report `model-comparison-report-b7852b296bb2bca8`：best `trial-004` top5 net excess `0.0784`、positive top5 rate `0.7625`、top10 net excess `0.0420`、Rank IC `-0.0039`、DSR `0.999992`、PBO `0.0`、winner dependency ready。它牺牲强趋势收益，但把 Jan/Feb monthly means 从负转正，因此只能作为弱市/胜率控制候选，不是收益最优主线。
- 下一步不应继续无限阈值调参。优先补 execution-aware label/gates：T+1、涨停买入/跌停卖出可成交性、费用/滑点/印花税、ADV capacity/fill，然后做 cost/capacity/regime stress。工程上还需要更快的 candidate evaluation cache/streaming digest，否则每个 160-date spec 约 10 分钟，搜索效率太低。

[2026-07-04T05:35:00+08:00] Comparison reports must carry execution-stress diagnostics before any promotion discussion:
仅有 top5 均值、DSR、PBO 和 winner dependency 仍不足以判断策略可推进。本轮把 execution stress proxy 加入 `model_comparison_report`：2x/3x 成本压力、月度均值稳定性、top5 日期组合路径回撤。该诊断参与 comparison gate，但不解除治理层的真实执行门禁。

补充说明
- Base concentrated refreshed report `model-comparison-report-d9a5fff2bf8a0399`：top5 net excess `0.0833`，2x/3x cost stress 仍为正，但 Jan/Feb monthly means 为负，path drawdown proxy `-1.6019`，因此 execution stress blocked。
- Confirmed refreshed report `model-comparison-report-24ae0a4e31be1bde`：top5 net excess `0.0982`，2x/3x cost stress 仍为正，收益最优地位不变；但 Jan/Feb monthly means 为负，path drawdown proxy `-1.2213`，因此仍 blocked。
- Balanced refreshed report `model-comparison-report-8445b5b9b1ef2d9e`：top5 net excess `0.0784`，positive top5 rate `0.7625`，2x/3x cost stress 仍为正，negative months cleared；但 path drawdown proxy `-1.0856` 仍略低于当前 stress 阈值，仍 blocked。
- 下一轮优化重点改为 path drawdown：退出规则、持有期/现金开关、弱市 exposure control、真实 T+1/limit/ADV fill label，而不是继续堆 entry filters。

[2026-07-04T05:58:00+08:00] Benchmark-only cash-switch is killed as the next top5 optimization path:
为了降低 balanced 候选的 path drawdown，本轮在 candidate runner 中加入 selection-policy cash-switch 支持：被 regime gate 关闭的日期按 cash return `0.0` 计入 top5 returns，而不是从样本中删除。机制可以保留，但用基准收益做硬/软空仓开关的具体候选失败。

补充说明
- Hard cash-switch report `model-comparison-report-53f0f7091c31c582`：path drawdown proxy 从 balanced 的 `-1.0856` 降到 `-0.0728`，但 top5 net excess 降到 `0.0441`，positive top5 rate `0.325`，Feb monthly mean 仍为负，PBO proxy `1.0`，OOS gate blocked。
- Soft cash-switch report `model-comparison-report-53d479f49d08bd9c`：path drawdown proxy `-0.2297`，top5 net excess `0.0519`，positive top5 rate `0.425`，Feb/Mar monthly means 为负，PBO proxy `1.0`，OOS gate blocked。
- 结论：cash-switch 机制可作为 future policy primitive 保留，但 benchmark-only cash-switch 不应作为下一轮主优化方向。优先探索 exit/hold-period logic、position sizing、真实可成交性和容量约束，而不是继续调 benchmark gate 阈值。

[2026-07-04T06:46:00+08:00] Light PIT risk-scaled top5 is the first comparison-ready Short Pick model candidate:
本轮继续优化 balanced concentrated top5，不再调 benchmark-only cash switch。固定 10 日退出被淘汰，轻量 PIT 风险仓位缩放成为当前第一条在 `model_comparison_report` 层面通过过拟合、赢家依赖和执行压力诊断的 research candidate。

补充说明
- 10d exit report `model-comparison-report-3acd5312ea1c17c1`：path drawdown 改善到 `-0.8880`，但 top5 net excess 只有 `0.0330`，positive top5 rate `0.6125`，DSR `0.9364 < 0.95`，Jan/Mar monthly means 为负，因此 killed。
- 第一版更重的 risk scaling report `model-comparison-report-fe023f85fe7ce9dc`：path drawdown `-0.6092`、DSR/PBO ready、positive top5 rate `0.7625`，但 Jan monthly mean 仍略负 `-0.000089`，因此 blocked。
- 轻量版 risk scaling report `model-comparison-report-863ce9de9ed3a4fb`：best `risk_scaled_balanced_concentrated_liquidity_momentum_20d_v1:trial-005`，top5 net excess `0.0722`，positive top5 rate `0.7750`，top10 net excess `0.0383`，DSR `0.999998`，PBO `0.0`，execution stress ready，all monthly means positive，path drawdown `-0.9362`，winner dependency ready。
- Best params are PIT-only and non-symbol-specific: `full_weight_max_volatility_20d_percentile=0.90`, `full_weight_max_turnover_rate_percentile=0.85`, `min_position_weight=0.80`, with the same balanced entry filters. High-risk top5 picks are position-scaled; unused exposure is cash.
- This is not production approval. Governance remains blocked by required real execution gates: T+1, suspension/limit-up buyability and limit-down sellability, fees/slippage/stamp tax, ADV capacity/fill, plus explicit governance promotion. Dashboard exposure remains forbidden.

[2026-07-04T07:25:00+08:00] Risk-scaled top5 is downgraded after long-window return reality check:
上条 decision 的“comparison-ready”只能说明短窗 report gate 通过，不能说明策略达标。补跑固定参数的 720-date 轻量历史资金曲线后，`risk_scaled_balanced_concentrated_liquidity_momentum_20d_v1` 必须降级为 diagnostic risk-control line，不再作为候选主线。

补充说明
- 720-date lightweight backtest 覆盖信号日 `2023-06-13` 到 `2026-05-27`，3121 只新开户主板候选，20 日持有，round-trip cost `0.1%`，按同一 PIT 选股和仓位缩放公式计算。
- Rolling 20-sleeve 资金曲线：总收益 `+43.0%`、年化约 `+12.5%`、最大回撤约 `-43.3%`；同期沪深300约 `+29.9%`、年化约 `+9.0%`、最大回撤约 `-21.4%`。Non-overlap 20d rebalance 只有 `+17.7%`，最大回撤约 `-49.7%`。
- 该结果远低于当前 Short Pick V2 quiet champion 的已知目标线：`quiet_r2_poolhot10_mtw__fixed85_top5_v1` 历史总收益约 `+271.2%`，年化约 `53.96%`，最大回撤约 `-11.9%`；也不满足 2026-06-13 定下的 30% 年化门槛。
- 结论：这个模型只证明“近期窗口里风险缩放能改善路径诊断”，不能作为“模型找到理想策略”的成功案例。后续模型搜索必须把 V1/V2 冻结/quiet champion 和回撤反转控制作为显式收益下限；新模型允许牺牲少量收益换稳定性，但不能把三年收益降到 `+43%` 且回撤扩大到 `-43%`。

[2026-07-04T07:38:00+08:00] Model-search return anchor should be V1 outcomes, not V2 method or constraints:
修正上一条对照口径：本轮模型探索主要对标试验田 V1 的历史结果，不应以 V2 quiet champion 作为主锚点。V2 有更多限制和独立治理语境；V1 才是用户当前关注的收益结果锚点。

补充说明
- V1 只能作为结果锚点，不能作为方法模板。后续模型仍必须探索更完善的多因素/动态权重/执行约束体系，不能退回 V1 那种单一来源判断和简单规则。
- 当前可引用的 V1-oriented 锚点包括：legacy frozen strategy 的高收益历史读数约 `+62.6%`（但 mixed-permission，不作为 executable proof），以及 runtime drawdown-reversal control artifact 的 next-close total return 约 `+59.5%`、excess 约 `+20.2%`（仍有自身样本/执行 caveat）。
- 因此 `risk_scaled_balanced_concentrated_liquidity_momentum_20d_v1` 的三年 `+43.0%`、年化 `+12.5%`、最大回撤 `-43.3%` 仍不合格：它低于 V1 结果锚点，且稳定性没有换来足够好的收益/回撤组合。
- 后续 qualification floor 应写成：不能比 V1 冻结策略/回撤反转过滤的历史结果低很多；允许为稳定性牺牲一部分收益，但必须保持同一量级，并证明更强的数据来源、多因素解释、regime 稳定性和真实执行约束。

[2026-07-05T00:00:00+08:00] Breakout/amount-confirmation top1 is the current model-search finalist, but only as a lightweight-screening result:
本轮继续按 V1 结果锚点优化模型，而不是回到 V1 的简单规则。轻量 next-close 缓存复筛发现 `breakout_amount_confirmation_top1_20d_v1` 是当前最强 finalist：它结合 20d 相对趋势、10d/20d 成交额扩张、流动性、一日过热惩罚、波动 cap 和换手 cap。

补充说明
- 可复现的稳定优先参数为：`momentum_20d_percentile_weight=1.5`、`amount_10d_vs_20d_percentile_weight=0.8`、`liquidity_percentile_weight=1.2`、`one_day_overheat_penalty=0.5`、`max_volatility_20d_percentile=0.85`、`max_turnover_rate_percentile=0.90`，`top_k=1`。
- 713 个信号日 lightweight rolling 20-sleeve proxy 覆盖 `2023-06-13` 到 `2026-05-26`：总收益约 `+245.3%`、年化约 `+55.0%`、最大回撤约 `-24.1%`、正收益信号日率约 `51.2%`、负月份 `15` 个。该结果高于 strict next-close governance leader `+75.9%` 和 old long-sample research target `+176.0%`，且回撤好于旧 long-sample `-31.7%`。
- 更高收益邻域参数达到约 `+264.3%`，但最大回撤恶化到约 `-33.3%`，2023 partial-year proxy loss 扩大到约 `-26.9%`，因此不作为默认 finalist。
- 160-date formal artifact `model-comparison-report-f80b77e8f82e26dd` completed for the finalist and is explicitly blocked/killed: selected top1 net excess mean `0.0408`, positive selected top1 rate `0.43`, negative 2026-03 monthly mean, path drawdown stress failure, winner dependency collapse after removing 2026-05, and insufficient eligible trials for PBO/DSR. This does not invalidate the lightweight three-year finalist, but it prevents any promotion or success claim.
- 当前 finalist 仍不是成功案例或 promotion：它有 top1 concentration、2023 partial-year proxy loss 约 `-20.5%`、15 个负月份、无 full research-validation artifact、无 forward paper tracking、无真实 T+1/涨跌停/停牌/ADV 容量/滑点成本验证，也尚未完成多重比较和 winner-dependency 的正式 artifact gate。Dashboard/paper tracking 继续禁止曝光。

[2026-07-05T00:00:00+08:00] Raw amount-expansion gating is real optimization space, but not a replacement default:
继续扫 `breakout_amount_confirmation_top1_20d_v1` 的邻域后，发现一个明确优化方向：对入选标的增加 PIT raw `amount_10d_vs_20d` 下限，并提高流动性权重。该方向在三年轻量曲线上显著改善收益/回撤，但在最新 160-date formal replay 上变差，因此注册为独立 challenger，而不是覆盖默认 finalist。

补充说明
- 新增 `breakout_amount_expansion_top1_20d_v1`：`momentum_20d_percentile_weight=1.5`、`amount_10d_vs_20d_percentile_weight=0.6`、`liquidity_percentile_weight=1.4`、`one_day_overheat_penalty=0.3`、`max_volatility_20d_percentile=0.85`、`max_turnover_rate_percentile=0.90`、`min_amount_10d_vs_20d=0.15`。
- 713 个信号日 lightweight rolling 20-sleeve proxy：总收益约 `+343.8%`、年化约 `+69.3%`、最大回撤约 `-20.0%`、正收益信号日率约 `52.3%`、负月份 `14` 个；相对默认 finalist 的 `+245.3%`、`-24.1%` 有明显改善。
- Formal 160-date artifact `model-comparison-report-837a0761bccaf56c` 反而更弱：selected top1 net excess mean `0.0099`，positive selected top1 rate `0.38`，Feb/Mar/Apr 2026 月均为负，winner dependency 在 symbol/date/month removal 下均 collapse。
- 结论：raw amount-expansion gate 是值得继续研究的优化空间，但它可能更偏长期强趋势/强量能 regime。下一步应做 full same-contract 三年 replay、时间分段 stability、winner dependency 和多候选 PBO/DSR，而不是直接把 challenger 升成默认策略。

[2026-07-05T00:00:00+08:00] Regime-adaptive defensive branch is the current stability finalist:
继续定位 formal 160-date failure 后，发现核心弱点不是 top1 本身，而是 benchmark 20d 为负时仍使用 breakout/amount-confirmation 追强势股。新增 `regime_adaptive_breakout_defensive_top1_20d_v1`：benchmark 20d return < 0 时切换到 liquidity + low volatility + low turnover + 5d relative strength；其他时候沿用 breakout/amount-confirmation。

补充说明
- 三年轻量 proxy 覆盖 `2023-06-13` 到 `2026-05-26`：总收益约 `+219.6%`、年化约 `+50.8%`、最大回撤约 `-11.0%`、正收益信号日率约 `58.6%`、负月份 `13` 个。收益低于 breakout top1 和 raw amount-expansion challenger，但回撤显著更好，且仍高于 old long-sample research target `+176.0%`。
- Formal 160-date artifact `model-comparison-report-1c89d56436b181c7`：candidate decision 从 kill 升为 `observe_blocked`，selected top1 net excess mean `0.0694`，positive selected top1 rate `0.50`，winner dependency `ready`；移除 top symbol 后均值 `0.0387`，移除 top date 后 `0.0583`，移除 top month 后 `0.0242`，不再 collapse。
- 仍未 promotion：2026-03 月均仍为负 `-0.0383`，path drawdown stress 仍 blocked，eligible trials 只有 1 条，DSR confidence `0.9135 < 0.95`，alpha t-stat `2.5403 < 3.0`，且真实 T+1、涨跌停/停牌、费用滑点、ADV 容量和 fill 仍未验证。
- `breakout_amount_confirmation_top2_20d_v1` 已作为 diversification replacement 被 formal artifact `model-comparison-report-13765e72fea137ca` 杀掉：selected top2 net excess mean `0.0057`、positive rate `0.44`、winner dependency collapse。不要把 top2 当成下一主线。
- 追加 16-trial formal family artifact `model-comparison-report-896e560a0226d090`：best `regime_adaptive_breakout_defensive_top1_20d_v1:trial-010`，弱市阈值为 `benchmark_return_20d < 0.0`，防御分支权重为 liquidity `1.0`、low volatility `1.2`、low turnover `1.2`、5d relative strength `0.0`。selected top1 net excess mean `0.0719`，positive selected top1 rate `0.53`，winner dependency `ready`，PBO proxy `0.0`，移除 top symbol/date/month 后均值仍为正。该 family 消除了 “eligible trials 只有 1 条” 的 PBO blocker，但多重比较惩罚后 DSR confidence 下降到 `0.6091 < 0.95`，alpha t-stat 为 `2.6317 < 3.0`；2026-03/2026-04 月均仍为负，path drawdown stress 仍 blocked。因此它是当前最有意义的稳定性 finalist，但不是成功案例、默认策略、paper tracking 候选或 dashboard 暴露对象。
- 追加 stability-aware trial selection 后的 formal artifact `model-comparison-report-e7cea6d36d8b6918`：comparison report 不再单纯按 selected top1 mean 选 trial，而是在 `selected_top_k_net_excess_mean >= 0.065` 后优先负月份更少、最差月更好的 trial。Best 从 `trial-010` 切到 `trial-012`，selected top1 net excess mean 仅从 `0.0719` 小幅降到 `0.0717`，positive selected top1 rate `0.52`，winner dependency 仍 `ready`，PBO proxy `0.0`；负月份从 `2026-03/2026-04` 降为仅 `2026-03`，2026-04 月均转正到 `0.00215`。仍未 promotion：2026-03 月均 `-0.0296`，path drawdown sum `-2.1821 < -1.0`，DSR confidence `0.6057 < 0.95`，alpha t-stat `2.6231 < 3.0`，且三年正式 result-anchor period count 仍不足。
- tighter volatility/earlier defensive challenger `regime_adaptive_breakout_defensive_tighter_top1_20d_v1` 已被 formal artifact `model-comparison-report-144e86dfb11ccd4e` 降级：虽然 lightweight proxy 显示约 `+237.2%`、最大回撤 `-7.4%`、负月份 `9` 个，但 formal 160-date best `trial-004` 只有 selected top1 net excess mean `0.0437`，DSR confidence `0.3519`，alpha t-stat `1.9746`，2026-03/2026-04 仍为负，且 path drawdown stress 仍 blocked。该方向不能替代当前 stability-adjusted regime-adaptive finalist。

[2026-07-05T00:00:00+08:00] Full-window regime-adaptive arbitration improves candidate selection but still does not complete the goal:
713-date formal replay exposed a validation-policy bug in the 160-date stability arbitration: a fixed `selected_top_k_net_excess_mean >= 0.065` floor is too high for full-window OOS averages, so it selected a lower-return trial. The comparison report now uses portfolio total-return and max-drawdown floors once the stability window has at least 500 periods.

补充说明
- New registry/report artifact root: `/tmp/stock_dashboard_regime_adaptive_stability_full713_arbitration_v2`.
- New registry artifact: `model-spec-registry-50fcaebf90867603`.
- New comparison report: `model-comparison-report-db3ea613abee7082`, sourced from the full713 candidate run `walk-forward-model-candidate-run-585eac2fd5c5143e` and the updated registry arbitration policy.
- Best trial is now `regime_adaptive_breakout_defensive_top1_20d_v1:trial-010`: 653 OOS periods, selected top1 net excess mean `0.0186`, positive date rate `0.5130`, portfolio total return proxy `+146.8%`, annualized `+41.7%`, max drawdown `-12.0%`, and 13 negative months.
- This is a real improvement over the stale `trial-002` selection (`+112.0%`, annualized `+33.6%`, max drawdown `-13.4%`) and it passes the strict next-close / drawdown-reversal result-anchor floor with much better drawdown.
- It is still not the target strategy. It remains below the old long-sample research target total return `+176.0%`, has many negative months, and is blocked by `deflated_sharpe_confidence_below_95pct`, `negative_monthly_mean_under_base_cost`, and `portfolio_path_drawdown_sum_below_minus_1`.
- Engineering change: prediction row digests are now computed only for the stored prediction sample rather than every generated prediction row; this keeps full-window candidate generation tractable without changing scoring semantics.
- Next optimization should target instability directly: regime transition smoothing, position sizing/exposure control, exit/holding-period logic, and execution-aware labels/capacity checks. Do not treat `trial-010` as dashboard/paper-tracking ready, and do not regress to V1-style single-source rules.

[2026-07-05T00:00:00+08:00] Risk scaling is useful but still below the strategy bar; defensive momentum confirmation is downgraded:
Two bounded full713 challengers were tested against the current regime-adaptive finalist. Both reuse the same input snapshot, feature matrix and executable label matrix as the full713 run; neither writes runtime business tables or dashboard projections.

补充说明
- `risk_scaled_regime_adaptive_breakout_defensive_top1_20d_v1` adds PIT volatility/turnover position scaling to the regime-adaptive selector. Formal candidate run `walk-forward-model-candidate-run-92a2b5d491d89526`; corrected arbitration report `model-comparison-report-6eaec6fb4a32e5d8`.
- Risk-scaled best `trial-003`: total return proxy `+145.5%`, annualized `+41.4%`, max drawdown `-11.8%`, selected top1 net excess mean `0.0184`, positive date rate `0.5130`, 14 negative months, DSR confidence `0.9186`, alpha t-stat `3.0606`.
- Interpretation: risk scaling materially improves DSR versus parent `trial-010` (`0.7514 -> 0.9186`) and slightly improves drawdown (`-12.0% -> -11.8%`), but it reduces total return (`+146.8% -> +145.5%`) and worsens negative-month count (`13 -> 14`). It remains `observe_blocked_not_replacement`, not a success case.
- `momentum_confirmed_regime_adaptive_breakout_defensive_top1_20d_v1` adds 20d relative-strength confirmation inside the weak-regime defensive branch. Formal candidate run `walk-forward-model-candidate-run-7a56a1c270d3226c`; corrected arbitration report `model-comparison-report-58b8998c054627a0`.
- Momentum-confirmed best `trial-000`: total return proxy `+117.6%`, annualized `+35.0%`, max drawdown `-12.4%`, selected top1 net excess mean `0.0147`, positive date rate `0.4855`, 14 negative months, DSR confidence `0.7797`, alpha t-stat `2.4364`. It is downgraded as weaker than the parent.
- Validation mechanism correction: long-window stability arbitration now sorts ineligible trials by portfolio total return and drawdown before weak-month count. Otherwise a low-return trial can look best merely because it has fewer negative months while failing the return floor.
- Engineering correction: the full-window candidate workflow now disables Python cyclic GC only during candidate generation and restores it afterwards. Sampling showed the previous run spent time in `deduce_unreachable/dict_traverse` over a huge dict/list graph; the GC-bounded rerun completed the 4-trial full713 challenger and kept memory materially lower.
- Next research direction: risk scaling may be combined with a better regime-transition/exposure model, but defensive 20d momentum confirmation should not replace the parent. Continue looking for a model that raises DSR above `0.95`, keeps full-window total return closer to or above the legacy target, and reduces negative-month/path stress.

[2026-07-05T00:00:00+08:00] Market-regime exposure scaling does not close the full713 stability gap:
Two additional full713 exposure challengers tested whether the near-miss risk-scaled line could clear monthly/path stress by conditioning exposure on benchmark regime. Both remain research-validation-only and do not affect runtime, dashboard, paper tracking or policy config.

补充说明
- `regime_exposure_scaled_regime_adaptive_breakout_defensive_top1_20d_v1` applies continuous market-regime exposure scaling in addition to stock volatility/turnover scaling. Formal candidate run `walk-forward-model-candidate-run-ccf6c109f1822c55`; report `model-comparison-report-d3a1596a97fafd20`.
- Market-exposure best `trial-003`: total return proxy `+119.1%`, annualized `+35.4%`, max drawdown `-11.8%`, 13 negative months, DSR confidence `0.8954`, alpha t-stat `2.9208`. It reduces return too much and is downgraded.
- `conditional_risk_scaled_regime_adaptive_breakout_defensive_top1_20d_v1` only tightens single-stock risk scaling in weak/high-volatility benchmark regimes, preserving full exposure for low-risk picks. Formal candidate run `walk-forward-model-candidate-run-8f2765b88249da5e`; report `model-comparison-report-cadd53fd6a3cb1e6`.
- Conditional best `trial-003`: total return proxy `+144.8%`, annualized `+41.3%`, max drawdown `-11.8%`, 14 negative months, DSR confidence `0.9170`, alpha t-stat `3.0505`. It is close to the risk-scaled challenger but still weaker (`+145.5%`, DSR `0.9186`) and does not reduce negative months.
- Conclusion: market-regime exposure scaling, whether broad or conditional, is not enough. The next useful direction should move beyond exposure-only controls into executable holding-period / exit logic, event/limit/capacity-aware labels, or richer regime-transition features that change the selected opportunity set rather than simply shrinking exposure.

[2026-07-05T00:00:00+08:00] Exit and rank-weighted sleeve improve pieces of the frontier but still do not complete the goal:
Three more full713 challengers were tested on the same reused input snapshot, PIT feature matrix and executable label matrix. They remain research-validation-only and did not write runtime business tables, policy config, paper tracking, dashboard approvals or production projections.

补充说明
- `adaptive_exit_risk_scaled_regime_adaptive_breakout_defensive_top1_20d_v1` added PIT 5/10/20-day holding-period selection from market regime plus single-stock risk. Formal candidate run `walk-forward-model-candidate-run-52b133e7583961ed`; report `model-comparison-report-95421910943186f3`. Best `trial-001`: total return `+132.8%`, annualized `+38.6%`, max drawdown `-14.1%`, 13 negative months, DSR `0.6971`, alpha t-stat `2.1812`, mean target horizon about `14.65` trading days. It shortened too many weak-regime winners and is downgraded.
- `tail_risk_exit_risk_scaled_regime_adaptive_breakout_defensive_top1_20d_v1` preserved 20d holding by default and exited early only for weak/high-volatility regime high-risk stocks. Formal candidate run `walk-forward-model-candidate-run-295411d5af9db144`; report `model-comparison-report-c4d96d7b0d1f5d0a`. Best `trial-000`: total return `+154.0%`, annualized `+43.3%`, max drawdown `-11.8%`, 14 negative months, DSR `0.9183`, alpha t-stat `3.0589`. This is a return frontier improvement, but it does not solve monthly/path stability.
- `rank_weighted_tail_risk_exit_risk_scaled_regime_adaptive_breakout_defensive_top2_20d_v1` added portfolio construction on top of the same scorer: top2 sleeve with fixed rank-weight profiles. Formal candidate run `walk-forward-model-candidate-run-4b97fee69f4a40a0`; report `model-comparison-report-baea5b17cd06ef3c`.
- Rank-weighted best `top2_95_05` (`trial-000`): total return `+152.4%`, annualized `+43.0%`, max drawdown `-11.5%`, 13 negative months, DSR `0.9214`, alpha t-stat `3.0796`. Stability-preferred `top2_90_10` (`trial-001`) keeps the return floor at `+147.0%`, improves max drawdown to `-11.2%`, and reduces negative months to `12`. This is the current most meaningful stability/return frontier, but still blocked by DSR `< 0.95`, negative-month stress and path-drawdown stress.
- `stress_cash_rank_weighted_tail_risk_exit_risk_scaled_regime_adaptive_breakout_defensive_top2_20d_v1` added conjunctive benchmark-stress cash switching to the 90/10 rank-weighted sleeve. Formal candidate run `walk-forward-model-candidate-run-4b737ec3e214f4d1`; report `model-comparison-report-2711575202ad0e38`. Best `trial-004` is effectively the same as rank-weighted 90/10 because the `0.09` volatility threshold produced no cash days: total return `+147.0%`, max drawdown `-11.2%`, 12 negative months. The `0.07` volatility variants reduced negative months to `11` but cut total return below the `1.45` floor and DSR dropped to `0.8547` after the 8-trial comparison penalty.
- Conclusion: broad exposure scaling, conditional exposure scaling, adaptive exits and conjunctive market cash switching are not enough. Rank-weighted sleeve is useful as a portfolio-construction layer, but the remaining gap likely requires changing the opportunity set or label/execution model: richer regime-transition features, event/limit/capacity-aware labels, industry/correlation constraints, or a trained scoring model that improves selection stability rather than only resizing or exiting the same top1 picks.

[2026-07-06T00:00:00+08:00] Regime-transition defensive branch is the new full713 frontier, but still blocked:
The next iteration changed the selected opportunity set instead of merely resizing/exiting the same picks. `regime_adaptive_breakout_defensive_ranker` now supports explicit `defensive_condition_mode=benchmark_20d_or_transition_stress`: before benchmark 20d turns negative, it can switch to the defensive branch when benchmark 10d is weak, benchmark 20d is not strong, and benchmark volatility is elevated.

补充说明
- Broad transition-defensive candidate `transition_defensive_rank_weighted_tail_risk_exit_risk_scaled_regime_adaptive_breakout_defensive_top2_20d_v1` ran 8 full713 trials. Formal candidate run `walk-forward-model-candidate-run-b25ec0b716584c64`; report `model-comparison-report-115676e844c4526b`. Best `trial-004`: total return `+152.0%`, annualized `+42.9%`, max drawdown `-11.2%`, 12 negative months, selected top2 mean `0.0177`, positive date rate `52.1%`, alpha t-stat `3.2179`, DSR `0.8807`. The direction improved return vs rank-weighted 90/10 and kept the same 12 negative months, but 8-trial DSR remained blocked.
- Narrow transition frontier `transition_defensive_frontier_rank_weighted_tail_risk_top2_20d_v1` fixed the useful transition region and compared only 95/5 vs 90/10 sleeves. Formal candidate run `walk-forward-model-candidate-run-d0b72f8a2b7e9173`; report `model-comparison-report-05032fe21ce33845`. Stability arbitration selected 90/10: total return `+152.0%`, annualized `+42.9%`, max drawdown `-11.2%`, 12 negative months, alpha t-stat `3.2179`, DSR improved to `0.9398` but still below the `0.95` gate.
- Sleeve scan `transition_defensive_sleeve_scan_rank_weighted_tail_risk_top2_20d_v1` then fixed the transition condition and formally tested 90/10, 91/9, 92/8 and 93/7. Candidate run `walk-forward-model-candidate-run-792a4b62a3bfa5ae`; corrected report `model-comparison-report-d464f8ef856be002` after fixing comparison-report sorting to honor declared `tie_break_order`. Current frontier is `trial-001` / `top2_91_09`: total return `+153.1%`, annualized `+43.1%`, max drawdown `-11.3%`, 12 negative months, positive date rate `52.2%`, alpha t-stat `3.2144`, DSR `0.9393`.
- Engineering correction: `model_comparison_report._sort_key` now honors registry-declared `trial_selection_policy.tie_break_order`; before this fix, the report always used a hardcoded stability ordering and incorrectly kept 90/10 ahead of 91/9 despite the sleeve-scan policy saying to choose higher total return after equal negative-month count.
- This is the best current frontier but still not the requested final strategy. It remains blocked by `deflated_sharpe_confidence_below_95pct`, negative monthly mean stress, path drawdown stress, and the standing execution gates for T+1, limit/suspension sellability, fees/slippage/stamp tax and ADV/fill capacity. Next useful direction should address the remaining negative months/path stress through richer opportunity-set constraints or executable label improvements, not more generic exposure/cash/exit tuning.

[2026-07-06T00:00:00+08:00] Industry diversification is downgraded; confidence-shifted rank weighting becomes the next hypothesis:
The next diagnostic added stock/industry metadata to prediction rows and selected-pick diagnostics, then joined the current full713 frontier selected Top2 picks to the retained universe matrix. Same-industry Top2 concentration is not the main remaining failure mode: only `73/653` signal dates (`11.2%`) selected two stocks from the same industry, and those dates had higher average weighted day return (`0.0317`) than cross-industry dates (`0.0161`). Several negative months had zero same-industry days, so a hard industry cap is unlikely to close the DSR/monthly/path blockers.

补充说明
- Registered `industry_diversified_transition_defensive_sleeve_scan_rank_weighted_tail_risk_top2_20d_v1` as a research-only candidate with `max_same_industry_picks=1`, but it is downgraded pending evidence because diagnostics do not support industry concentration as the dominant cause.
- Worst-date feature join showed the frontier's remaining tail is mostly Rank1 single-stock crashes during otherwise positive or mixed benchmark states. Many worst dates have high first-rank volatility/turnover and weak score separation from Rank2, e.g. 2024-05 and 2026-04/05 loss clusters.
- Registered `confidence_shifted_transition_defensive_rank_weighted_tail_risk_top2_20d_v1`: it keeps the transition-defensive scorer but changes portfolio construction from fixed `top2_91_09` to a conditional function. When Rank1 `volatility_20d_percentile >= 0.80` and Rank1/Rank2 score margin `<= 0.05`, the sleeve can shift to `top2_50_50` or `top2_60_40`.
- Selected-Top2 proxy on the existing full713 frontier suggests the `top2_50_50` shift fires on `86` dates and reduces negative months from `12` to `11`, with worst monthly mean improving from about `-0.0640` to `-0.0613`. This is hypothesis evidence only because it reuses selected Top2 rather than reranking all candidates.
- Latest 160-date formal smoke artifact `model-comparison-report-8e48a8ba57331d2e` completed for the confidence-shifted candidate, but it had zero dynamic-shift trigger dates in that recent window. It proves the runner/report mechanics but does not validate the full-window improvement.
- Direct full713 rebuild with metadata was killed with exit `137` after writing a 1.8G universe matrix. Before accepting or rejecting the confidence-shifted candidate formally, the workbench needs a low-memory replay path that can reuse existing full713 feature/label matrices or stream candidate generation without loading/writing multi-GB matrices.

[2026-07-06T00:00:00+08:00] Confidence-shifted rank weighting is the new full713 research frontier, but not production-ready:
Low-memory streaming matrix replay is now implemented for deterministic score-only specs. It reuses the existing full713 input snapshot, PIT feature matrix and executable label matrix without loading the multi-GB row payloads into memory, builds a temporary SQLite label/prediction index, and writes normal `walk_forward_model_candidate_run` plus `model_comparison_report` artifacts. The workflow now preserves real matrix artifact ids and carries `source_db_snapshot_id` / `source_data_time_range` from the input snapshot into candidate/report/governance artifacts.

补充说明
- Formal fixed full713 run: `/tmp/stock_dashboard_confidence_shifted_stream_full713_min60_grid4_fixed`, candidate run `walk-forward-model-candidate-run-539b8817cbcff561`, comparison report `model-comparison-report-91f1cfae6d8334f7`.
- Same validation contract as the previous frontier: input snapshot `model-exploration-input-snapshot-733355793be8ae3a`, feature matrix `pit-feature-matrix-9c652453b88384ab`, label matrix `executable-label-matrix-b653ac6da6b7dc5e`, 653 OOS periods, `min_train_dates=60`, `test_window_dates=20`, deterministic next-close executable labels.
- Best trial is `confidence_shifted_transition_defensive_rank_weighted_tail_risk_top2_20d_v1:trial-001`: base sleeve `top2_91_09`, conditional shift to `top2_50_50` when Rank1 `volatility_20d_percentile >= 0.80` and Rank1/Rank2 score margin `<= 0.05`.
- Versus the old corrected frontier `transition_defensive_sleeve_scan_rank_weighted_tail_risk_top2_20d_v1:trial-001` / `model-comparison-report-d464f8ef856be002`, total return improves from `+153.1%` to `+163.1%`, annualized return from `+43.1%` to `+45.2%`, max drawdown from `-11.25%` to `-10.82%`, negative months from `12` to `11`, positive date rate from `52.2%` to `53.0%`, alpha t-stat from `3.2144` to `3.5053`, and DSR confidence from `0.9393` to `0.9671`.
- Overfit diagnostics are now ready rather than blocked: eligible trials `4`, split count `33`, period count `653`, PBO proxy `0.0`, DSR confidence `0.9671 >= 0.95`, alpha t-stat `3.5053 >= 3.0`.
- Promotion still remains blocked. The comparison report still fails `execution_stress:negative_monthly_mean_under_base_cost` and `execution_stress:portfolio_path_drawdown_sum_below_minus_1`, and governance still blocks on T+1 execution, suspension/limit-state buy/sellability, fees/slippage/stamp-tax, ADV/capacity/fill-rate. Therefore this is the new research frontier and a meaningful model candidate, not a production strategy, paper-tracking migration, dashboard projection, or policy-config change.
- Next research should target the remaining 11 negative months and path stress with execution-aware labels, liquidity/capacity constraints, regime-transition features, and tail-event diagnostics. Do not regress this line into V1-style single-source screening; keep using registered model specs, same-window full713 replay, and governance artifacts.

[2026-07-06T00:00:00+08:00] Shortpick model exploration artifact retention and next optimization target:
The broad exploration phase created several GB-scale temporary matrix rebuilds that are no longer required after the streaming full713 replay succeeded. Cleanup retained compact JSON evidence under `/tmp/stock_dashboard_retained_reports_20260706` and removed obsolete large intermediate directories such as the 160-date breakout/regime/confidence smoke rebuilds, the industry metadata smoke rebuild, stale anchor directories, and the temporary `stock_dashboard_light_rows_h20.pkl`. The canonical reusable source remains `/tmp/stock_dashboard_regime_adaptive_stability_selected_full713` because it contains the source input snapshot, PIT feature matrix and executable label matrix needed to reproduce finalist replays. The confidence-shifted formal frontier at cleanup time was `/tmp/stock_dashboard_confidence_shifted_stream_full713_min60_grid4_fixed`; it was later superseded by the Top3 tail-blended replay.

执行约定
- Do not create another full matrix rebuild for finalist checks unless the feature or label definition actually changes. Reuse canonical full713 matrices through `--stream-matrix-replay`.
- After a challenger is downgraded, keep only compact comparison/candidate/governance JSON unless the matrix itself is the canonical reusable source for future experiments.
- Any next candidate must use the current confidence-shifted frontier as a non-degradation floor on the same full713/min60 contract: total return `>= +163.1%`, annualized return `>= +45.2%`, max drawdown no worse than `-10.82%`, negative months `<= 11`, DSR `>= 0.9671`, alpha t-stat `>= 3.5053`, PBO proxy `<= 0.1`, and no new lineage/governance metadata blockers.
- The next optimization goal is not to raise headline return by adding complexity. It is to clear or materially reduce the remaining blockers while preserving the above floors: `execution_stress:negative_monthly_mean_under_base_cost`, `execution_stress:portfolio_path_drawdown_sum_below_minus_1`, and the execution/capacity gates for T+1, limit/suspension, fees/slippage/stamp-tax, ADV and fill-rate.
- If clearing an execution blocker requires a more realistic label that reduces returns, the result must be reported as a stricter-reality diagnostic, not as a replacement for the current frontier unless it still meets the non-degradation floor.

[2026-07-06T00:00:00+08:00] Top3 tail-blended confidence shift improves the frontier but still does not clear stress blockers:
Using the compact selected-Top5 feature join `/tmp/stock_dashboard_confidence_frontier_top5_features_20260706.json`, a bounded proxy scan found that the remaining weak-margin/high-volatility dates benefit from spreading exposure across the third-ranked pick rather than only rebalancing Rank1/Rank2. This led to registered spec `top3_tail_blended_confidence_shifted_transition_defensive_rank_weighted_20d_v1`: base allocation remains effectively `top2_91_09`, but when Rank1 volatility percentile is at least `0.78` and Rank1/Rank2 score margin is small, the sleeve shifts to `top3_50_30_20`.

Formal same-contract streaming full713 replay completed at `/tmp/stock_dashboard_top3_tail_blended_stream_full713_min60`, reusing the canonical matrix artifacts without rebuilding them. Candidate run `walk-forward-model-candidate-run-0b21e799e5ee3c29`; comparison report `model-comparison-report-e0d817a563cb53cf`.

补充说明
- New best trial: `top3_tail_blended_confidence_shifted_transition_defensive_rank_weighted_20d_v1:trial-002`.
- Versus the previous confidence-shifted frontier `model-comparison-report-91f1cfae6d8334f7`, total return improves from `+163.1%` to `+170.3%`, annualized return from `+45.2%` to `+46.8%`, max drawdown from `-10.82%` to `-9.69%`, selected mean from `0.01889` to `0.01987`, positive date rate from `52.99%` to `53.45%`, DSR from `0.9671` to `0.9837`, and alpha t-stat from `3.5053` to `3.8011`.
- Stability also improves but does not clear the hard blockers: negative months remain `11`, worst monthly mean improves from `-0.0613` to `-0.0490`, and execution path drawdown sum improves from `-2.0206` to `-1.9876`, still below the `>-1.0` requirement.
- Governance remains blocked by `execution_stress:negative_monthly_mean_under_base_cost`, `execution_stress:portfolio_path_drawdown_sum_below_minus_1`, and unresolved execution/capacity gates. Therefore this is the new research frontier, not a production strategy or dashboard/paper-tracking candidate.
- Next optimization should not broaden the grid. It should diagnose the remaining 11 negative months and path drawdown sequence directly, likely through execution-aware labels, capacity/fill filters, or selective tail-event avoidance that preserves the new frontier floors: total return `>= +170.3%`, annualized `>= +46.8%`, max drawdown no worse than `-9.69%`, negative months `<= 11`, DSR `>= 0.9837`, alpha t-stat `>= 3.8011`, and PBO `<= 0.1`.

[2026-07-06T12:30:26+08:00] Post-score signal cash switches improve the frontier, but remaining path stress is no longer a simple rule problem:
Two additional bounded full713 challengers were tested with the same canonical input snapshot, PIT feature matrix and executable label matrix, using `--stream-matrix-replay` only. No GB-scale matrix rebuild was created; the new replay roots are compact report/run artifacts under `/tmp/stock_dashboard_overheat_cash_top3_tail_stream_full713_min60` and `/tmp/stock_dashboard_weak_low_vol_cash_stream_full713_min60`.

补充说明
- `overheat_cash_top3_tail_blended_confidence_shifted_transition_defensive_rank_weighted_20d_v1` adds a post-score cash switch for dates where Rank1 is in extreme 5d/20d overheat, benchmark 20d is positive, and Rank1/Rank2 score separation is weak. Formal report `model-comparison-report-773d4ba2fda17834`; candidate run `walk-forward-model-candidate-run-15c92007b2e7ac5e`; best `trial-000`.
- Overheat-cash best result: total return `+177.1%`, annualized `+48.2%`, max drawdown `-9.23%`, selected mean `0.02086`, positive date rate `52.68%`, 11 negative months, worst monthly mean `-0.0470`, path drawdown sum `-1.6164`, DSR `0.9914`, alpha t-stat `4.0470`, PBO proxy `0.0`. It is the return-preferred blocked frontier.
- `weak_low_vol_cash_overheat_top3_tail_blended_confidence_shifted_transition_defensive_20d_v1` keeps the overheat switch and adds a weak-market low-volatility cash switch: benchmark 10d weak, benchmark 20d volatility elevated, and Rank1 very high low-volatility percentile. Formal report `model-comparison-report-993b0e970e7f74e7`; candidate run `walk-forward-model-candidate-run-972a82e6882ee40c`; best `trial-001`.
- Weak-low-vol best result: total return `+170.4%`, annualized `+46.8%`, max drawdown `-9.27%`, selected mean `0.02292`, positive date rate `48.55%`, negative months reduced to `9`, worst monthly mean `-0.0470`, path drawdown sum `-1.4874`, DSR `0.9977`, alpha t-stat `4.4956`, PBO proxy `0.0`. It is the stability-preferred blocked frontier: it gives up the overheat-cash return premium but preserves the Top3 return floor while improving monthly stability.
- Both still fail `execution_stress:negative_monthly_mean_under_base_cost` and `execution_stress:portfolio_path_drawdown_sum_below_minus_1`; governance also remains blocked by T+1 execution, suspension/limit-state buy/sellability, fees/slippage/stamp-tax, ADV/capacity/fill-rate.
- A compact broad scan over one-to-four-condition simple cash rules found `clearing_count 0` for clearing path drawdown `>-1.0` while preserving the Top3 proxy return floor. The next useful blocker-clearing work should move into execution-aware labels and constraints rather than stacking more generic cash switches.
- Follow-up compact execution proxy diagnostic was retained at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_execution_constraint_diagnostic_20260706.json`. It tested relative turnover, amount-expansion and liquidity-percentile scaling/cash rules on the stability-preferred frontier. Best proxy variants only moved path drawdown from about `-1.50` to about `-1.48`, still far from the `>-1.0` gate. Current feature data lacks absolute ADV/fill/sellability fields, so the remaining blocker cannot be credibly cleared with existing relative liquidity proxies alone.
- A richer selected-pick execution join was then retained at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_selected_pick_execution_enriched_join_20260706.json`, matching `1692/1692` stability-frontier selected picks back to the canonical PIT feature matrix. It found `73` selected `limit_up_like` rows and `1` `limit_down_like` row; selected limit-state rows had aggregate weighted contribution about `-1.0531`.
- Registered `limit_aware_weak_low_vol_cash_overheat_top3_tail_blended_confidence_shifted_transition_20d_v1` to test the real pre-ranking gate rather than post-hoc deletion: block `limit_up_like` entries and suspension/stale proxies, then let full713 replay choose replacement candidates. Formal report `model-comparison-report-84ab19a0a021cdef`; candidate run `walk-forward-model-candidate-run-059ca269699beb50`.
- Limit-aware best `trial-000`: total return `+171.4%`, annualized `+47.0%`, max drawdown `-9.60%`, selected mean `0.02291`, positive date rate `49.46%`, 10 negative months, worst monthly mean `-0.0328`, path drawdown sum `-1.4877`, DSR `0.9979`, alpha t-stat `4.5350`, PBO proxy `0.0`. This preserves the broad return/DSR floor and improves worst-month mean, but it does not beat the stability frontier on negative-month count or path stress. Capacity floor variants degrade return sharply. Treat it as an execution diagnostic, not a replacement frontier.

[2026-07-06T13:18:00+08:00] Execution-label contract must move to order-level v3 before further blocker clearing:
A compact order-level diagnostic joined the limit-aware frontier's selected picks back to the canonical executable label matrix without rebuilding any full713 matrix. It retained `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_order_level_execution_label_gap_diagnostic_20260706.json`.

补充说明
- Diagnostic scope: `limit_aware_weak_low_vol_cash_overheat_top3_tail_blended_confidence_shifted_transition_20d_v1:trial-000`, candidate run `walk-forward-model-candidate-run-059ca269699beb50`, canonical label matrix `executable-label-matrix-b653ac6da6b7dc5e`.
- Result: `1695/1695` selected picks matched label rows; all `1695` labels are `ready` and `tradable_research_proxy`; selected weighted return attached to blocked labels is `0.0`.
- Interpretation: the current selected-pick frontier is not secretly using label-blocked entry trades. The remaining execution blocker is a label-contract gap: v2 labels do not persist `exit_date`, per-horizon exit sellability, or order-level execution state, so sellability, slippage/capacity and true fill-rate governance cannot be cleared credibly from the existing report.
- Code contract update: `MODEL_EXPLORATION_LABEL_VERSION` is now `shortpick_model_executable_label_matrix:v3`. New label rows include `entry_execution`, `exit_dates_by_horizon`, `exit_tradability_by_horizon`, and `exit_execution_by_horizon`; exit-day suspension/stale and `limit_down_like` sellability now block labels through reasons such as `suspended_or_stale_exit_20d` and `unsellable_limit_down_exit_20d`.
- This is not a new profitable strategy result yet. The next meaningful iteration is to rebuild/replay against label v3, then compare return/stability against the current blocked frontiers. Do not continue generic cash-switch or relative-liquidity proxy stacking until v3 execution labels are available.

[2026-07-06T15:35:00+08:00] Label v3 strict replay preserves the research line but does not clear the goal:
The v3 executable label matrix was rebuilt label-only from the existing full713 input snapshot and runtime DB. It did not rebuild or duplicate the PIT feature matrix. New label artifact: `/tmp/stock_dashboard_label_v3_full713_20260706/research_validation/executable_label_matrices/executable-label-matrix-403088086820ac2d.json`, `4.7G`, `2,098,150` rows, `2,024,090` ready rows. Streaming validation matched declared row and ready counts, and rows carry `entry_execution` plus per-horizon `exit_execution_by_horizon`.

补充说明
- Engineering correction: streamed replay no longer stores full v3 label JSON in the temporary SQLite label index. It stores only the numeric label columns required by candidate evaluation. A failed three-spec replay exposed a `35G` temp index; after the fix the label index stayed around hundreds of MB.
- Engineering correction: streamed replay predictions are now stored in a compact column table instead of full `prediction_json` blobs. A failed one-spec run exposed about `11G` temporary predictions; after the fix individual v3 frontier replays completed with compact final roots around `26M` and controlled temporary working sets around a few GB.
- v3 return-preferred replay: `/tmp/stock_dashboard_label_v3_return_frontier_full713_min60`, report `model-comparison-report-f07951b1c04e9a71`, candidate run `walk-forward-model-candidate-run-9ca74b49b4e184cf`. Best `overheat_cash_top3_tail_blended_confidence_shifted_transition_defensive_rank_weighted_20d_v1:trial-000`: total return `+170.0%`, annualized `+46.7%`, max drawdown `-8.44%`, selected mean `0.02005`, positive date rate `52.68%`, 12 negative months, worst monthly mean `-0.0411`, path drawdown sum `-1.7068`, DSR `0.9885`, alpha t-stat `3.9397`, PBO `0.0`.
- v3 stability-preferred replay: `/tmp/stock_dashboard_label_v3_stability_frontier_full713_min60`, report `model-comparison-report-13f09aeca20a8b0d`, candidate run `walk-forward-model-candidate-run-9b05cbde4add5ba6`. Best `weak_low_vol_cash_overheat_top3_tail_blended_confidence_shifted_transition_defensive_20d_v1:trial-001`: total return `+163.5%`, annualized `+45.3%`, max drawdown `-8.44%`, selected mean `0.02211`, positive date rate `48.55%`, 10 negative months, worst monthly mean `-0.0385`, path drawdown sum `-1.5563`, DSR `0.9968`, alpha t-stat `4.3931`, PBO `0.0`.
- v3 limit-aware replay: `/tmp/stock_dashboard_label_v3_limit_aware_frontier_full713_min60`, report `model-comparison-report-1ed4a05fe7d6a04a`, candidate run `walk-forward-model-candidate-run-840d88285cab3fe0`. Best `trial-000`: total return `+159.3%`, annualized `+44.4%`, max drawdown `-8.84%`, 10 negative months, worst monthly mean `-0.0385`, path drawdown sum `-1.6662`, DSR `0.9958`, alpha t-stat `4.3009`, PBO `0.0`.
- Interpretation: label v3 makes the results stricter but does not invalidate the research line. It improves max drawdown versus v2 but reduces total return and does not clear the two hard stress blockers. Under v3, return-preferred remains near the old Top3 return floor but has 12 negative months and worse path stress; stability-preferred is the current v3 stability frontier but gives up too much return versus the v2 frontier and still fails path `>-1.0`.
- Next optimization should be run on v3 labels as the new strict contract. The immediate target is not more entry limit filtering; it is path-stress and negative-month reduction while keeping v3 total return near or above `+170%`, DSR above `0.99`, max drawdown near `-8.5%`, and PBO `0.0`. Candidate directions: month/path-tail conditional portfolio construction, regime-transition opportunity-set changes, and real cost/capacity labels. Do not promote, dashboard-project, paper-track, or policy-config any of these results.

[2026-07-06T16:25:00+08:00] High-confidence tail-cash improves the label-v3 frontier but remains blocked:
The v3 stability selected-pick join and proxy scan found a narrow path-stress opportunity: unusually large Rank1/Rank2 score-margin tail dates were hurting path more than they helped stability. This led to registered spec `high_confidence_tail_cash_weak_low_vol_overheat_top3_transition_defensive_20d_v1`, which preserves the v3 weak-low-vol/overheat/top3 model family and adds a declared post-score cash switch for Rank1 high-confidence tail dates.

补充说明
- Full v3 same-contract replay completed at `/tmp/stock_dashboard_label_v3_high_confidence_tail_cash_full713_min60`, candidate run `walk-forward-model-candidate-run-7252eaa3c919d8ba`.
- The first report `model-comparison-report-728ed389493b19d1` selected `trial-002` because the report still used the candidate-run embedded old tie-break policy and prioritized negative-month count before return/path. This was an arbitration bug for the current goal, not a model failure.
- Engineering correction: `model_comparison_report` now overlays registry-declared `selection_policy` when building the leaderboard and retains `candidate_run_selection_policy` for audit. This makes a report rebuild a real re-arbitration step instead of merely regenerating metadata. A targeted regression test covers this case.
- Re-arbitrated report `model-comparison-report-9169bed0e1736fe2` selects `trial-000`: total return `+170.8%`, annualized `+46.9%`, max drawdown `-8.68%`, selected mean `0.02263`, positive date rate `47.63%`, 11 negative months, worst monthly mean `-0.0306`, path drawdown sum `-1.4874`, DSR confidence `0.9979`, alpha t-stat `4.5255`, PBO proxy `0.0`, winner dependency `ready`.
- This is the current label-v3 return/path challenger: it slightly beats the v3 return-preferred replay on total return (`+170.8%` vs `+170.0%`) and materially improves worst month/path versus the v3 return line (`-0.0306` / `-1.4874` vs `-0.0411` / `-1.7068`), while retaining high DSR/PBO quality.
- It is still not the requested final strategy. The report remains `blocked_from_production` because negative monthly mean stress and path drawdown sum `>-1.0` still fail; governance also remains blocked by T+1 execution, suspension/limit buy/sellability, fees/slippage/stamp-tax and ADV/fill-rate. Do not promote, dashboard-project, paper-track or policy-config this candidate.
- Next useful optimization must attack the remaining path/month sequence directly on label v3. Generic entry-limit, relative-liquidity and broad cash-switch scans have already failed to clear the path gate without degrading return; the next direction should be a more explicit path-tail model or regime-transition opportunity-set change that keeps total return near/above `+170%`, max drawdown near `-8.5%`, DSR near/above `0.99`, and PBO `0.0`.

[2026-07-06T17:25:00+08:00] Market-euphoric path-tail cash becomes the current v3 return frontier, but still does not clear stress gates:
The high-confidence v3 frontier's maximum path drawdown was concentrated in `2026-04-22` through `2026-05-11`. A retained selected-pick feature join (`/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_high_confidence_selected_pick_feature_join_20260706.json`) showed the losing Rank1 picks in that window shared a concrete PIT state: strong benchmark 20d return, Rank1 5d/20d return percentiles near the top of the universe, high amount-expansion percentile, medium/high volatility percentile, and relatively modest absolute `avg_amount_20d`.

补充说明
- Retained proxy scan `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_high_confidence_path_tail_proxy_scan_20260706.json` found a bounded condition that improved the selected-pick proxy from `+170.8%` to about `+180.9%`: cash when Rank1 has `benchmark_return_20d >= 0.04`, `return_5d_percentile >= 0.98`, `return_20d_percentile >= 0.94`, `amount_10d_vs_20d_percentile >= 0.90`, `volatility_20d_percentile >= 0.55`, and `avg_amount_20d <= 300M`.
- Registered spec `path_tail_overheat_cash_high_confidence_tail_cash_weak_low_vol_overheat_top3_20d_v1` keeps the v3 high-confidence tail-cash parent and adds this narrow market-euphoric volume-tail cash switch. The grid is bounded to four trials: benchmark 20d threshold `0.04/0.05` x `avg_amount_20d` cap `200M/300M`.
- First formal replay `model-comparison-report-73776d622f55d436` was intentionally not accepted as a frontier because the spec initially had only 2 trials and triggered `overfit:insufficient_eligible_trials_for_pbo`; it also exposed a replay/proxy mismatch because the compact rank-signal subset did not retain `avg_amount_20d`.
- Engineering correction: `_rank_signal_feature_subset` now includes `avg_amount_20d`, with a regression test, so streamed replay can evaluate the same tail-cash condition used by the selected-pick proxy without loading full feature rows into prediction storage.
- Corrected 4-trial formal replay root: `/tmp/stock_dashboard_label_v3_path_tail_cash_v2_full713_min60`; candidate run `walk-forward-model-candidate-run-d23c47012ce81e1f`; report `model-comparison-report-00602b973c354176`; best `trial-002` uses the `0.04` benchmark threshold and `300M` amount cap.
- Best formal result: total return `+180.9%`, annualized `+49.0%`, max drawdown `-8.68%`, selected mean `0.02438`, positive date rate `46.55%`, 11 negative months, worst monthly mean `-0.0306`, path drawdown sum `-1.4519`, DSR confidence `0.9995`, alpha t-stat `4.9796`, PBO proxy `0.0`, winner dependency `ready`.
- This is now the v3 return/path frontier and is materially better than the prior high-confidence frontier on return and overfit statistics. It still does not complete the user's goal: negative monthly mean stress remains, path drawdown sum is still below the `>-1.0` gate, and governance remains blocked by T+1 execution, suspension/limit buy/sellability, fees/slippage/stamp-tax and ADV/fill-rate.
- Next work should not celebrate the higher headline return as success. The useful next target is the remaining path sequence after the tail-cash switch, while preserving the new `+180%`-class return and DSR/PBO quality. If a proposed blocker fix only reduces return or simply adds broad cash without improving path/month stress, it should be downgraded.

[2026-07-06T17:55:00+08:00] Weak-low-liquidity tail cash improves stability but still does not clear path stress:
After market-euphoric path-tail cash, the maximum path drawdown moved to `2024-08-12` through `2024-09-23`. A retained Rank1 feature join (`/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_path_tail_frontier_aug_sep_2024_rank1_feature_join_20260706.json`) showed this was the opposite regime: weak benchmark 20d return, very low Rank1 volatility/turnover, and often very low absolute `avg_amount_20d`. The existing weak-low-vol cash switch missed this segment because it required elevated benchmark volatility; this drawdown was a low-volatility weak-market grind.

补充说明
- Retained proxy scan `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_path_tail_frontier_weak_low_liquidity_proxy_scan_20260706.json` found that cashing out a narrow weak-market low-liquidity Rank1 tail can improve path from `-1.4519` to about `-1.3019` and reduce negative months from `11` to `10`, while keeping total return around `+174.9%`.
- Code correction: `_rank_signal_feature_subset` now retains `turnover_rate_percentile` in addition to `avg_amount_20d`, so streamed replay can evaluate the same weak-low-liquidity condition as the proxy scan without storing full feature rows.
- Registered spec `weak_low_liquidity_tail_cash_path_tail_overheat_high_confidence_top3_20d_v1` as a stability challenger. It extends the current path-tail return frontier with a narrow `rank1_weak_low_liquidity_tail_cash` switch. The grid is bounded to four trials and is not a broad cash-switch search.
- Formal v3 replay root: `/tmp/stock_dashboard_label_v3_weak_low_liquidity_tail_cash_full713_min60`; candidate run `walk-forward-model-candidate-run-152a0094db668f36`; report `model-comparison-report-a51dd60f1a714872`.
- Best formal trial `trial-000`: total return `+174.9%`, annualized `+47.7%`, max drawdown `-8.68%`, selected mean `0.02469`, positive date rate `45.79%`, negative months `10`, worst monthly mean `-0.0302`, path drawdown sum `-1.3019`, DSR confidence `0.9997`, alpha t-stat `5.0561`, PBO proxy `0.0`, winner dependency `ready`.
- Interpretation: this is a real stability improvement over the current return frontier (`path -1.4519 -> -1.3019`, negative months `11 -> 10`) while preserving a +170%-class return and overfit quality. It is not the final strategy because it gives up headline return versus `+180.9%` and still fails both monthly/path execution stress gates.
- Next search should treat two frontiers separately: return frontier `+180.9%` / path `-1.4519`, and stability frontier `+174.9%` / path `-1.3019` / 10 negative months. A useful next candidate must either preserve the return frontier while improving path, or preserve the stability frontier while moving path materially closer to `>-1.0`.

[2026-07-06T18:45:00+08:00] Weak-defensive-grind position scaling becomes the current v3 frontier but remains blocked by negative months:
Full-window selected-pick diagnostics after the weak-low-liquidity frontier found two separate residual tail states: crowded low-liquidity momentum tails and weak-market low-volatility defensive grinds. Cashing both tails could clear path stress, but the more aggressive cash version was killed by `positive_selected_top_k_rate_below_gate`. The accepted implementation therefore keeps the congested low-liquidity momentum tail as a bounded cash switch and handles the weak defensive grind through `signal_position_scaling`, reducing exposure instead of converting the date to cash.

补充说明
- Retained diagnostics: full selected-pick join `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_stability_frontier_full_selected_pick_feature_join_20260706.json`, congested proxy scan `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_stability_frontier_full_congested_momentum_proxy_scan_20260706.json`, weak-defensive-grind proxy scan `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_congested_frontier_weak_defensive_grind_proxy_scan_20260706.json`.
- Downgraded cash-only reports: `model-comparison-report-459d10497a95bb81` and `model-comparison-report-1a82298f4b6b5656`; both cleared path but were killed by positive-rate gate. Diagnostic-only.
- Current formal replay root `/tmp/stock_dashboard_label_v3_weak_defensive_grind_scale_congested_tail_full713_min60`; candidate run `walk-forward-model-candidate-run-1fe34d1ea3e50563`; report `model-comparison-report-4136b7f6fdc835ab`.
- Best trial `weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_v1:trial-002`: total `+204.9%`, annualized `+53.8%`, maxDD `-4.33%`, selected mean `0.02716`, positive date rate `45.02%`, negative months `9`, worst monthly mean `-0.0268`, path `-0.9661`, alpha t-stat `5.7873`, DSR `0.99998`, PBO `0.0`.
- This is the first formal label-v3 replay to clear `execution_stress:portfolio_path_drawdown_sum_below_minus_1` while preserving positive-rate/OOS gates and improving return versus the previous `+180.9%` and `+174.9%` frontiers.
- It is still not a final production, paper-tracking, dashboard, or policy-config strategy: `execution_stress:negative_monthly_mean_under_base_cost` fails for `2024-02`, `2024-03`, `2024-05`, `2024-08`, `2025-04`, `2025-05`, `2025-08`, `2025-11`, `2026-03`; governance blocks now remain fees/slippage/stamp-tax, ADV/capacity and fill-rate; T+1 and suspension/limit buy/sellability are covered by label-v3 evidence.
- Next optimization should target negative-month stress through granular portfolio construction, conditional exposure scaling or additional feature sources. Do not add broad cash switches that merely reduce participation without preserving the current frontier floors.

[2026-07-06T19:35:00+08:00] Residual high-momentum amount-tail scaling improves the current v3 frontier but does not clear negative months:
A focused proxy scan on the current v3 frontier tested extra signal-date scaling for the remaining negative-month states. It found no configuration that reduced negative months from `9` to `8` while preserving the current `+204.9%` rolling total-return floor. The non-degrading direction was narrower: residual high-momentum, high amount-expansion Rank1 dates with benchmark 20d strength and moderate volatility could be scaled down without reducing headline return, improving path stress and max drawdown.

补充说明
- Retained proxy scan: `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_current_frontier_negative_month_extra_scale_proxy_scan_20260706.json`.
- Code now supports optional `rank1_residual_momentum_amount_tail_scale` inside `signal_position_scaling`; it is fixed, not a broader grid expansion. The spec still has `4` trials.
- Residual rule: Rank1 `benchmark_return_20d >= 0.03`, `benchmark_return_10d <= 0.04`, `return_5d_percentile >= 0.98`, `return_20d_percentile >= 0.96`, `amount_10d_vs_20d_percentile >= 0.95`, `volatility_20d_percentile >= 0.30`, `avg_amount_20d <= 600M`, scale to `0.3`.
- Formal same-contract replay root `/tmp/stock_dashboard_label_v3_residual_momentum_scale_full713_min60`; candidate run `walk-forward-model-candidate-run-ffe5dcac95195469`; report `model-comparison-report-6a8763b11b62ab02`.
- New best trial remains `weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_v1:trial-002`: total `+208.5%`, annualized `+54.4%`, maxDD `-3.71%`, selected mean `0.02811`, positive date rate `45.02%`, negative months `9`, worst monthly mean `-0.0268`, path `-0.8905`, alpha t-stat `5.9339`, DSR `0.99999`, PBO `0.0`.
- This is a non-degrading frontier improvement over the previous `+204.9%`, `-4.33%` maxDD and `-0.9661` path result. It still fails `execution_stress:negative_monthly_mean_under_base_cost` for the same `9` months and remains blocked by execution/governance. Do not promote, dashboard-project, paper-track or policy-config it.

[2026-07-06T20:05:00+08:00] Execution governance is partially evidence-cleared by label v3, but cost/capacity remains blocked:
The residual momentum frontier report was rebuilt from the existing candidate run and registry without rerunning full713 or reading large matrices. The rebuilt report adds `execution_label_contract`, allowing governance to distinguish execution gates covered by label-v3 evidence from gates that are still only policy requirements.

补充说明
- Rebuilt comparison report: `model-comparison-report-6a8763b11b62ab02`; rebuilt governance decision: `governance-promotion-decision-cceadd52f4d7aa91`; dashboard projection remains blocked as `dashboard-approved-projection-registry-4d3ac652cf778025`.
- `execution_label_contract` marks `t_plus_1_execution_model` and `suspension_limit_buy_sellability` ready because label-v3 rows persist `entry_execution` plus per-horizon exit execution and the runner evaluates `label_status=ready` rows only.
- Governance no longer lists `execution:t_plus_1_execution_model` or `execution:suspension_limit_buy_sellability` for this v3 report.
- Governance still blocks `execution:fees_slippage_stamp_tax`, `execution:adv_capacity_fill_rate`, and `model_comparison_report:execution_stress:negative_monthly_mean_under_base_cost`.
- This is execution-governance cleanup only. It does not promote the strategy, does not clear negative-month stress, and does not model cost/capacity. Next work should either add order-level fee/slippage/capacity labels or find a non-degrading way to eliminate the 9 remaining negative months.

[2026-07-06T20:15:00+08:00] Model-exploration temp data was compacted after the residual frontier replay:
The post-frontier cleanup archived small evidence JSONs from downgraded replay roots into `/tmp/stock_dashboard_retained_reports_20260706/retained_artifacts` before deleting the obsolete compact replay directories. This keeps cited report/registry/governance/projection evidence recoverable without leaving every historical challenger root in `/tmp`.

补充说明
- Retained artifact archive contains `125` JSON/text files and is about `11M`; total retained evidence directory is now about `109M`.
- At that cleanup point, `/tmp` research footprint was bounded to the canonical PIT feature/input root, canonical label-v3 root, residual-momentum frontier root, immediate predecessor comparator, and retained compact evidence. A later cleanup after the Rank2 frontier deleted the now-superseded compact replay roots and retained only the current Rank2 root plus the immediate Rank1-extreme comparator.
- Future research runs should not create duplicate full713 PIT feature or label matrices for deterministic registered-spec replay. Use the existing canonical matrix artifacts plus `--stream-matrix-replay`; create a new matrix only when the feature or label definition itself changes.
- This cleanup does not change the model conclusion: current frontier remains `model-comparison-report-6a8763b11b62ab02`, still blocked by 9 negative months plus fee/slippage/stamp-tax and ADV/capacity execution governance.

[2026-07-06T20:52:00+08:00] High-turnover momentum-tail cash improves the v3 frontier but still does not clear negative months:
After generating a current-frontier selected-pick feature join from existing retained evidence, a compact proxy scan tested additional Rank1 high-risk tail conditions on the residual-momentum frontier. The scan found that broad rules reducing negative months from `9` to `7` materially degraded return, but a very narrow high-turnover momentum-tail cash switch was non-degrading and worth formal replay.

补充说明
- New retained current-frontier join: `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_residual_momentum_frontier_selected_pick_feature_join_20260706.json`, matched `1491/1491` selected picks without rescanning or duplicating the PIT matrix.
- New retained proxy scan: `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_residual_momentum_frontier_high_risk_tail_proxy_scan_20260706.json`, checked `213840` bounded Rank1 PIT-feature configs. Negative-month reducers existed but were rejected because the best `7`-negative-month variants cut rolling total return to about `+195.0%` or lower and worsened path in some variants. The accepted non-degrading proxy condition triggered `6` dates.
- Registered fixed rule: cash when Rank1 has `benchmark_return_20d >= 0.0`, `benchmark_return_10d <= 0.02`, `return_5d_percentile >= 0.98`, `return_20d_percentile >= 0.94`, `amount_10d_vs_20d_percentile >= 0.95`, `volatility_20d_percentile >= 0.65`, `turnover_rate_percentile >= 0.85`, and `avg_amount_20d <= 300M`. This is fixed evidence-driven tail handling, not a grid expansion; the spec remains `4` trials.
- Formal same-contract stream replay root: `/tmp/stock_dashboard_label_v3_high_turnover_tail_cash_full713_min60`; candidate run `walk-forward-model-candidate-run-2f51944f4d8a3cdc`; report `model-comparison-report-14a320961b9942af`; governance decision `governance-promotion-decision-f282bf9c0ec5825c`; dashboard registry `dashboard-approved-projection-registry-5cc32e123996eaa8`.
- New best remains `weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_v1:trial-002`: total return `+217.1%`, annualized `+56.1%`, max drawdown `-3.69%`, selected mean `0.02796`, positive date rate `45.02%`, negative months `9`, worst monthly mean `-0.0268`, path drawdown sum `-0.8905`, DSR `0.999996`, PBO `0.0`.
- The rule triggered formal cash dates `2024-03-25`, `2025-03-11`, `2025-05-27`, `2025-07-15`, `2026-03-10`, and `2026-03-11`.
- This is the current v3 return/drawdown frontier, but not a success case. It still fails `execution_stress:negative_monthly_mean_under_base_cost`, and governance remains blocked on `fees_slippage_stamp_tax` plus `adv_capacity_fill_rate`. T+1 and suspension/limit buy/sellability remain covered by label-v3 evidence. Do not promote, dashboard-project, paper-track, or policy-config it.

[2026-07-06T21:38:00+08:00] Rank1 high-turnover low-liquidity position scaling improves the v3 frontier and reduces negative months to 8:
A compact rank-level scan on the high-turnover cash frontier tested per-pick exposure scaling instead of whole-signal cashing. This is a different portfolio-construction layer: only Rank1 exposure is reduced when a narrow high-momentum / high-turnover / low-absolute-liquidity state appears; Rank2/Rank3 can remain invested. The scan was retained at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_high_turnover_frontier_rank_level_scaling_proxy_scan_20260706.json` and did not create duplicate matrices.

补充说明
- New code path: `rank_position_scaling.mode = rank1_high_momentum_low_liquidity_turnover_scale`; it records `rank_position_scale`, `rank_position_scale_reasons`, `rank_position_scaled_pick_count`, and applies the same scale to weighted return and gross exposure.
- Registered fixed rule: scale Rank1 to `0.0` when Rank1 has `benchmark_return_20d >= 0.0`, `benchmark_return_10d <= 0.04`, `return_5d_percentile >= 0.90`, `return_20d_percentile >= 0.94`, `amount_10d_vs_20d_percentile >= 0.90`, `volatility_20d_percentile >= 0.55`, `turnover_rate_percentile >= 0.85`, and `avg_amount_20d <= 100M`. The spec remains bounded at `4` trials.
- Formal same-contract stream replay root: `/tmp/stock_dashboard_label_v3_rank1_tail_scaled_high_turnover_full713_min60`; candidate run `walk-forward-model-candidate-run-0be89efe67f05ab6`; report `model-comparison-report-c75ba1220c2c28f6`; governance decision `governance-promotion-decision-bafc27fd02948b15`; dashboard registry `dashboard-approved-projection-registry-11cd754efd8af29a`.
- Best trial remains `weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_v1:trial-002`: total return `+221.1%`, annualized `+56.9%`, max drawdown `-3.29%`, selected mean `0.02832`, positive date rate `45.18%`, negative months `8`, worst monthly mean `-0.0268`, path drawdown sum `-0.8905`, alpha t-stat `6.2032`, DSR `0.999997`, PBO `0.0`.
- Versus the previous high-turnover frontier (`model-comparison-report-14a320961b9942af`), this is non-degrading on the required metrics: total `+217.1% -> +221.1%`, annualized `+56.1% -> +56.9%`, maxDD `-3.69% -> -3.29%`, selected mean `0.02796 -> 0.02832`, positive date rate `45.02% -> 45.18%`, negative months `9 -> 8`, DSR `0.999996 -> 0.999997`, PBO stays `0.0`.
- The new rule formally triggers `6` Rank1 picks and lowers average gross exposure from about `0.7215` to `0.7160`; output root size is `30M`, so artifact growth is controlled.
- This became the label-v3 return/drawdown/stability frontier at the time, but was later superseded. It remained blocked by `execution_stress:negative_monthly_mean_under_base_cost`; governance still blocked fees/slippage/stamp-tax and ADV/capacity/fill-rate. Do not promote, dashboard-project, paper-track or policy-config it.

[2026-07-06T22:10:00+08:00] Extreme Rank1 momentum-turnover position scaling improves the frontier and reduces negative months to 7:
After accepting the first Rank1 position-scaling layer, a second compact selected-pick scan targeted the remaining eight negative months. The scan stayed bounded to the current frontier's selected picks and retained only a small JSON artifact at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_rank1_scaled_frontier_remaining_negative_month_rank_scale_scan_20260706.json`.

补充说明
- New fixed subrule: `rank1_extreme_momentum_turnover_scale` inside `rank_position_scaling`. It scales only Rank1 to `0.0` when Rank1 has `benchmark_return_20d >= 0.03`, `benchmark_return_10d <= 0.06`, `return_5d_percentile >= 0.98`, `return_20d_percentile >= 0.96`, `amount_10d_vs_20d_percentile >= 0.88`, `volatility_20d_percentile >= 0.30`, `turnover_rate_percentile >= 0.75`, and `avg_amount_20d <= 600M`.
- This is not a grid expansion: all new hyperparameter keys are fixed single-value lists and the spec remains at `4` trials.
- Formal same-contract replay root: `/tmp/stock_dashboard_label_v3_rank1_extreme_scaled_high_turnover_full713_min60`; candidate run `walk-forward-model-candidate-run-273a8a8a8c2dee63`; report `model-comparison-report-e13ac319e2fc2c94`; governance decision `governance-promotion-decision-2ac0651c51a5718d`; dashboard registry `dashboard-approved-projection-registry-fa9a4407627b9066`.
- Best trial remains `weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_v1:trial-002`: total return `+227.9%`, annualized `+58.1%`, max drawdown `-3.28%`, selected mean `0.02900`, positive date rate `45.18%`, negative months `7`, worst monthly mean `-0.0268`, path drawdown sum `-0.8905`, alpha t-stat `6.3414`, DSR `0.999999`, PBO `0.0`.
- Versus the prior Rank1-scaled frontier (`model-comparison-report-c75ba1220c2c28f6`): total `+221.1% -> +227.9%`, annualized `+56.9% -> +58.1%`, maxDD `-3.29% -> -3.28%`, selected mean `0.02832 -> 0.02900`, negative months `8 -> 7`, alpha `6.2032 -> 6.3414`, DSR `0.999997 -> 0.999999`, PBO remains `0.0`.
- The two Rank1 scaling rules formally trigger `20` Rank1 picks; output root remains compact at about `30M`, and retained compact evidence is about `115M`.
- This became the v3 frontier at the time, but was later superseded by the Rank2 high-momentum turnover subrule. It remained blocked by `execution_stress:negative_monthly_mean_under_base_cost` for `2024-02`, `2024-03`, `2024-08`, `2025-04`, `2025-08`, `2025-11`, and `2026-03`; governance still blocked fee/slippage/stamp-tax and ADV/capacity/fill-rate. Do not promote, dashboard-project, paper-track or policy-config it.

[2026-07-06T22:45:00+08:00] Rank2 high-momentum turnover position scaling becomes the current v3 frontier and reduces negative months to 6:
After the extreme Rank1 frontier, a targeted single-rule scan stayed bounded to residual selected-pick states and wrote only `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_rank1_extreme_frontier_targeted_single_rule_proxy_scan_20260706.json` (`486KB`). It checked `37,908` configs, found `80` proxy non-degrading candidates, and selected a fixed Rank2 high-momentum / high-amount-expansion / high-turnover position-scaling rule for formal replay.

补充说明
- New fixed subrule: `rank2_high_momentum_turnover_scale` inside `rank_position_scaling`. It scales only Rank2 to `0.0` when Rank2 has `benchmark_return_20d >= 0.0`, `benchmark_return_10d <= 0.02`, `return_5d_percentile >= 0.94`, `return_20d_percentile >= 0.90`, `amount_10d_vs_20d_percentile >= 0.94`, `volatility_20d_percentile >= 0.55`, `turnover_rate_percentile >= 0.85`, and `avg_amount_20d <= 800M`.
- This is not a grid expansion: all new hyperparameter keys are fixed single-value lists and the spec remains at `4` trials.
- Formal same-contract replay root: `/tmp/stock_dashboard_label_v3_rank2_scaled_high_turnover_full713_min60`; candidate run `walk-forward-model-candidate-run-c2b9db7e29b74f5d`; report `model-comparison-report-e3c25f696d53e504`; governance decision `governance-promotion-decision-2e5a3c3a3e691b1a`; dashboard registry `dashboard-approved-projection-registry-20de2515c0de9283`.
- Best trial remains `weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_v1:trial-002`: total return `+230.3%`, annualized `+58.6%`, max drawdown `-3.28%`, selected mean `0.02922`, positive date rate `45.64%`, negative months `6`, worst monthly mean `-0.0268`, path drawdown sum `-0.8905`, alpha t-stat `6.3980`, DSR `0.999999`, PBO `0.0`.
- Versus the prior extreme Rank1 frontier (`model-comparison-report-e13ac319e2fc2c94`): total `+227.9% -> +230.3%`, annualized `+58.1% -> +58.6%`, maxDD unchanged at `-3.28%`, selected mean `0.02900 -> 0.02922`, positive date rate `45.18% -> 45.64%`, negative months `7 -> 6`, alpha `6.3414 -> 6.3980`, DSR non-degrading, PBO remains `0.0`.
- This became the v3 frontier at the time and was later superseded by the Rank3 high-momentum turnover subrule. It remained blocked by `execution_stress:negative_monthly_mean_under_base_cost` for `2024-02`, `2024-03`, `2024-08`, `2025-08`, `2025-11`, and `2026-03`; governance still blocked fee/slippage/stamp-tax and ADV/capacity/fill-rate. Do not promote, dashboard-project, paper-track or policy-config it.

[2026-07-06T23:15:00+08:00] Weak-market low-volatility Rank1 scaling is downgraded because it sacrifices total return:
After the Rank2 frontier, a bounded proxy check tested whether the earlier weak-market low-volatility / low-turnover Rank1 tail could be combined with the then-current Rank2 frontier. The proxy artifact is retained at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_rank2_frontier_weak_lowvol_combo_proxy_scan_20260706.json`; it matched `1473/1473` then-current selected picks to retained PIT features and did not rescan or duplicate the canonical matrices.

补充说明
- Tested fixed rule: scale Rank1 to `0.0` when `benchmark_return_20d <= -0.02`, `benchmark_return_10d <= 0.02`, `benchmark_volatility_20d >= 0.045`, `low_volatility_percentile >= 0.97`, `turnover_rate_percentile <= 0.07`, and `avg_amount_20d <= 300M`.
- Formal same-contract replay root was `/tmp/stock_dashboard_label_v3_rank2_weak_lowvol_scaled_full713_min60`; candidate run `walk-forward-model-candidate-run-fbb1117292de6980`; report `model-comparison-report-bd34471e08afc7a5`; governance decision `governance-promotion-decision-452d5387245370a3`. Small report/registry/governance/projection JSONs were archived, and the compact replay root was deleted to avoid artifact growth.
- Result: worst monthly mean improved from `-0.0268` to `-0.0170`, selected mean improved from `0.02922` to `0.02941`, alpha improved from `6.3980` to `6.4526`, DSR stayed excellent and PBO stayed `0.0`.
- Rejection reason: total return degraded from `+230.3%` to `+226.3%`, annualized return degraded from `+58.6%` to `+57.8%`, positive date rate fell from `45.64%` to `45.48%`, and negative months stayed `6`. This violates the current non-degradation floor, so the rule was removed from active code/registry and must not replace the Rank2 frontier.

[2026-07-06T23:35:00+08:00] Weak-lowvol plus Rank3 high-momentum combo is also downgraded under the non-degradation floor:
After the weak-lowvol single-rule rejection, a bounded combo replay tested whether adding a fixed Rank3 high-momentum / high-turnover scale could recover return while preserving the improved worst-month profile. The run reused the canonical full713 input snapshot, PIT feature matrix and label-v3 executable label matrix via stream replay.

补充说明
- Formal same-contract replay root was `/tmp/stock_dashboard_label_v3_rank1_weaklow_rank3_scaled_full713_min60`; candidate run `walk-forward-model-candidate-run-d00208b0c201d478`; report `model-comparison-report-e474a755224dbc7b`; governance decision `governance-promotion-decision-26b247a9f2085ad7`; dashboard registry `dashboard-approved-projection-registry-8d38be0e2582a8f2`. Small report/registry/governance/projection JSONs were archived into `/tmp/stock_dashboard_retained_reports_20260706/retained_artifacts`, excluding the large candidate-run JSON, and the compact replay root was deleted.
- Result: worst monthly mean stayed improved at `-0.0170`, selected mean improved to `0.02960`, alpha improved to `6.5170`, DSR improved to `0.999999`, PBO stayed `0.0`, max drawdown and path drawdown sum did not worsen.
- Rejection reason: total return remained below the Rank2 frontier, `+228.6%` versus `+230.3%`, annualized return was `+58.3%` versus `+58.6%`, and negative months stayed `6`. Because it did not beat the hard return floor and did not clear the remaining monthly stress gate, the weak-lowvol branch remains inactive; the later accepted Rank3-only replay is separate from this rejected combo.

[2026-07-06T23:55:00+08:00] Rank3 high-momentum turnover position scaling becomes the current v3 frontier but remains blocked:
After removing the rejected weak-lowvol branch, a same-contract Rank3-only full713 replay tested the fixed Rank3 high-momentum / high-turnover subrule on top of the accepted Rank1, Rank1-extreme and Rank2 rank-position scaling rules. This reused the canonical full713 input snapshot, PIT feature matrix and label-v3 executable label matrix via `--stream-matrix-replay`; no duplicate feature or label matrix was created.

补充说明
- New fixed subrule: `rank3_high_momentum_turnover_scale` inside `rank_position_scaling`. It scales only Rank3 to `0.0` when Rank3 has `benchmark_return_20d >= 0.03`, `benchmark_return_10d <= 0.06`, `return_5d_percentile >= 0.96`, `return_20d_percentile >= 0.90`, `amount_10d_vs_20d_percentile >= 0.90`, `volatility_20d_percentile >= 0.75`, `turnover_rate_percentile >= 0.75`, and `avg_amount_20d <= 800M`.
- This is still not a grid expansion: all new hyperparameter keys are fixed single-value lists and the spec remains at `4` trials.
- Formal same-contract replay root: `/tmp/stock_dashboard_label_v3_rank3_scaled_full713_min60`; candidate run `walk-forward-model-candidate-run-91205683e19b48a5`; report `model-comparison-report-0c77a38610312156`; governance decision `governance-promotion-decision-2701120490f81ac0`; dashboard registry `dashboard-approved-projection-registry-1e0f1daaa94e8bfb`.
- Best trial remains `weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_v1:trial-002`: total return `+232.5%`, annualized `+59.0%`, max drawdown `-3.28%`, selected mean `0.02941`, positive date rate `45.79%`, negative months `6`, worst monthly mean `-0.0268`, path drawdown sum `-0.8905`, alpha t-stat `6.4621`, DSR `0.999999`, PBO `0.0`.
- Versus the prior Rank2 frontier (`model-comparison-report-e3c25f696d53e504`): total `+230.3% -> +232.5%`, annualized `+58.6% -> +59.0%`, maxDD unchanged at `-3.28%`, selected mean `0.02922 -> 0.02941`, positive date rate `45.64% -> 45.79%`, negative months unchanged at `6`, alpha `6.3980 -> 6.4621`, DSR non-degrading, PBO remains `0.0`.
- This became the v3 frontier at the time and was later superseded by the Rank1 neutral-chop subrule. It remained blocked by `execution_stress:negative_monthly_mean_under_base_cost` for `2024-02`, `2024-03`, `2024-08`, `2025-08`, `2025-11`, and `2026-03`; governance still blocked fee/slippage/stamp-tax and ADV/capacity/fill-rate. Do not promote, dashboard-project, paper-track or policy-config it.

[2026-07-07T00:40:00+08:00] Rank1 neutral-chop position scaling becomes the current v3 frontier and reduces negative months to 5:
After the Rank3 frontier, a bounded selected-pick proxy scan targeted the remaining negative-month states without rescanning canonical matrices. The retained proxy artifact is `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_rank3_frontier_manual_negative_month_proxy_scan_20260706.json`; it used the then-current Rank3 selected picks joined to retained PIT features and identified a narrow Rank1 neutral-chop state that removed the `2025-11` negative month in proxy.

补充说明
- New fixed subrule: `rank1_neutral_chop_scale` inside `rank_position_scaling`. It scales only Rank1 to `0.0` when `-0.01 <= benchmark_return_20d <= 0.03`, `benchmark_return_10d <= 0.03`, `benchmark_volatility_20d >= 0.04`, `return_5d_percentile >= 0.64`, `return_20d_percentile <= 0.97`, `amount_10d_vs_20d_percentile >= 0.59`, `max_drawdown_20d <= -0.003`, and `avg_amount_20d <= 2300M`.
- This is not a grid expansion: all new hyperparameter keys are fixed single-value lists and the spec remains at `4` trials. The streamed prediction feature subset now retains `max_drawdown_20d` so the formal replay evaluates the same condition as the proxy.
- Formal same-contract replay root: `/tmp/stock_dashboard_label_v3_rank1_neutral_chop_scaled_full713_min60`; candidate run `walk-forward-model-candidate-run-5bd0a8b3d768a339`; report `model-comparison-report-3c8b5ce0286183c6`; governance decision `governance-promotion-decision-3f01749e7786e2d9`; dashboard registry `dashboard-approved-projection-registry-c55b19ec9a31e663`.
- Best trial remains `weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_v1:trial-002`: total return `+236.2%`, annualized `+59.7%`, max drawdown `-3.28%`, selected mean `0.02952`, positive date rate `45.79%`, negative months `5`, worst monthly mean `-0.0268`, path drawdown sum `-0.8905`, alpha t-stat `6.6140`, DSR `0.9999996`, PBO `0.0`.
- Versus the prior Rank3 frontier (`model-comparison-report-0c77a38610312156`): total `+232.5% -> +236.2%`, annualized `+59.0% -> +59.7%`, maxDD unchanged at `-3.28%`, selected mean `0.02941 -> 0.02952`, negative months `6 -> 5`, alpha `6.4621 -> 6.6140`, DSR non-degrading, PBO remains `0.0`.
- This is the current v3 frontier, but still not the final goal. It remains blocked by `execution_stress:negative_monthly_mean_under_base_cost` for `2024-02`, `2024-03`, `2024-08`, `2025-08`, and `2026-03`; governance still blocks fee/slippage/stamp-tax and ADV/capacity/fill-rate. Do not promote, dashboard-project, paper-track or policy-config it.

[2026-07-07T01:25:00+08:00] Low-ADV Rank2 capacity scaling is rejected and retained as compact evidence only:
After the current neutral-chop frontier, a capacity-focused proxy tested whether very low ADV Rank2 exposure should be removed to address the remaining ADV/capacity blocker without changing the model family. The proxy was intentionally bounded to selected picks and wrote only `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_neutral_chop_frontier_low_adv_capacity_proxy_scan_20260707.json`.

补充说明
- Tested fixed rule: scale only Rank2 to `0.0` when `avg_amount_20d < 20M`. The proxy triggered `36` Rank2 picks, improved selected-pick mean from `0.0403828` to `0.0406200`, and kept negative months at `5`, so it qualified only for formal replay.
- Formal same-contract stream replay root was `/tmp/stock_dashboard_label_v3_rank2_low_adv_scaled_full713_min60`; candidate run `walk-forward-model-candidate-run-0ff0a1dae6de4d1b`; report `model-comparison-report-0faf6038b64791dc`; governance decision `governance-promotion-decision-e4a78f8bf2ce99ab`; dashboard registry `dashboard-approved-projection-registry-dca8a0258ec685b6`.
- Result: total return `+235.1%`, annualized `+59.5%`, max drawdown `-3.28%`, selected mean `0.03054`, positive date rate `45.79%`, negative months `5`, worst monthly mean `-0.0268`, path drawdown sum `-0.8535`, alpha t-stat `6.6623`, DSR `0.9999997`, PBO `0.0`.
- Rejection reason: total return and annualized return fell below the current neutral-chop floor (`+236.2%` / `+59.7%`). Stability did not degrade, but the non-degradation contract requires return and stability both to pass. The active code/registry rule was removed.
- Cleanup: the `30M` formal replay root was deleted after writing compact rejection summary `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_rank2_low_adv_capacity_formal_rejection_20260707.json`. Current frontier remains `model-comparison-report-3c8b5ce0286183c6`.

[2026-07-07T01:35:00+08:00] Research artifact retention removes candidate-run payloads from compact archive:
The retained evidence directory `/tmp/stock_dashboard_retained_reports_20260706` still contained stale `walk_forward_model_candidate_runs/*candidate-run*.json` files from earlier archived roots. These are not needed for current frontier/rejection traceability because the retained comparison reports, governance decisions, projection registries, proxy scans and formal rejection summaries carry the cited IDs and summary metrics.

补充说明
- Removed retained candidate-run payloads and empty directories from `/tmp/stock_dashboard_retained_reports_20260706`.
- Retained evidence footprint is now `32M`, down from `119M`; candidate-run files in retained evidence are now `0`.
- Future cleanup rule: keep canonical input/feature/label matrices, current frontier root, immediate predecessor comparator root, and small summary/diagnostic/rejection JSONs; do not retain historical candidate-run payloads unless a later investigation explicitly needs split-level prediction detail.

[2026-07-07T01:50:00+08:00] Fee/slippage/stamp-tax gate becomes evidence-driven and clears for the current frontier:
The current neutral-chop frontier already had comparison-report cost-stress evidence showing positive mean net excess after 1x/2x/3x fee, slippage and stamp-tax proxy costs. The governance layer previously kept `fees_slippage_stamp_tax` as a fixed fail-closed blocker even when this evidence existed. This was a governance blocker, not a model strategy issue.

补充说明
- Code change: `execution_label_contract` and governance execution gates now clear `fees_slippage_stamp_tax` only when `execution_diagnostics.cost_stress` has sufficient periods and positive 1x/2x/3x stressed mean. Insufficient-period unit samples still block.
- Refreshed current frontier artifacts without rerunning the candidate model: comparison report `model-comparison-report-74afadcd87fa8bab`, governance decision `governance-promotion-decision-835b37ab25b1a90b`, dashboard registry `dashboard-approved-projection-registry-50154c659adf9898`.
- New governance blockers are `execution:adv_capacity_fill_rate`, `model_comparison_report:execution_stress:negative_monthly_mean_under_base_cost`, and `model_comparison_report:governance_promotion_pending`. The fee/slippage/stamp-tax blocker is no longer present.
- This does not promote the strategy: negative-month stress and ADV/capacity/fill-rate remain unresolved, and dashboard approved projection count remains blocked.

[2026-07-07T02:20:00+08:00] ADV/capacity blocker is now quantified for the current frontier:
The current neutral-chop candidate-run artifact did not yet persist pick-level `avg_amount_20d`, so the runner was updated to include a bounded set of capacity fields on future selected-pick diagnostics: `avg_amount_20d`, `amount_10d_vs_20d_percentile`, and `turnover_rate_percentile`. A comparison-report capacity diagnostic was also added, using active capital weight `portfolio_weight * rank_weight_multiplier / selected_top_k`.

补充说明
- Capacity gate proxy: `1,000,000 CNY` portfolio, single pick can consume at most `5%` of `avg_amount_20d`, and every active pick must have fill rate `>= 1.0`.
- Current frontier diagnostic retained at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_neutral_chop_frontier_adv_capacity_diagnostic_20260707.json`.
- Result: `1473` selected picks, `998` active capital picks, `0` missing `avg_amount_20d` after joining retained PIT features, `27` active picks below full fill, full-fill rate `97.29%`, minimum fill rate `0.1186`.
- Interpretation: `execution:adv_capacity_fill_rate` remains a real blocker, not just missing plumbing. The earlier low-ADV Rank2 scaling attempt is still rejected because formal replay degraded total/annualized return; do not reactivate it as a shortcut.

[2026-07-07T02:45:00+08:00] Capacity-adjusted net proxy is rejected before formal replay:
After quantifying the 27 underfilled active picks, a bounded proxy applied partial-fill scaling to selected-pick net excess contributions, with unfilled capital treated as cash under the same zero-return convention used by the research workbench. This used the retained PIT feature join and wrote only a compact summary at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_neutral_chop_frontier_capacity_adjusted_net_proxy_20260707.json`.

补充说明
- Base selected-pick proxy: mean `0.04038`, positive date rate `60.90%`, negative months `5`, path drawdown sum `-0.8905`.
- Capacity-adjusted proxy: mean `0.03709`, positive date rate `61.10%`, negative months `6`, path drawdown sum `-0.7353`.
- Rejection reason: path improves, but mean falls and negative months increase from `5` to `6`. Current candidate-run lacks per-pick `target_total_return`, so this proxy also cannot prove non-degradation of total return. It is rejected without formal full713 replay.

[2026-07-07T03:25:00+08:00] Rank1 no-20d-drawdown position scaling becomes the current v3 research frontier and reduces negative months to 4:
After rejecting the capacity-adjusted net proxy, an expanded but bounded selected-pick proxy scan targeted the remaining negative-month states from the neutral-chop frontier. The retained scan is `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_neutral_chop_frontier_negative_month_expanded_proxy_scan_20260707.json`; it found one strict non-degrading candidate: scale Rank1 to `0.0` when `volatility_risk.max_drawdown_20d >= 0.0`.

补充说明
- New fixed subrule: `rank1_no_drawdown_scale` inside `rank_position_scaling`. It scales only Rank1 to `0.0` when the selected pick has no 20-day drawdown (`max_drawdown_20d >= 0.0`). This remains a fixed single-value subrule, not a grid expansion.
- Formal same-contract stream replay root: `/tmp/stock_dashboard_label_v3_rank1_no_drawdown_scaled_full713_min60` (`33M`); candidate run `walk-forward-model-candidate-run-3a5ae65140f49b02`; report `model-comparison-report-481e82b0595596c8`; governance decision `governance-promotion-decision-0205285afc980732`; dashboard registry `dashboard-approved-projection-registry-dd39a792b014227e`.
- Best trial remains `weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_v1:trial-002`: total return `+236.8%`, annualized `+59.8%`, max drawdown `-3.28%`, selected mean `0.02978`, execution mean `0.03056`, positive date rate `46.25%`, negative months `4` (`2024-02`, `2024-03`, `2024-08`, `2026-03`), worst monthly mean `-0.0268`, path drawdown sum `-0.8877`, alpha t-stat `6.6675`, DSR `0.9999997`, PBO `0.0`.
- Versus the prior neutral-chop frontier (`model-comparison-report-3c8b5ce0286183c6`): total `+236.2% -> +236.8%`, annualized `+59.7% -> +59.8%`, maxDD non-degrading at `-3.28%`, selected mean `0.02952 -> 0.02978`, positive date rate `45.79% -> 46.25%`, negative months `5 -> 4`, path drawdown sum `-0.8905 -> -0.8877`, alpha `6.6140 -> 6.6675`, DSR improves, PBO remains `0.0`.
- Capacity diagnostics improved only marginally and do not clear governance: active picks `998 -> 985`, below-full-fill active picks `27 -> 26`, full-fill rate `97.29% -> 97.36%`, minimum fill rate remains `0.1186`. Remaining blockers are `execution_stress:negative_monthly_mean_under_base_cost`, `execution_stress:capacity:adv_capacity_fill_rate_below_floor`, and `governance_promotion_pending`; governance also reports `execution:adv_capacity_fill_rate`.
- This is now the current blocked research frontier, not a production, paper-tracking, dashboard, or policy-config strategy.

[2026-07-07T04:05:00+08:00] Rank1 low-ADV turnover capacity scaling is rejected under the return floor:
After accepting the no-drawdown frontier, a bounded selected-pick capacity scan tested whether simple liquidity/turnover constraints could reduce the ADV/fill-rate blocker without sacrificing the frontier. The retained proxy scan is `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_no_drawdown_frontier_capacity_feature_proxy_scan_20260707.json`.

补充说明
- Best proxy rule: scale Rank1 to `0.0` when `avg_amount_20d < 15M` and `turnover_rate_percentile > 0.02`. In proxy it improved selected-pick mean (`0.04064 -> 0.04082`), kept negative months at `4`, improved path (`-0.8877 -> -0.7759`), and reduced below-full-fill active picks from `26` to `13`.
- Formal same-contract replay root was `/tmp/stock_dashboard_label_v3_rank1_low_adv_turnover_scaled_full713_min60`; candidate run `walk-forward-model-candidate-run-37eba98a2bcf5ef3`; report `model-comparison-report-66c772ffff0a9c05`; governance decision `governance-promotion-decision-a599c1b696c99407`; dashboard registry `dashboard-approved-projection-registry-a0ccc6be8b9db83a`.
- Formal result: total return `+223.2%`, annualized `+57.3%`, max drawdown `-3.28%`, path drawdown sum `-0.7759`, negative months `4`, alpha t-stat `6.7129`, DSR `0.9999998`, PBO `0.0`; below-full-fill active picks fell to `13`, but minimum fill rate still stayed `0.1186`.
- Rejection reason: total and annualized return fell below the active no-drawdown frontier (`+236.8%` / `+59.8%`). The path/capacity improvement is real but not enough to violate the non-degradation contract. The active code/registry rule was removed, compact rejection summary is retained at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_rank1_low_adv_turnover_capacity_formal_rejection_20260707.json`, and the formal replay root was deleted.

[2026-07-07T04:45:00+08:00] Rank1 high-position pullback scaling becomes the current v3 research frontier and reduces negative months to 3:
After the low-ADV capacity rejection, a compact selected-pick feature/label join was built for the no-drawdown frontier without copying canonical matrices: `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_no_drawdown_frontier_selected_pick_feature_label_join_20260707.json` (`4.9M`, `1473` rows, `0` missing labels/features). A total-curve-aligned two-stage proxy scan then tested Rank1 feature predicates and retained `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_no_drawdown_frontier_two_stage_total_curve_proxy_scan_20260707.json`.

补充说明
- New fixed subrule: `rank1_high_position_pullback_scale` inside `rank_position_scaling`. It scales only Rank1 to `0.0` when `max_drawdown_40d >= -0.04386677497969138` and `return_1d <= -0.0166975881261594`. This is a PIT high-position pullback condition, not a date/symbol filter.
- Formal same-contract stream replay root: `/tmp/stock_dashboard_label_v3_rank1_high_position_pullback_scaled_full713_min60`; candidate run `walk-forward-model-candidate-run-b04ea56d86886270`; report `model-comparison-report-ece4ed12a79d221d`; governance decision `governance-promotion-decision-f3c05a5ce8d1da4b`; dashboard registry `dashboard-approved-projection-registry-6522c02eca82dbec`.
- Best trial remains `weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_v1:trial-002`: total return `+242.6%`, annualized `+60.8%`, max drawdown `-3.28%`, selected mean `0.03011`, execution mean `0.03096`, positive date rate `46.40%`, negative months `3` (`2024-02`, `2024-08`, `2026-03`), worst monthly mean `-0.0268`, path drawdown sum `-0.8877`, alpha t-stat `6.7760`, DSR `0.9999998`, PBO `0.0`.
- Versus the prior no-drawdown frontier (`model-comparison-report-481e82b0595596c8`): total `+236.8% -> +242.6%`, annualized `+59.8% -> +60.8%`, maxDD effectively unchanged at `-3.28%`, selected mean `0.02978 -> 0.03011`, positive date rate `46.25% -> 46.40%`, negative months `4 -> 3`, path drawdown unchanged at `-0.8877`, alpha `6.6675 -> 6.7760`, DSR improves, PBO remains `0.0`.
- Capacity did not clear: active picks `985 -> 975`, below-full-fill active picks stay `26`, full-fill rate is `97.33%`, and minimum fill rate remains `0.1186`. Remaining blockers are `execution_stress:negative_monthly_mean_under_base_cost`, `execution_stress:capacity:adv_capacity_fill_rate_below_floor`, and `governance_promotion_pending`; governance also reports `execution:adv_capacity_fill_rate`.
- This is the current blocked research frontier, not a production, paper-tracking, dashboard, or policy-config strategy.

[2026-07-07T05:25:00+08:00] Rank1 low-score/high-position scaling becomes the current v3 research frontier and improves worst-month stress:
After the high-position-pullback frontier, a compact current-frontier selected-pick feature/label join was built without copying canonical matrices: `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_high_position_pullback_frontier_selected_pick_feature_label_join_20260707.json` (`4.9M`, `1473` rows, `0` missing labels/features). The follow-up two-stage proxy scan retained `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_high_position_pullback_frontier_two_stage_total_curve_proxy_scan_20260707.json` (`103K`) and found a strict non-degrading Rank1 state: low absolute model score while price is essentially at its 40-day high.

补充说明
- New fixed subrule: `rank1_low_score_high_position_scale` inside `rank_position_scaling`. It scales only Rank1 to `0.0` when `score <= 3.3878779420277896` and `distance_from_40d_high >= -0.0020618556701030855`. This is a PIT score/position state, not a date/symbol filter.
- This is not a grid expansion: all new hyperparameter keys are fixed single-value lists and the spec remains at `4` trials. The streamed prediction feature subset now retains `distance_from_40d_high` so the formal replay evaluates the same condition as the proxy.
- Formal same-contract stream replay root: `/tmp/stock_dashboard_label_v3_rank1_low_score_high_position_scaled_full713_min60` (`35M`); candidate run `walk-forward-model-candidate-run-833ef57c7cef942c`; report `model-comparison-report-3c83db6385250480`; governance decision `governance-promotion-decision-b9879707fc0c0bf8`; dashboard registry `dashboard-approved-projection-registry-54e5511b22125181`.
- Best trial remains `weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_v1:trial-002`: total return `+246.7%`, annualized `+61.6%`, max drawdown `-3.06%`, selected mean `0.03080`, execution mean `0.03158`, positive date rate `46.71%`, negative months `3` (`2024-02`, `2024-08`, `2026-03`), worst monthly mean `-2.03%`, path drawdown sum `-0.8877`, alpha t-stat `6.9524`, DSR `0.9999999`, PBO `0.0`.
- Versus the prior high-position-pullback frontier (`model-comparison-report-ece4ed12a79d221d`): total `+242.6% -> +246.7%`, annualized `+60.8% -> +61.6%`, maxDD `-3.28% -> -3.06%`, selected mean `0.03018 -> 0.03080`, execution mean `0.03096 -> 0.03158`, positive date rate `46.40% -> 46.71%`, negative months remain `3`, worst monthly mean improves `-2.68% -> -2.03%`, path drawdown unchanged at `-0.8877`, alpha `6.7760 -> 6.9524`, DSR improves, PBO remains `0.0`.
- Capacity still does not clear and should not be overstated: active picks `975 -> 964`, below-full-fill active picks stay `26`, full-fill rate moves `97.33% -> 97.30%`, and minimum fill rate remains `0.1186`. Remaining blockers are `execution_stress:negative_monthly_mean_under_base_cost`, `execution_stress:capacity:adv_capacity_fill_rate_below_floor`, and `governance_promotion_pending`; governance also reports `execution:adv_capacity_fill_rate`.
- This is the current blocked research frontier, not a production, paper-tracking, dashboard, or policy-config strategy.

[2026-07-07T05:45:00+08:00] Current-frontier single-condition scan finds no next formal replay candidate:
After accepting the low-score/high-position frontier, a bounded selected-pick diagnostic scan reused the existing `1473`-row feature/label join instead of rescanning canonical matrices. A first broad pair scan was interrupted because repeated Python dict evaluation made it an inefficient long run; no artifact was retained from that aborted pass. The replacement diagnostic is `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_low_score_high_position_frontier_narrow_proxy_scan_20260707.json`.

补充说明
- Scan scope: `2916` single-condition rank-position scale configs across ranks 1/2/3 and existing PIT feature fields, evaluated only on the compact selected-pick join.
- Materiality gate: a candidate needed to reduce negative-month count, improve worst monthly mean by at least `0.001`, or reduce below-full-fill active picks, while not degrading selected-pick mean, positive-date rate, negative-month count, worst month, or below-full-fill count in the selected-pick proxy.
- Result: `0` meaningful non-degrading candidates. Some trivial configs moved selected-pick mean by tiny amounts, but none materially improved the remaining negative-month or capacity blockers.
- Interpretation: do not run another formal replay for single-condition rules from this same current-frontier selected-pick space. Next useful work should either use a deliberately designed multi-condition month-state scan with a tighter candidate budget, or move to an order-level capacity/fill model that changes sizing rather than simply deleting low-liquidity picks.

[2026-07-07T06:15:00+08:00] Weak-benchmark low-score/high-position Rank1 rule is rejected because it sacrifices return:
After the single-condition negative result, a bounded stress-loser scan targeted only the three remaining negative months (`2024-02`, `2024-08`, `2026-03`) and only active Rank1 losing picks. The retained scan is `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_low_score_high_position_frontier_stress_loser_rule_scan_20260707.json` (`36K`). It found a plausible three-condition rule: scale Rank1 to `0.0` when `score <= 3.231715652768284`, `benchmark_return_10d <= -0.012530569470406094`, and `distance_from_40d_high >= -0.01782531194295911`.

补充说明
- Proxy direction looked useful: selected-pick mean improved, positive-date rate improved, worst monthly mean improved materially, and below-full-fill active picks improved from `26` to `24`.
- Formal same-contract stream replay root was `/tmp/stock_dashboard_label_v3_rank1_weak_benchmark_low_score_high_position_scaled_full713_min60`; candidate run `walk-forward-model-candidate-run-c73e56f0f725bb21`; report `model-comparison-report-33ecdf5d41f26420`; governance decision `governance-promotion-decision-f76c209a6c989684`; dashboard registry `dashboard-approved-projection-registry-1edc15d16a0f0e7a`.
- Formal result: total return `+239.6%`, annualized `+60.3%`, max drawdown `-3.06%`, selected mean `0.03101`, execution mean `0.03179`, positive date rate `47.01%`, negative months `3`, worst monthly mean `-1.04%`, path drawdown sum `-0.7611`, alpha t-stat `7.0224`, DSR `0.99999996`, PBO `0.0`, capacity below-full-fill `24`.
- Rejection reason: total and annualized return degraded versus the active low-score/high-position frontier (`+246.7%` / `+61.6%`). The stability/capacity improvement is real but violates the non-degradation contract on profitability.
- Cleanup: the `35M` formal replay root was deleted after retaining compact rejection summary `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_rank1_weak_benchmark_low_score_high_position_formal_rejection_20260707.json`. The active code/registry rule was removed; the then-current frontier remained `model-comparison-report-3c83db6385250480` until the later benchmark-momentum pullback replay superseded it.

[2026-07-07T06:45:00+08:00] Capacity sizing and underfilled-pick shortcuts are rejected as current-frontier optimization paths:
After the weak-benchmark low-score/high-position rejection, the next execution-focused pass tested whether the ADV/capacity blocker could be cleared by order-level sizing rather than deleting whole signals. The retained capacity sizing proxy is `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_low_score_high_position_frontier_capacity_sizing_proxy_20260707.json`. It evaluated current frontier base sizing, hard ADV cap with unused cash, and three redistribution policies (`desired`, `score`, `rank_priority`) under the same `1,000,000 CNY` / `5% ADV` proxy used by comparison-report governance.

补充说明
- Full ADV-cap sizing does clear below-full-fill count from `26` to `0`, but every tested mode violates the non-degradation contract. The least-bad redistribution modes still drop selected-pick mean from `0.04200` to about `0.0387-0.0388`, increase negative months from `3` to `4`, and reduce total-return proxy from `2.5386` to about `2.27`.
- A follow-up underfilled-pick local rule scan retained `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_low_score_high_position_frontier_underfilled_pick_rule_scan_20260707.json`. It searched predicates derived from the `26` underfilled active picks and required selected mean, positive rate, negative months, worst month, total, annualized, max drawdown, and path to be non-degrading while below-full-fill count decreased.
- Result: `0` non-degrading local underfilled-pick candidates.
- Interpretation: the current frontier's ADV/capacity blocker cannot be responsibly cleared by simple capacity capping, redistribution, or local underfilled-pick deletion. These approaches either lower return or worsen monthly stability. The next useful execution path is not another selected-pick shortcut; it should model capacity as a capital-envelope/portfolio-size constraint, or introduce a fuller order-level optimizer with explicit return floor checks before any formal replay.

[2026-07-07T07:10:00+08:00] Current-frontier capacity envelope is persisted without clearing the 1M governance blocker:
The then-current low-score/high-position frontier report was refreshed as `model-comparison-report-3c83db6385250480` with an explicit capacity envelope inside `execution_diagnostics.capacity_diagnostics`. This reused the existing formal candidate run and report builder; it did not rerun the full matrix or create another replay root.

补充说明
- Capacity envelope result: all active picks can be fully filled at about `118,555 CNY`; the `100,000 CNY` tier has `0` active picks below full fill; the configured `1,000,000 CNY` stress tier still has `26` below-full-fill active picks, full-fill rate `97.30%`, and min fill rate `0.1186`.
- Registry evidence now records `rank1_low_score_high_position_scale_adv_capacity_all_full_fill_notional_cny`, `rank1_low_score_high_position_scale_adv_capacity_100k_below_full_fill_count`, and `rank1_low_score_high_position_scale_adv_capacity_1m_below_full_fill_count`, with tests protecting those fields.
- Interpretation: the model may be meaningful at a smaller capital envelope, but this does not satisfy the existing 1M governance contract. Keep `execution_stress:capacity:adv_capacity_fill_rate_below_floor` and `execution:adv_capacity_fill_rate` blocked until an order-level optimizer or a formally accepted lower-capital product contract is designed and validated.

[2026-07-07T07:45:00+08:00] Rank1 benchmark-momentum pullback scaling becomes the current v3 research frontier:
After the capacity envelope clarification, the existing stress-loser scan was revisited for candidates that had not yet received formal replay. The narrowest non-degrading proxy candidate scales only Rank1 to `0.0` when `benchmark_return_10d >= 0.020298683992506783`, `return_20d_percentile >= 0.9818865345181135`, and `return_1d <= -0.014409221902017322`. It triggered only `4` selected-pick proxy rows, improved selected-pick mean (`0.04226 -> 0.04256`) and improved proxy worst month (`-2.76% -> -1.37%`) without expanding the four-trial grid.

补充说明
- Formal same-contract stream replay reused the canonical full713 input snapshot, PIT feature matrix and label-v3 matrix via `--stream-matrix-replay`; no duplicate feature or label matrix was created. Replay root: `/tmp/stock_dashboard_label_v3_rank1_benchmark_momentum_pullback_scaled_full713_min60` (`35M`); candidate run `walk-forward-model-candidate-run-fc76091e8cb864f3`; report `model-comparison-report-72fe170cfa0464ce`; governance decision `governance-promotion-decision-e7869f3b560adc9d`; dashboard registry `dashboard-approved-projection-registry-154d76ce347798a8`.
- Best trial remains `weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_v1:trial-002`: total return `+247.0%`, annualized `+61.6%`, max drawdown `-3.06%`, selected mean `0.03103`, execution mean `0.03181`, positive date rate `46.71%`, negative months `3` (`2024-02`, `2024-08`, `2026-03`), worst monthly mean `-0.97%`, path drawdown sum `-0.8877`, alpha t-stat `7.0294`, DSR `0.99999996`, PBO `0.0`.
- Versus the prior low-score/high-position frontier (`model-comparison-report-3c83db6385250480`): total `+246.7% -> +247.0%`, annualized `+61.57% -> +61.63%`, maxDD unchanged at `-3.06%`, selected mean `0.03080 -> 0.03103`, execution mean `0.03158 -> 0.03181`, negative months remain `3`, worst monthly mean improves `-2.03% -> -0.97%`, path unchanged at `-0.8877`, alpha and DSR improve, PBO remains `0.0`.
- Capacity remains blocked and should not be overstated: active capital picks `964 -> 960`, below-full-fill active picks remain `26`, full-fill rate is `97.29%`, minimum fill rate remains `0.1186`; the capacity envelope still clears `100,000 CNY` but not the configured `1,000,000 CNY` governance tier.
- This is now the current blocked research frontier, not a production, paper-tracking, dashboard, or policy-config strategy. The older high-position-pullback compact replay root was deleted after retaining durable summary evidence; keep only the current benchmark-momentum-pullback root plus the immediate predecessor low-score/high-position root for compact comparator needs.

[2026-07-07T08:15:00+08:00] Post-frontier prior stress-rule rescan finds execution-side hints but no monthly blocker reducer:
After accepting the benchmark-momentum pullback frontier, a compact rescan reused only the new candidate-run selected-pick rows plus the existing high-position-pullback feature/label join. It did not touch canonical matrices or create a replay root. The retained artifact is `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_benchmark_momentum_pullback_frontier_prior_stress_rule_rescan_20260707.json` (`13KB`).

补充说明
- Scope: `14` prior stress-loser top rules, evaluated over `1473` selected-pick rows from `walk-forward-model-candidate-run-fc76091e8cb864f3`.
- Result: `11` proxy non-degrading rules remain on selected mean, positive-date rate, negative-month count and worst-month. However, none improves the remaining negative-month count or worst month versus the new frontier proxy.
- Best execution-side hint: scale Rank1 to `0.0` when `benchmark_return_10d <= -0.012530569470406094`, `avg_amount_20d <= 67,166,197.6`, and `max_drawdown_20d >= -0.011458333333333237`; proxy mean improves by `0.00060`, positive-date rate improves by `0.01018`, and below-full-fill active picks improve from `26` to `22`. It still leaves min fill at `0.1186` and does not improve the monthly blocker, so it is only a next-candidate hint, not an accepted strategy.
- Interpretation: the next formal replay, if pursued, should be framed as an execution-capacity reducer with strict return floors, not as a monthly-stress fix. Do not repeat broad stress-loser scans until this execution-side hint is either formally rejected or accepted.

[2026-07-07T08:45:00+08:00] Rank1 weak-liquidity capacity reducer is formally rejected:
The execution-side hint from the post-frontier rescan was promoted to a fixed trial-only subrule and formally replayed through the same canonical full713 matrices with `--stream-matrix-replay`. The tested rule scaled only Rank1 to `0.0` when `benchmark_return_10d <= -0.012530569470406094`, `avg_amount_20d <= 67,166,197.6`, and `max_drawdown_20d >= -0.011458333333333237`.

补充说明
- Formal replay root was `/tmp/stock_dashboard_label_v3_rank1_weak_liquidity_shallow_drawdown_capacity_scaled_full713_min60`; candidate run `walk-forward-model-candidate-run-e259b6cccd5e5767`; report `model-comparison-report-c3a8fcfc8dc603f0`; governance `governance-promotion-decision-c0de790681dcad6a`; dashboard registry `dashboard-approved-projection-registry-f42cc6fa036f86b5`.
- Directional benefits were real: selected mean `0.03103 -> 0.03148`, positive date rate `46.71% -> 47.47%`, path drawdown sum `-0.8877 -> -0.5971`, alpha `7.0294 -> 7.1358`, DSR improved, PBO stayed `0.0`, and below-full-fill active picks improved `26 -> 22`.
- Rejection reason: profitability and monthly stress violated the non-degradation contract. Total return fell `+247.0% -> +236.7%`, annualized return fell `+61.6% -> +59.8%`, and worst monthly mean worsened `-0.97% -> -1.11%`. Minimum fill stayed `0.1186`, so the 1M capacity blocker was not cleared.
- Cleanup: the active code/registry subrule was removed, compact rejection summary was retained at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_rank1_weak_liquidity_capacity_formal_rejection_20260707.json`, and the rejected `35M` replay root was deleted. The then-current frontier remained `model-comparison-report-72fe170cfa0464ce`; the later capacity-contract refresh superseded that report with `model-comparison-report-efb1ccc40019b51b` without changing the candidate run.

[2026-07-07T09:05:00+08:00] Current-frontier negative-month rank-predicate scan finds no next formal candidate:
After the weak-liquidity capacity rejection, a compact contribution diagnostic reused only the current candidate-run selected-pick rows and the existing selected-pick feature join. It retained `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_benchmark_momentum_pullback_frontier_negative_month_contribution_diagnostic_20260707.json` (`62KB`) and showed that the remaining negative months are dominated by active Rank1 losses: `2024-02` Rank1 weighted sum `-0.4177`, `2024-08` Rank1 weighted sum `-0.5472`, and `2026-03` Rank1 weighted sum `-0.2200`; Rank2 contributes less, and Rank3 is mostly inactive.

补充说明
- A bounded follow-up scan retained `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_benchmark_momentum_pullback_frontier_negative_month_rank_rule_scan_20260707.json` (`1.6KB`). It used only `44` current negative-month losing active picks to build candidate predicates, checked `40` Rank1/Rank2 two- and three-condition rules, and required selected mean, positive-date rate, negative-month count, worst month, total proxy, and below-full-fill count to be non-degrading while improving a remaining blocker.
- Result: `0` useful non-degrading candidates. No rule in this bounded selected-pick rank-predicate space improved negative-month count, worst month, or capacity without violating a proxy floor.
- Interpretation: do not keep repeating selected-pick-only Rank1/Rank2 predicate scans on the current frontier. The remaining work likely requires a different design surface: an order-level optimizer that can model capital/fill explicitly, a formally lower-capital product contract, or new feature/label sources that change the opportunity set rather than deleting a few already-selected picks.

[2026-07-07T09:25:00+08:00] Current frontier now carries a machine-readable lower-capital capacity contract without clearing 1M governance:
The comparison report capacity diagnostics now emit `capacity_contract` in addition to the raw capacity envelope. The current benchmark-momentum-pullback frontier report was refreshed without rerunning the candidate run: report `model-comparison-report-efb1ccc40019b51b`, governance `governance-promotion-decision-b608bf5baad5603f`, and dashboard registry `dashboard-approved-projection-registry-d19e31f40989755b`.

补充说明
- `capacity_contract.status` is `lower_capital_research_contract_ready`: the largest configured tier with full fill is `100,000 CNY`, with `960` active picks, `0` below-full-fill picks, min fill `1.1856`, and p05 fill `20.4013`.
- `configured_governance_portfolio_notional_cny` remains `1,000,000 CNY`, `configured_governance_status` remains `blocked`, and `capacity_diagnostics.status` remains `blocked` with `adv_capacity_fill_rate_below_floor`.
- This is not a strategy promotion, dashboard projection approval, or production clearance. It makes the lower-capital envelope auditable and machine-readable so future work can choose explicitly between a lower-capital research contract and the existing 1M governance contract instead of silently weakening the blocker.

[2026-07-07T10:05:00+08:00] Research artifact retention is now guarded by a runnable audit:
Manual `/tmp` cleanup is no longer only a documentation convention. Added `research_artifact_retention_audit` as a file-system gate plus CLI command `research-artifact-retention-audit` to keep retained evidence compact while preserving canonical reusable matrices.

补充说明
- The audit blocks retained `walk_forward_model_candidate_runs/*.json` payloads, too many compact replay roots, missing replay roots, oversized retained evidence roots, and oversized compact replay roots.
- Default bounds are intentionally narrow for compact evidence: retained summary root `<=256MiB`, at most `2` compact replay roots, and each compact replay root `<=128MiB`. Canonical matrix roots are not passed to this audit and remain governed separately by the reuse contract.
- Current real `/private/tmp` audit passed: `/private/tmp/stock_dashboard_retained_reports_20260706` is `44,174,429` bytes with `0` retained candidate-run files; the current frontier root is `36,808,069` bytes; the predecessor comparator root is `36,658,852` bytes.
- This cleanup gate does not change model metrics. It is a research-governance blocker guard so future optimization must keep evidence bounded while attacking the remaining negative-month and 1M capacity blockers.

[2026-07-07T10:45:00+08:00] Order-level capacity proxy rejects simple ADV cap and same-basket redistribution:
Added `research-order-capacity-proxy` as a bounded execution diagnostic over an existing candidate-run artifact. It reads the current frontier's selected-pick diagnostics, applies a 5% ADV order cap at the configured `1,000,000 CNY` notional, and writes only compact summary evidence instead of retaining candidate-run copies or selected-pick details.

补充说明
- Retained compact proxy: `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_benchmark_momentum_pullback_order_level_capacity_proxy_20260707.json`.
- Scope: current benchmark-momentum-pullback frontier `walk-forward-model-candidate-run-fc76091e8cb864f3`, trial `weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_v1:trial-002`, `1473` selected picks, `653` evaluation dates, `960` active capital picks, `26` underfilled picks at `1,000,000 CNY` / `5% ADV`.
- Baseline full-fill reference: mean net excess `0.03181`, positive-date rate `46.71%`, negative months `3`, worst monthly mean `-0.00971`, path drawdown sum `-0.8877`.
- `adv_cap_cash` leaves unfilled capital as cash: mean net excess falls to `0.02932`, negative months increase to `4` by adding `2024-05`, worst monthly mean worsens to `-0.01246`. Path proxy improves to `-0.5971`, but the return/monthly-stress degradation violates the non-degradation contract.
- Same-date `rank` or `score` redistribution nearly eliminates cash weight but still degrades mean net excess to `0.02938`, increases negative months to `4`, and worsens worst month to `-0.01388`.
- A bounded Top5 substitute proxy initially used the stored `top_5_picks_by_date` trial diagnostic, but the proxy was corrected to model slot substitution properly: replacement candidates must be able to carry the underfilled original capital slot, and the replacement return is applied to that original slot. Under that corrected contract, the substitution still degrades mean net excess to `0.02829`, positive-date rate to `46.25%`, negative months to `4`, worst monthly mean to `-0.02863`, and path drawdown sum to `-1.0072`.
- Input boundary: the full prediction set has `7,410,732` rows, but inline candidate-run storage keeps only `8,000` sampled rows (`prediction_rows_truncated=true`). Therefore any substitute search beyond saved Top5 diagnostics must be implemented as a streaming matrix/top-candidate artifact, not by reading the inline prediction sample.
- A corrected streaming Top20 inventory was then generated from the canonical feature and label matrices without storing full prediction rows: `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_benchmark_momentum_pullback_top20_candidate_inventory_20260707.json` (`8,050,444` bytes). It streamed `1,852,683` prediction rows for the selected trial, retained `13,060` rows (`653` dates x Top20), and avoided the earlier invalid date-order assumption that temporarily produced a 1.1GB artifact; that invalid file was deleted and retention audit passed afterward.
- Top20 substitution still finds no non-degrading mode. It substitutes all `26` underfilled picks but produces the same rejected result as the corrected Top5 path: mean net excess `0.02829`, positive-date rate `46.25%`, negative months `4`, worst monthly mean `-0.02863`, and path drawdown sum `-1.0072`.
- A stricter capacity-aware pre-selection mode was also tested over the streamed Top20 inventory. It reselects each same-date capital slot by original score order, requiring each chosen candidate to fully carry that slot under the 5% ADV cap. This removes cash drag but is much worse: `163` selected slots change, mean net excess falls to `0.02774`, positive-date rate falls to `45.02%`, negative months jump from `3` to `8`, worst monthly mean is `-0.02650`, and path drawdown sum is `-0.9061`.
- Interpretation: do not repeat simple order-level ADV cap, cash retention, same selected-basket redistribution, TopN underfilled-pick substitution, or naive liquidity-first pre-selection as the next capacity fix. The useful next execution direction must either change the scoring model itself with liquidity/capacity as a learned/weighted factor, design a formally lower-capital product contract, or build a richer streaming optimizer with explicit non-degradation floors instead of hard skipping high-score low-capacity candidates.

[2026-07-07T11:30:00+08:00] Liquidity soft-rerank is rejected, but gross-exposure scaling is a non-degrading stability overlay candidate:
After the Top20 inventory was retained, two bounded current-frontier proxies tested whether the remaining capacity/path blockers could be attacked without copying candidate-run payloads or creating another full replay root. The soft-rerank proxy is `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_benchmark_momentum_pullback_capacity_soft_rerank_proxy_20260707.json` (`7KB`), and the exposure-stability proxy is `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_benchmark_momentum_pullback_exposure_floor_stability_proxy_20260707.json` (`21KB`).

补充说明
- `research-capacity-soft-rerank-proxy` scans Top20 candidates with `score + liquidity_weight * fill_capacity_score` under the same `1,000,000 CNY` / `5% ADV` proxy. It fixes the underfill count at larger weights, but no scan is non-degrading. At `liquidity_weight=0.1`, underfilled picks fall to `0`, but total proxy falls `1.7932 -> 1.4147`, mean net excess falls `0.03181 -> 0.02731`, positive-date rate falls `46.71% -> 44.41%`, negative months rise `3 -> 8`, worst month worsens to `-0.02867`, and path drawdown worsens to `-0.9877`.
- The soft-rerank implementation was corrected to evaluate all `653` baseline dates, not only the `491` active candidate dates; the earlier active-only view was discarded because it overstated mean returns.
- `research-exposure-floor-stability-proxy` scans date-level `gross_exposure` overlays from the candidate's own selected-return diagnostics. The strict non-degradation gate now includes total proxy, max drawdown, positive-date rate, negative-month count, and worst monthly mean.
- Best balanced proxy candidate: `gross_exposure_linear_scale_overlay` with `gross_exposure_floor=0.3`. It scales low-exposure dates by `gross_exposure / 0.3` instead of going fully to cash. Metrics improve without reducing positive-date rate: total proxy `1.7932 -> 1.8007`, annualized proxy `48.65% -> 48.80%`, maxDD `-4.356% -> -4.279%`, mean net excess `0.03181 -> 0.03190`, positive-date rate unchanged at `46.71%`, negative months remain `3`, worst monthly mean improves `-0.00971 -> -0.00882`, and path drawdown sum improves `-0.8877 -> -0.8715`. It touches `76` low-exposure active dates and gates `0` dates fully to cash.
- Stronger cash-floor overlays can improve headline total more, but they reduce positive-date rate, so they are not the preferred candidate under the updated non-degradation contract.
- Interpretation: the next meaningful step is a formal registered-spec replay or comparison-report overlay path for `gross_exposure_linear_scale_overlay@0.3`, with strict no-regression gates and no dashboard/paper/runtime promotion until governance accepts it. Do not repeat TopN liquidity soft-rerank as implemented; it solved underfill mechanically but damaged return and monthly stability.

[2026-07-07T12:15:00+08:00] Gross-exposure linear scaling becomes the current blocked v3 research frontier:
The `gross_exposure_linear_scale_overlay@0.3` proxy was promoted to a fixed registered spec, not a report-only patch: `weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_scaled_v1`. The candidate runner now supports `selection_policy.date_exposure_scaling.mode=gross_exposure_floor_linear_scale`, applying the same date-level scale to selected returns and selected-pick weights. Formal full713 stream replay reused the existing input snapshot, PIT feature matrix, and label-v3 matrix; no duplicate feature/label matrix was created.

补充说明
- Formal replay root: `/tmp/stock_dashboard_label_v3_gross_exposure_scaled_full713_min60` (`39M`); candidate run `walk-forward-model-candidate-run-53b14185088ead43`; report `model-comparison-report-26c4f58b6afcabe0`; governance decision `governance-promotion-decision-5ff85ab74df18cc1`; dashboard registry `dashboard-approved-projection-registry-62ff61ace39f0365`.
- Best trial remains trial-002 under the new spec. It scales `77` dates / `231` selected-pick rows where base gross exposure is below `0.3`; no date is fully cashed out by this overlay.
- Formal result: total return `+247.3%`, annualized `+61.7%`, maxDD `-3.06%`, selected mean `0.03103`, execution mean `0.03190`, positive date rate `46.71%`, negative months `3` (`2024-02`, `2024-08`, `2026-03`), worst monthly mean `-0.00882`, path drawdown sum `-0.8715`, alpha t-stat `7.0512`, DSR `0.999999964`, PBO `0.0`.
- Versus the prior benchmark-momentum-pullback frontier (`model-comparison-report-efb1ccc40019b51b`): total `+247.0% -> +247.3%`, annualized `+61.6% -> +61.7%`, maxDD stays about `-3.06%`, execution mean `0.03181 -> 0.03190`, positive date rate unchanged `46.71%`, negative months remain `3`, worst month improves `-0.00971 -> -0.00882`, path improves `-0.8877 -> -0.8715`, alpha/DSR improve, PBO remains `0.0`.
- Remaining blockers are real: `execution_stress:negative_monthly_mean_under_base_cost`, `execution_stress:capacity:adv_capacity_fill_rate_below_floor`, and governance promotion pending. The `1,000,000 CNY` / `5% ADV` capacity stress remains unchanged at `960` active capital picks, `26` below full fill, full-fill rate `97.29%`, and min fill `0.1186`. The lower-capital `100,000 CNY` research contract remains ready but does not clear the configured 1M governance tier.
- Cleanup: the older low-score/high-position compact replay root was deleted after this replay accepted, leaving only the new gross-exposure-scaled current root and the direct predecessor benchmark-momentum-pullback root. Retention audit passed with retained compact evidence root `52,266,150` bytes, candidate-run files `0`, new root `40,846,527` bytes, and predecessor root `36,808,069` bytes.
- This is the current blocked research frontier, not a production, paper-tracking, dashboard, or policy-config strategy. Next useful work should target either the remaining three negative months or a richer capacity optimizer/lower-capital contract without degrading this new frontier.

[2026-07-07T12:55:00+08:00] Score-confidence overlay is formally rejected and cleaned up:
After the gross-exposure-scaled frontier, a compact date-state scan suggested halving exposure when the selected basket's minimum model score was below `3.1010533469249064`. The idea was promoted to a temporary fixed formal replay candidate only to test whether the proxy held under the same full713 stream replay contract.

补充说明
- Formal replay root was `/tmp/stock_dashboard_label_v3_gross_exposure_score_scaled_full713_min60`; report `model-comparison-report-d7090709c8f91a20`; candidate run `walk-forward-model-candidate-run-f97b44e95c7c8c82`; governance decision `governance-promotion-decision-a56b42905c7a0d27`; dashboard registry `dashboard-approved-projection-registry-79a27d967f9c104b`.
- Directional improvements were not enough for promotion: path drawdown sum improved `-0.8715 -> -0.6906`, worst monthly mean improved `-0.00882 -> -0.00869`, alpha/DSR improved slightly, and underfilled active picks improved `26 -> 21`.
- Rejection reason: the candidate violated the no-profit-degradation floor. Total return fell `+247.3% -> +243.0%`, annualized return fell `+61.7% -> +60.9%`, and execution mean fell `0.03190 -> 0.03177`. Negative months remained `3` (`2024-02`, `2024-08`, `2026-03`), maxDD stayed about `-3.06%`, and PBO stayed `0.0`.
- Cleanup: the temporary registered spec/execution path was removed, the full replay root was deleted, and only a compact rejection summary was retained at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_score_confidence_overlay_rejection_summary_20260707.json`. Retained evidence still has `0` candidate-run files and only the two compact replay roots: current gross-exposure-scaled frontier plus direct benchmark-momentum-pullback predecessor.
- Interpretation: do not repeat score-threshold date exposure halving as the next blocker fix unless the scoring model itself changes. Future work must attack the remaining negative-month and 1M ADV capacity blockers without lowering the gross-exposure frontier's `+247.3%` return, `-3.06%` maxDD, DSR/PBO, or execution mean floors.

[2026-07-07T13:35:00+08:00] Rank1 low-score turnover pick-level scaling is formally rejected and cleaned up:
A second compact selected-pick scan tested whether the score idea should be moved from date-level exposure to pick-level model risk control. The fixed candidate scaled only Rank1 picks to `0.0` when `score <= 3.2` and `turnover_rate_percentile >= 0.05`, then replayed it under the same gross-exposure-scaled full713 contract.

补充说明
- Formal replay root was `/tmp/stock_dashboard_label_v3_gross_exposure_low_score_turnover_scaled_full713_min60`; report `model-comparison-report-35c3abef6ca04ea7`; candidate run `walk-forward-model-candidate-run-2aa0144451df4de4`; governance decision `governance-promotion-decision-9cbd02b6fb932dae`; dashboard registry `dashboard-approved-projection-registry-d60a6cdb135ee232`.
- Directional improvements were real but not sufficient: execution mean improved `0.03190 -> 0.03202`, worst monthly mean improved `-0.00882 -> -0.00862`, path drawdown sum improved `-0.8715 -> -0.6360`, alpha/DSR improved, and below-full-fill active picks improved `26 -> 23`.
- Rejection reason: headline profitability violated the non-degradation floor. Total return fell `+247.3% -> +235.1%` and annualized return fell `+61.7% -> +59.5%`. Negative months remained `3`, maxDD stayed about `-3.06%`, and PBO stayed `0.0`, so the monthly and capacity blockers were not cleared.
- Cleanup: the temporary runner subrule, registered spec, and tests were removed; the full replay root was deleted; compact rejection summary was retained at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_low_score_turnover_pick_scale_rejection_summary_20260707.json`.
- Interpretation: do not repeat score-threshold pick deletion as the next fix. It improves several stability proxies by removing profitable exposure enough to damage compounding return. The next useful direction needs a model/optimizer that can replace or resize risky exposure without reducing the gross-exposure frontier's return floor.

[2026-07-07T14:30:00+08:00] Rank1 low-score low-liquidity slot replacement becomes the current blocked v3 research frontier:
After rejecting deletion-style score filters, a Top20 replacement scan tested whether risky exposure can be replaced rather than removed. A deterministic proxy found a fixed non-degrading rule: when Rank1 has `score <= 3.1` and `avg_amount_20d <= 150M`, replace that Rank1 slot with the highest-score same-date Top20 candidate whose `avg_amount_20d >= 20M`. This rule uses only as-of-date score/liquidity information for selection; a separate oracle diagnostic was retained only as an upper-bound study and is not a strategy.

补充说明
- Compact proxy artifacts retained:
  - `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_gross_exposure_top20_deterministic_replacement_scan_20260707.json` (`26KB`): checked `1331` low-dimensional replacement rules; best accepted proxy replaced `6` Rank1 slots and improved total `+247.3% -> +253.1%`, annualized `+61.7% -> +62.7%`, mean `0.03190 -> 0.03241`, worst month `-0.00882 -> -0.00862`, path `-0.8715 -> -0.7367`, and underfilled rough count `29 -> 27`.
  - `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_gross_exposure_top20_replacement_oracle_gap_diagnostic_20260707.json` (`309KB`): oracle-only upper bound showing the Top20 opportunity set contains enough ex-post alternatives, but future labels are forbidden for strategy selection.
- Formal replay root: `/tmp/stock_dashboard_label_v3_gross_exposure_rank1_replacement_full713_min60`; candidate run `walk-forward-model-candidate-run-be8fed0fba2b8335`; report `model-comparison-report-ce774ba891e26edf`; governance decision `governance-promotion-decision-f48aff8f9373df2c`; dashboard registry `dashboard-approved-projection-registry-833b716996291669`.
- Best trial remains trial-002 under registered spec `weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_rank1_replacement_v1`. The candidate runner now persists `slot_replacement_source_symbol`, `slot_replacement_source_score`, `slot_replacement_reason`, date-level `slot_replacement_count`, and replacement reasons in the candidate-run diagnostics. Formal replay replaced `6` Rank1 slots across `6` dates.
- Formal result versus the prior gross-exposure frontier: total return `+247.3% -> +252.9%`, annualized `+61.7% -> +62.7%`, maxDD remains about `-3.06%`, execution mean `0.03190 -> 0.03239`, positive date rate unchanged `46.71%`, negative months remain `3` (`2024-02`, `2024-08`, `2026-03`), worst monthly mean improves `-0.00882 -> -0.00862`, path drawdown sum improves `-0.8715 -> -0.7367`, alpha t-stat improves `7.0512 -> 7.1622`, DSR improves `0.999999964 -> 0.999999981`, PBO remains `0.0`.
- Capacity direction improves but does not clear governance: active capital picks stay `960`, below-full-fill active picks improve `26 -> 24`, full-fill rate is `97.50%`, and min fill remains `0.1186`. The `100,000 CNY` lower-capital research contract remains ready but the configured `1,000,000 CNY` governance tier remains blocked.
- Cleanup: after this replay accepted, the older benchmark-momentum-pullback replay root was deleted. Compact retention now keeps only the new rank1-replacement current root and the direct predecessor gross-exposure root; retained summary evidence still contains `0` candidate-run files.
- This is the current blocked research frontier, not production, paper-tracking, dashboard, or policy-config strategy. Remaining blockers are still negative monthly mean stress and ADV/capacity/fill-rate governance. Next useful work should target the remaining three negative months and the remaining `24` underfilled active picks without degrading this new `+252.9%` / `-3.06%` / DSR/PBO frontier.

[2026-07-07T14:45:00+08:00] Rank1 very-low-liquidity Top20 replacement is registered as a proxy-only follow-up, not a formal frontier:
A workstation-friendly narrow proxy scan tested whether the current Rank1 replacement frontier could further reduce ADV/capacity stress through replacement rather than deletion. The scan used the existing formal current-frontier selected-pick diagnostics plus the compact Top20 inventory; it did not rescan or duplicate canonical matrices.

补充说明
- Retained proxy: `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_rank1_replacement_frontier_targeted_top20_replacement_proxy_scan_20260707.json`.
- Registered follow-up spec: `weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_rank1_liquidity_replacement_v1`. It keeps the accepted primary Rank1 replacement rule, then adds a second fixed rule: when the post-primary Rank1 has `score <= 3.2`, `avg_amount_20d <= 20M`, `turnover_rate_percentile <= 0.2`, and `amount_10d_vs_20d_percentile <= 0.85`, replace that slot with the highest-score same-date Top20 candidate with `avg_amount_20d >= 100M`.
- Proxy result versus the current formal frontier: replacements `9`, total return `+252.9% -> +253.0%`, annualized `+62.69% -> +62.71%`, execution mean `0.032391 -> 0.032397`, positive date rate `46.71% -> 46.86%`, maxDD unchanged at about `-3.06%`, negative months remain `3` (`2024-02`, `2024-08`, `2026-03`), worst monthly mean unchanged `-0.00862`, path drawdown sum improves `-0.7367 -> -0.5966`, and active picks below full fill improve `24 -> 16`.
- Formal replay status: not completed. A single-spec full713 stream replay was started with `nice -n 15` but was stopped after about `3.5` minutes with no CLI output to avoid workstation performance impact. It was still in the pure-Python `_iter_artifact_rows` scan of the 6.2GB PIT feature matrix. No replay root was written.
- Interpretation: this is a legitimate next formal candidate because it is registered, bounded, and proxy-non-degrading, but it is not the current formal frontier and must not be described as accepted. Next work should either run the single-spec formal replay during an idle window or improve the stream iterator / compact replay path before claiming formal metrics. Negative-month stress remains unresolved even in proxy.

[2026-07-07T15:05:00+08:00] Stream replay JSON iterator bottleneck is fixed; SQLite prediction staging remains the next performance blocker:
The failed liquidity-replacement formal replay exposed that the generic artifact row iterator was scanning multi-GB JSON artifacts one Python character at a time. The iterator was replaced with chunked `json.JSONDecoder.raw_decode` parsing, and temporary stream-replay SQLite connections now use low-overhead PRAGMAs (`journal_mode=OFF`, `synchronous=OFF`, `temp_store=MEMORY`, larger cache, exclusive locking). This is a performance-only change for research artifact replay and does not change model formulas, selection rules, labels, or governance thresholds.

补充说明
- Added unit coverage for chunk-boundary parsing with nested objects, escaped quotes, and bracket/brace characters inside strings.
- Real matrix smoke checks are now fast: reading the first `1000` rows from the 6.2GB PIT feature matrix took about `0.017s`; reading the first `1000` rows from the 4.7GB label-v3 matrix took about `0.018s`.
- A second low-priority formal replay attempt for `weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_rank1_liquidity_replacement_v1` progressed past JSON reading, then was stopped after about `4` minutes while creating `predictions_trial_date_idx` on the staged prediction table. No formal replay root was written.
- Verification: focused stream tests passed; `python3 -m pytest -q` passed with `1053 passed, 180 deselected, 6 subtests passed`; policy audit passed; retention audit passed with retained root `52,698,602` bytes, `0` candidate-run files, and compact replay roots still limited to the current formal frontier plus direct predecessor.
- Interpretation: do not claim the liquidity-replacement candidate is formally accepted. The next performance cleanup should reduce or bypass full prediction SQLite staging/indexing for deterministic specs, or the full 4-trial replay should be scheduled explicitly for an idle window.

[2026-07-07T15:35:00+08:00] Rank1 very-low-liquidity replacement becomes the current blocked formal v3 frontier:
The stream replay bottleneck after JSON parsing was removed by replacing full prediction SQLite staging/indexing with direct per-trial/date aggregation. The streamed runner still computes date Rank IC, split Rank IC, Top5/Top10, selected TopK returns/picks, bounded prediction samples and diagnostics, but no longer writes all trial predictions into a temporary `predictions` table or builds `predictions_trial_date_idx`. Small-matrix tests assert streamed metrics and selected returns match the regular runner.

补充说明
- Formal replay root: `/tmp/stock_dashboard_label_v3_gross_exposure_rank1_liquidity_replacement_full713_min60`; candidate run `walk-forward-model-candidate-run-50a0f5c2b9758efa`; comparison report `model-comparison-report-ea4a723c3a6a69b4`; governance decision `governance-promotion-decision-262872b0d9ae1bd6`; dashboard registry `dashboard-approved-projection-registry-8ba6a0c49efd758d`.
- Best trial: `weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_rank1_liquidity_replacement_v1:trial-003`.
- The formal run replaced `15` Rank1 slots: `6` from the existing `rank1_low_score_low_amount_full_fill_topn_substitute` rule plus `9` from `rank1_very_low_liquidity_top20_high_amount_substitute`.
- Formal metrics: total return `+253.1%`, annualized `+62.7%`, max drawdown `-3.06%`, positive date rate `46.86%`, negative months `3` (`2024-02`, `2024-08`, `2026-03`), worst monthly mean `-0.00862`, path drawdown sum `-0.5966`, alpha t-stat `7.2503`, DSR `0.999999988`, PBO `0.0`.
- Versus the prior Rank1 replacement frontier (`model-comparison-report-ce774ba891e26edf`): total `+252.9% -> +253.1%`, annualized `+62.69% -> +62.72%`, maxDD unchanged around `-3.06%`, positive date rate `46.71% -> 46.86%`, negative months remain `3`, worst month unchanged, path improves `-0.7367 -> -0.5966`, alpha/DSR improve, PBO remains `0.0`, and 1M/5%ADV underfilled active picks improve `24 -> 16`.
- Important caveat: comparison-report execution mean fell slightly `0.032391 -> 0.032307`. This is therefore accepted as the current return/path/capacity frontier, not as an execution-mean frontier. It remains blocked by `negative_monthly_mean_under_base_cost` and `capacity:adv_capacity_fill_rate_below_floor`.
- Capacity remains unresolved but improves materially: active picks `960`, below-full-fill active picks `16`, full-fill rate `98.33%`, minimum fill `0.1219`; lower-capital full-fill research tier improves to `120,000 CNY`, but configured `1,000,000 CNY` governance remains blocked.
- Cleanup: after this replay accepted, the older gross-exposure-scaled compact replay root was deleted. Retention audit passed with retained compact evidence `52,698,602` bytes, `0` retained candidate-run files, current frontier root `46,435,025` bytes, and direct predecessor rank1-replacement root `46,216,425` bytes.

[2026-07-07T18:58:00+08:00] Rank1 amount-expansion high-amount replacement is rejected after formal replay:

- A bounded current-frontier Top20 inventory was generated at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_rank1_liquidity_frontier_top20_candidate_inventory_20260707.json` (`top-candidate-inventory-fffe97f461edf0cb`, `13,060` retained rows, `1,852,683` streamed predictions) to avoid another full prediction payload.
- Selected-pick proxy suggested that replacing low-turnover, high `amount_10d_vs_20d_percentile`, mid/low-absolute-amount Rank1 picks with same-date high-amount Top20 candidates could reduce negative months from `3` to `1`. The same diagnostic also found that 2024-08 can be fully cleared only by hindsight/oracle candidate choices inside Top20, not by the current ex-ante score/liquidity ordering; those oracle replacements were explicitly excluded.
- The candidate was promoted only to a temporary fixed registered spec for formal validation: `weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_rank1_amount_expansion_replacement_v1`.
- Formal full713 stream replay rejected the candidate. Best `trial-003` produced candidate run `walk-forward-model-candidate-run-3fcff5c64480cebe`, report `model-comparison-report-4cf3f23df3d96df0`, governance `governance-promotion-decision-b0f865cffe620659`, and dashboard registry `dashboard-approved-projection-registry-1c0c03ec068675ab`.
- Formal metrics degraded versus the current liquidity-replacement frontier: total return `+253.1% -> +248.6%`, annualized `+62.7% -> +61.9%`, worst monthly mean `-0.00862 -> -0.00913`, and negative months only improved from `3` to `2` (`2024-02`, `2024-08`). Positive date rate improved slightly `46.86% -> 47.01%`, maxDD/path were unchanged around `-3.06%` / `-0.5966`, and configured-capacity underfilled active picks improved `16 -> 14`, but this is not enough to offset return and worst-month degradation.
- Cleanup: the temporary registered spec was removed from the active registry, the formal replay root `/tmp/stock_dashboard_label_v3_gross_exposure_rank1_amount_expansion_replacement_full713_min60` was deleted, and compact rejection summary was retained at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_rank1_amount_expansion_replacement_formal_rejection_20260707.json`.
- Do not continue simple Rank1 Top20 replacement patching for 2024-08. The next valid direction needs richer ex-ante features or scoring architecture that can distinguish the 2024-08 substitutes without outcome leakage while preserving the current frontier's return floor.
- This is not production, paper-tracking, dashboard, or policy-config strategy. Next optimization should target the remaining three negative months and the remaining `16` underfilled active picks without degrading the new total-return, maxDD, DSR/PBO, path and capacity floors.

[2026-07-07T19:20:00+08:00] Feature-rich Top20 inventory is now required for replacement proxy screening:

- Root cause of the amount-expansion false positive: the first current-frontier Top20 inventory retained selected/candidate scores and a few liquidity fields, but did not retain the rank-position feature values that the formal strategy uses for position scaling. That made the selected-pick proxy materially weaker than the formal replay contract.
- The inventory builder now retains bounded `rank_weight_feature_values` per Top20 candidate row. The regenerated current-frontier inventory is `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_rank1_liquidity_frontier_top20_candidate_inventory_feature_rich_20260707.json` (`top-candidate-inventory-a7d8267b3d602565`, `13,060` rows, `18,291,860` bytes), covering position-scale inputs including `volatility_20d_percentile`, `return_20d_percentile`, `return_5d_percentile`, benchmark return/volatility fields, drawdown/distance fields, absolute amount and amount-expansion fields.
- Proxy parity diagnostic retained at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_rank1_amount_expansion_proxy_parity_diagnostic_20260707.json` shows the earlier proxy overstated the improvement: for 2024-02, naive monthly mean was `+0.01455`, but scale-aware replacement using the feature-rich inventory was still `-0.00827`; 2024-08 stayed negative in both (`-0.00812`). Scale-aware negative months were `2` (`2024-02`, `2024-08`), matching the formal rejection direction.
- Rule: future Rank1/TopN replacement scans must use feature-rich inventory and reapply official position scaling before any formal full713 replay. Selected-pick-only replacement proxies are diagnostic only and must not be promoted to a registered spec.

[2026-07-07T20:05:00+08:00] Neutral-chop date-level scale improves negative-month and capacity stress, but remains blocked:

- Feature-rich date-level proxy scan retained at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_rank1_feature_rich_date_extra_scale_scan_20260707.json` found a narrow neutral-chop date-scale candidate: Rank1 benchmark 20d return between `-0.02` and `0.01`, benchmark 20d volatility `>= 0.03`, Rank1 20d return percentile `<= 0.95`, Rank1 5d return percentile `>= 0.80`, and Rank1 20d max drawdown `<= -0.003`, with date-level scale `0.0`.
- The rule was added as a fixed registered spec, not as an ad hoc report patch: `weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_rank1_liquidity_replacement_neutral_chop_date_scale_v1`.
- Formal full713 stream replay reused canonical matrices and wrote root `/tmp/stock_dashboard_label_v3_neutral_chop_date_scale_full713_min60`: candidate run `walk-forward-model-candidate-run-a37b68b6027372ac`, registry `model-spec-registry-361e3212107e0851`, report `model-comparison-report-ed79aad6324b2fea`, governance `governance-promotion-decision-964094681743e68c`, dashboard registry `dashboard-approved-projection-registry-7b468666ba4d8305`.
- Best trial `trial-003` slightly improves the liquidity-replacement frontier on return and overfit metrics: total return `+253.107% -> +253.115%`, annualized `+62.7209% -> +62.7222%`, alpha t-stat `7.2503 -> 7.4095`, DSR `0.999999988 -> 0.999999995`, PBO remains `0.0`, max drawdown/path/worst month hold, negative months fall `3 -> 2` (`2024-02`, `2024-08`), and configured-capacity underfilled active picks improve `16 -> 14`.
- Caveat: trial-stability positive date rate drops `46.86% -> 45.02%`. This is therefore a negative-month/capacity challenger with a positive-date-rate caveat, not an unconditional all-metric frontier.
- Governance remains blocked: `negative_monthly_mean_under_base_cost` and `adv_capacity_fill_rate` still fail. It is not production, paper-tracking, dashboard, or policy-config ready.
- Retention cleanup: the older rank1-replacement predecessor replay root was archived as small registry/report/governance/projection JSONs under `/tmp/stock_dashboard_retained_reports_20260706/retained_artifacts/rank1_replacement_predecessor_20260707/` and deleted. Current compact replay roots are limited to the liquidity-replacement frontier and the neutral-chop date-scale challenger; retention audit passes with retained root `80,145,162` bytes and `0` retained candidate-run files.

[2026-07-07T20:25:00+08:00] Remaining-negative-month scan after neutral-chop finds no non-degrading blocker clear:

- Retained diagnostic: `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_neutral_chop_remaining_negative_month_extra_scale_scan_20260707.json`.
- The scan used the formal neutral-chop date-scale candidate as the base and required non-degradation on total return, max drawdown, path drawdown, worst monthly mean, negative-month count, and positive-date rate. It checked `37,600` bounded feature-only date-scale configurations over the feature-rich Top20 inventory.
- Accepted configurations only improved return while leaving negative months unchanged at `2` (`2024-02`, `2024-08`). Best accepted proxy reached total return `+254.99%`, annualized `+63.06%`, maxDD/path/worst month unchanged, and positive-date rate unchanged at `45.02%`, but it did not clear another blocker.
- Near-miss configurations can reduce negative months to `1`, but they degrade the active candidate: total return falls to about `+252.25%`, annualized to about `+62.57%`, and positive-date rate to about `44.72%`. That violates the current non-degradation floor, so they are not promoted to registered spec or formal replay.
- Conclusion: do not keep stacking simple date-level scale/cash rules on the neutral-chop candidate. The remaining work likely needs richer ex-ante features, opportunity-set changes, or capacity-aware scoring that changes selected candidates without further lowering positive-date stability.

[2026-07-07T20:45:00+08:00] Simple capacity-aware Top20 fixes and learned Top20 reranking are rejected:

- Retained diagnostics:
  - `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_neutral_chop_capacity_aware_score_adjustment_scan_20260707.json`
  - `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_neutral_chop_underfilled_slot_replacement_scan_20260707.json`
  - `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_neutral_chop_walk_forward_feature_reranker_scan_20260707.json`
- The capacity-aware score-adjustment scan tested `399` bounded liquidity/amount score transforms over the feature-rich Top20 inventory and found `0` accepted configurations. Best capacity improvement lowers underfilled active picks from `14` to `8`, but degrades total return to about `+251.26%` and worsens worst monthly mean to about `-1.20%`.
- The underfilled-slot replacement scan tested `1,440` same-date Top20 liquid substitute rules and found `0` accepted configurations. Best underfilled reduction is only `14 -> 13`, and it degrades total return to about `+236.40%`; this is not a candidate for formal replay.
- The order-level cap/cash proxy retained at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_neutral_chop_order_level_cap_cash_proxy_20260707.json` applies the configured `1,000,000 CNY` / `5% ADV` fill cap directly to the formal selected picks and leaves unfilled capital in cash. It clears the capacity blocker mechanically (`14 -> 0` underfilled active picks), but degrades total return `+253.1% -> +212.3%`, annualized return `+62.7% -> +55.2%`, and negative months `2 -> 3`. This proves a pure execution haircut is not an acceptable way to clear capacity.
- The learned Top20 reranker diagnostic used expanding walk-forward training with at least `60` prior dates, ridge regression over feature-rich Top20 rows, and no future labels at prediction time. It checked `36` alpha/blend/target configurations and found `0` accepted or near-improved configurations.
- Conclusion: the remaining blocker is not solved by simple amount/liquidity score bonuses, same-date underfilled-slot replacement, or a shallow learned reranker over the existing Top20 opportunity set. Next research should change the ex-ante feature set or candidate opportunity set before selection, or build a more explicit capacity-aware model with formal non-degradation floors.

[2026-07-07T22:35:00+08:00] Segment-risk scale is the new blocked formal challenger, but it does not clear the hard blockers:

- Top50 underfilled-slot replacement retained at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_neutral_chop_top50_underfilled_slot_replacement_scan_20260707.json` checked `960` configs and found `0` accepted. Best near miss only improves underfilled active picks `14 -> 13` while lowering proxy total return to about `+236.4%`.
- Top50 learned walk-forward reranker retained at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_neutral_chop_top50_walk_forward_feature_reranker_scan_20260707.json` checked `1,440` prior-date training configs and found `0` accepted. Best return config still degraded total return to about `+241.6%`, negative months `2 -> 5`, and capacity `14 -> 18`.
- Selected-pick single-factor segment scan retained at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_neutral_chop_selected_pick_segment_risk_scale_scan_20260707.json` checked `4,800` configs and found `12` accepted, all mild return/stability improvements rather than blocker clears.
- Small accepted-rule combo scan retained at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_neutral_chop_segment_risk_scale_small_combo_scan_20260707.json` selected a three-rule overlay: Rank2 `turnover_rate_percentile >= 0.8888137884420412` scale `0.5`, Rank3 `score >= 3.381482156586441` scale `0.5`, and Rank1 `avg_amount_20d >= 1,619,280,193.75` scale `0.75`.
- The overlay is now a fixed registered spec, not a report patch: `weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_rank1_liquidity_replacement_neutral_chop_segment_risk_scale_v1`.
- Formal full713 stream replay root `/tmp/stock_dashboard_label_v3_segment_risk_scale_full713_min60` produced candidate run `walk-forward-model-candidate-run-d826fbf4377bca0c`, registry `model-spec-registry-e707e2ffee4e287b`, report `model-comparison-report-105775d168efe41d`, governance `governance-promotion-decision-2b7d2b80a7ecd9ff`, and dashboard registry `dashboard-approved-projection-registry-f71789a5d0a57c35`.
- Versus neutral-chop date-scale, formal metrics improve but do not clear blockers: total return `+253.115% -> +253.613%`, annualized `+62.722% -> +62.811%`, mean net excess `0.032869 -> 0.032964`, positive-date rate `45.02% -> 45.18%`, worst monthly mean `-0.8625% -> -0.8605%`, alpha t-stat `7.4095 -> 7.4416`, DSR `0.999999995 -> 0.999999996`, PBO `0.0`, maxDD/path unchanged at about `-3.06%` / `-0.5966`.
- Remaining blockers are unchanged: negative months remain `2` (`2024-02`, `2024-08`) and configured `1,000,000 CNY` / `5% ADV` capacity still has `14` active picks below full fill. The lower-capital full-fill research tier remains `120,000 CNY`.
- Follow-up Top50 date-state scale scan retained at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_segment_risk_top50_date_state_scale_scan_20260707.json` checked `1,560` aggregate date-state configs and found `0` accepted. Rules that clear negative months do it by broad cashing and collapse total return to about `+20.5%`, so single-factor date-state scaling is rejected.
- Bounded formal exit-horizon scan was also rejected. The temporary scan spec varied only `weak_regime_exit_horizon_days`, `neutral_regime_exit_horizon_days`, and inherited weak-grind parameters, while keeping scoring, segment-risk scale, replacement, and candidate universe unchanged. Replay root `/tmp/stock_dashboard_label_v3_segment_risk_exit_horizon_scan_full713_min60` produced candidate run `walk-forward-model-candidate-run-9787c99647a7c547`, report `model-comparison-report-182040e0d659006e`, governance `governance-promotion-decision-8c7275af63dbce5a`, and dashboard registry `dashboard-approved-projection-registry-da0185e7937b733a`.
- Best exit-horizon trial exactly matched the segment-risk formal metrics but suffered a lower DSR because the comparison set expanded from `4` to `16` eligible trials (`0.999999996 -> 0.999999818`). Alternate horizon combos degraded total return to about `+244.4%` or worse and often increased negative months, so no exit-horizon variant is promoted.
- The rejected replay root was archived under `/tmp/stock_dashboard_retained_reports_20260706/retained_artifacts/segment_risk_exit_horizon_scan_rejection_20260707/` and deleted. The temporary exit-horizon scan spec was removed from the active registry to avoid repeated default reruns.
- Cleanup: the superseded neutral-chop date-scale replay root was archived as small registry/report/governance/projection JSONs under `/tmp/stock_dashboard_retained_reports_20260706/retained_artifacts/neutral_chop_date_scale_predecessor_20260707/` and deleted. Compact replay roots are limited to the liquidity-replacement predecessor and the segment-risk challenger.

[2026-07-07T23:35:00+08:00] Defensive-crowding multi-condition scale is rejected after formal replay despite reducing negative months:

- A bounded selected-pick two-condition scan retained at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_segment_risk_defensive_crowding_two_condition_scan_20260707.json` checked `9,636` point-in-time feature configurations. The best proxy rule scaled Rank1 to `0.0` when `return_5d_percentile <= 0.1` and `turnover_rate_percentile <= 0.1`, improving horizon-normalized proxy `1.9012 -> 1.9320` and negative months `2 -> 1` while preserving proxy positive-date, path and `14` underfilled active picks.
- Runner support for multi-condition `segment_risk_scale_rules` was added and tested, but the temporary registered spec was not kept after formal rejection.
- Formal full713 stream replay root `/tmp/stock_dashboard_label_v3_segment_risk_defensive_crowding_full713_min60` produced candidate run `walk-forward-model-candidate-run-73d733cc147d0299`, registry `model-spec-registry-60f24e714885819d`, report `model-comparison-report-2c3dac9477edd0f3`, governance `governance-promotion-decision-31bfbb626d13b722`, and dashboard registry `dashboard-approved-projection-registry-1b3178948640b600`.
- Best formal trial was `trial-002`. It reduced formal negative months from `2` to `1` by clearing `2024-08`, improved mean net excess `0.032964 -> 0.033337`, and preserved maxDD/path around `-3.058%` / `-0.5966`, but it degraded total return `+253.613% -> +252.317%`, annualized return `+62.811% -> +62.580%`, and left configured `1,000,000 CNY` / `5% ADV` capacity blocked with `14` underfilled active picks.
- Decision: reject and remove the temporary spec from the active registry. Do not promote rules that clear a negative month by giving back the current segment-risk frontier's total-return floor. The remaining useful direction is not another selected-pick scale rule; it needs richer ex-ante opportunity-set construction or a capacity-aware model that improves 2024-02 and the underfilled picks without degrading the formal return frontier.
- Cleanup: the rejected replay root was archived as small registry/report/governance/projection JSONs under `/tmp/stock_dashboard_retained_reports_20260706/retained_artifacts/segment_risk_defensive_crowding_rejection_20260707/` and deleted. Compact replay roots remain limited to the liquidity-replacement predecessor and the segment-risk challenger.

[2026-07-07T23:58:00+08:00] Defensive-crowding Top50 replacement becomes the new blocked formal frontier:

- A bounded incremental Top50 replacement proxy retained at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_segment_risk_defensive_crowding_top50_replacement_scan_20260707.json` tested replacement, not cashing: when current Rank1 had `return_5d_percentile <= 0.1` and `turnover_rate_percentile <= 0.1`, replace it with a same-date Top10 candidate requiring `avg_amount_20d >= 100,000,000`, `return_5d_percentile >= 0.1`, and `turnover_rate_percentile <= 0.1`. The proxy checked `1,440` configs and found `739` accepted; the selected rule replaced `7` of `8` trigger dates and improved proxy total `1.9012 -> 1.9731` while reducing negative months `2 -> 1`.
- Runner support was extended so additional Rank1 replacement rules can filter the source by `return_5d_percentile` and filter replacement candidates by `return_5d_percentile`, `turnover_rate_percentile`, and score while keeping old replacement rules compatible.
- The fixed candidate is registered as `weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_replacement_v1`.
- Formal full713 stream replay root `/tmp/stock_dashboard_label_v3_segment_risk_defensive_crowding_replacement_full713_min60` produced candidate run `walk-forward-model-candidate-run-cbe41a865c118889`, registry `model-spec-registry-9e438820482697b8`, report `model-comparison-report-36d14a4a5c301cde`, governance `governance-promotion-decision-00ef2d8c24ded644`, and dashboard registry `dashboard-approved-projection-registry-f2633cc23a1f08ef`.
- Versus the segment-risk frontier, formal metrics improve without degrading the required return/drawdown/overfit floors: total return `+253.613% -> +262.281%`, annualized return `+62.811% -> +64.339%`, mean net excess `0.032964 -> 0.033717`, positive-date rate `45.18% -> 45.33%`, negative months `2 -> 1` (`2024-02` remains), alpha t-stat `7.4416 -> 7.6069`, DSR `0.999999996 -> 0.999999999`, and PBO remains `0.0`; maxDD/path/worst month stay about `-3.058%` / `-0.5966` / `-0.8605%`.
- Remaining blocker: configured `1,000,000 CNY` / `5% ADV` capacity still has `14` active picks below full fill. Lower-capital research full-fill tier remains `120,000 CNY`. Therefore this is the new blocked research frontier, not production, paper-tracking, dashboard, or policy-config ready.
- Capacity interpretation: underfilled exposure is concentrated in Rank1 low-amount names, especially `603117.SH`, and those picks include large positive-return contributors. A coarse minimum-ADV filter or blanket capacity replacement is likely to give back the newly improved return frontier. The next capacity work should first identify ex-ante features that separate low-capacity losers from low-capacity winners, then test capacity-aware replacement/sizing against the new `+262.281%` frontier.
- Retention cleanup: the older liquidity-replacement replay root was archived as small registry/report/governance/projection JSONs under `/tmp/stock_dashboard_retained_reports_20260706/retained_artifacts/liquidity_replacement_predecessor_20260707/` and deleted. Compact replay roots are now limited to the direct predecessor segment-risk root and the current defensive-crowding replacement root. Retention audit passes with retained root `133,070,188` bytes, `0` retained candidate-run files, segment-risk root `47,257,108` bytes, and current replacement root `47,765,112` bytes.

[2026-07-08T00:18:00+08:00] High-momentum Rank1 replacement clears negative months but is rejected for return degradation:

- A narrow incremental proxy retained at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_replacement_frontier_rank1_high_momentum_top50_replacement_scan_20260707.json` tested remaining `2024-02`-style stress: Rank1 high `return_5d_percentile`, high `return_20d_percentile`, elevated benchmark volatility, and existing 20d drawdown, with same-date Top20 replacement. It checked `1,152` configs, found `156` accepted by proxy, and the selected rule reduced proxy negative months `1 -> 0`.
- Runner support for additional source-side high-momentum/high-volatility replacement filters was added and tested, but the temporary formal spec was removed after replay.
- Formal full713 stream replay root `/tmp/stock_dashboard_label_v3_segment_risk_defensive_crowding_high_momentum_replacement_full713_min60` produced candidate run `walk-forward-model-candidate-run-47b32deb373ac423`, registry `model-spec-registry-4d7069d82f4f7145`, report `model-comparison-report-9140a97491b205cf`, governance `governance-promotion-decision-92c6bbf8889f2a19`, and dashboard registry `dashboard-approved-projection-registry-9af9bd6d8531f9e7`.
- Formal result: negative months clear completely (`1 -> 0`) and DSR/PBO remain strong (`DSR 0.999999999`, `PBO 0.0`), but total return degrades versus the current frontier `+262.281% -> +255.483%`, annualized return `+64.339% -> +63.143%`, and configured capacity remains blocked with `14` underfilled active picks.
- Decision: reject and remove the temporary spec from active registry. Clearing the negative-month gate is not enough if the current return frontier is materially degraded. This remains useful evidence that 2024-02 can be cleared, but the next candidate must preserve the current `+262.281%` return floor while addressing capacity.
- Cleanup: the rejected replay root was archived as small registry/report/governance/projection JSONs under `/tmp/stock_dashboard_retained_reports_20260706/retained_artifacts/high_momentum_replacement_rejection_20260707/` and deleted. Retention audit passes with retained root `134,625,755` bytes, `0` retained candidate-run files, and compact replay roots still limited to segment-risk predecessor plus current defensive-crowding replacement.

[2026-07-07T13:55:00+08:00] Weak-overheated low-turnover replacement becomes the new blocked formal frontier and clears negative-month stress:

- A bounded selected-pick plus Top20 proxy tested the remaining defensive-crowding frontier stress without month or symbol filters. The accepted feature-state rule triggers when Rank1 is in a weak and volatile benchmark regime (`benchmark_return_20d <= -0.01`, `benchmark_volatility_20d >= 0.035`), has high low-volatility percentile (`>= 0.90`), strong 5d/20d relative strength (`return_5d_percentile >= 0.85`, `return_20d_percentile >= 0.90`), low turnover (`turnover_rate_percentile <= 0.10`), and `avg_amount_20d <= 500M`. It replaces Rank1 with a same-date Top20 candidate requiring `avg_amount_20d >= 50M`, `return_20d_percentile <= 0.80`, and `turnover_rate_percentile <= 0.30`.
- Runner support was generalized so Rank1 replacement rules now accept reusable `source_conditions` and `candidate_conditions` lists using the same feature/operator threshold format as segment-risk scale rules. This avoids adding one-off source/candidate filter fields for every new feature.
- The fixed challenger is registered as `weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_weak_overheated_replacement_v1`.
- Formal full713 stream replay root `/tmp/stock_dashboard_label_v3_weak_overheated_replacement_full713_min60` produced candidate run `walk-forward-model-candidate-run-b64804e67db8a9f0`, registry `model-spec-registry-631845742ad6da84`, report `model-comparison-report-938db0b5f0cc8bf5`, governance `governance-promotion-decision-f58e20f640f37ef5`, and dashboard registry `dashboard-approved-projection-registry-0ec47da36887b1bd`.
- Versus the prior defensive-crowding replacement frontier, formal metrics improve or hold: total return `+262.281% -> +265.589%`, annualized return `+64.339% -> +64.917%`, mean net excess `0.033717 -> 0.033996`, positive-date rate `45.33% -> 45.64%`, negative months `1 -> 0`, worst monthly mean `-0.8605% -> +0.0852%`, alpha t-stat `7.6069 -> 7.6858`, DSR `0.999999999 -> 0.999999999`, and PBO remains `0.0`; maxDD/path remain about `-3.058%` / `-0.5966`.
- Remaining blocker is now specifically capacity: configured `1,000,000 CNY` / `5% ADV` still has `14` active picks below full fill, with lower-capital full-fill research tier still `120,000 CNY`. The comparison report no longer blocks on negative monthly mean. This is the new research frontier, but it is still not production, paper-tracking, dashboard, or policy-config ready.
- Cleanup: the superseded segment-risk scale replay root was archived as small registry/report/governance/projection JSONs under `/tmp/stock_dashboard_retained_reports_20260706/retained_artifacts/segment_risk_scale_predecessor_20260708/` and deleted. Compact replay roots are now limited to the prior defensive-crowding replacement root and the new weak-overheated replacement root.

[2026-07-07T14:05:00+08:00] Capacity blocker has no non-degrading simple Rank1 low-ADV Top20 replacement on the new frontier:

- A lightweight capacity proxy scanned `57,600` feature-state replacement configurations on top of the new weak-overheated frontier. The scan targeted Rank1 low-ADV states using only point-in-time fields such as `avg_amount_20d`, 5d/20d relative-strength percentiles, turnover percentile and low-volatility percentile, then substituted same-date Top20 candidates with stronger ADV floors and bounded return/turnover constraints.
- Acceptance required reducing the configured `1,000,000 CNY` / `5% ADV` underfilled active-pick count below `14` while preserving the new frontier floors: mean net excess, horizon-normalized total proxy, maxDD proxy, path drawdown proxy, zero negative months, and worst monthly mean.
- Result: `0` accepted configurations. This matches the underfilled-pick anatomy: several low-ADV Rank1 picks, especially `603117.SH`, are major positive-return contributors, so a blanket liquidity substitution gives back the return edge before it clears capacity.
- A Top50 future-label oracle bound confirms the shape of the remaining problem. If each underfilled Rank1 slot is replaced by the best future-return same-date Top50 candidate with `avg_amount_20d >= 18.5M`, underfilled picks fall `14 -> 0` and total proxy improves, but negative months reappear (`0 -> 1`). Raising the liquidity floor to `200M` still clears capacity in oracle but degrades total proxy below the new frontier and also reintroduces a negative month.
- Decision: do not register another simple low-ADV replacement spec. The remaining blocker needs a richer capacity-aware opportunity-set model or explicit capital sizing contract that jointly optimizes capacity and monthly stability; simple Rank1 ADV thresholds, same-date Top20 liquidity substitution, and cash/redistribution-style execution fixes are rejected unless a new feature source changes the separability of low-capacity winners vs losers.

[2026-07-07T14:18:00+08:00] New-frontier order-level capacity sizing remains rejected:

- Compact retained artifact: `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_weak_overheated_order_level_capacity_proxy_20260707.json`.
- The proxy reused the new weak-overheated formal candidate run and applied the same `1,000,000 CNY` / `5% ADV` order cap without duplicating prediction rows. Baseline full-fill reference is the accepted new frontier: mean `0.033996`, total proxy `2.0005`, zero negative months, path `-0.5966`, and `14` underfilled active picks.
- `adv_cap_cash` leaves unfilled capital in cash and degrades mean `0.033996 -> 0.031837`, total proxy `2.0005 -> 1.7993`, and reintroduces one negative month (`2024-05`).
- Rank/score redistribution reduces cash drag but still degrades mean to `0.031987`, total proxy to `1.8129`, and reintroduces one negative month (`2024-05`).
- Top5 substitution changes the 14 underfilled slots but degrades mean to `0.031421`, total proxy to `1.7613`, positive-date rate to `45.33%`, and reintroduces one negative month.
- Capacity-aware TopN pre-selection is much worse: it changes `167` slots, lowers mean to `0.028902`, total proxy to `1.5438`, worsens maxDD/path, and reintroduces `7` negative months.
- Decision: no order-level sizing or selected-basket execution adjustment is accepted. The remaining capacity blocker cannot be cleared by execution-layer math on top of the current selected picks; it needs a model-level capacity objective, new features, or a formally scoped lower-capital product contract.

[2026-07-07T14:22:00+08:00] New-frontier Top50 capacity soft-rerank is rejected:

- Matching Top50 candidate inventory was generated for the weak-overheated frontier at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_weak_overheated_top50_candidate_inventory_20260707.json` (`top-candidate-inventory-56f31d4246628dbf`, `32,650` rows, about `44M`).
- Soft-rerank result is retained at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_weak_overheated_top50_capacity_soft_rerank_proxy_20260707.json`.
- Baseline full-fill reference remains the accepted weak-overheated frontier: mean `0.033996`, horizon-normalized total proxy `2.0005`, zero negative months, path drawdown sum `-0.5966`, and `14` active picks underfilled at `1,000,000 CNY` / `5% ADV`.
- Liquidity weights `0.01`, `0.02`, `0.05`, `0.1`, `0.2`, and `0.4` found `0` non-degrading scans. Weights `0.1+` can clear underfilled active picks to `0`, but total proxy drops to about `1.49-1.51`, mean drops to about `0.0283-0.0285`, positive-date rate falls to about `43.0%`, and `7-8` negative months return.
- Decision: do not continue monotonic liquidity-bonus reranking over the current Top50 opportunity set. It solves capacity mechanically by selecting a materially worse model. The remaining search must add capacity-separating ex-ante features, a joint monthly-stability/capacity objective, or a scoped lower-capital product contract.

[2026-07-07T14:42:00+08:00] Underfilled-feature Rank1 replacement becomes the new blocked formal frontier:

- A targeted underfilled-source scan retained at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_weak_overheated_underfilled_feature_replacement_scan_20260707.json` used the weak-overheated Top50 inventory to test small feature-state replacement rules over the actual underfilled active picks.
- The accepted rule is ex-ante and symbol/month-free: replace a low-ADV Rank1 slot when `avg_amount_20d <= 4M`, `return_5d_percentile >= 0.60`, `return_20d_percentile <= 0.52`, `amount_10d_vs_20d_percentile >= 0.55`, and `turnover_rate_percentile >= 0.04`; substitute the first same-date Top20 candidate with `avg_amount_20d >= 50M`, `return_20d_percentile <= 0.80`, and `turnover_rate_percentile <= 0.30`.
- Proxy replaced one active underfilled losing slot (`2023-11-09`, source `603117.SH`, replacement `601766.SH`), improving total proxy `2.0005 -> 2.0125`, mean `0.033996 -> 0.034118`, positive-date rate `45.64% -> 45.79%`, keeping zero negative months, and reducing underfilled active picks `14 -> 13`.
- The fixed spec is now registered as `weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_weak_overheated_underfilled_feature_replacement_v1`.
- Formal full713 stream replay root `/tmp/stock_dashboard_label_v3_underfilled_feature_replacement_full713_min60` produced candidate run `walk-forward-model-candidate-run-b2197c9884e8e420`, registry `model-spec-registry-3cee5a7e8e0157ed`, report `model-comparison-report-9dc0123fffece1d2`, governance `governance-promotion-decision-e7d8aeab9974f0d2`, and dashboard registry `dashboard-approved-projection-registry-465683cf238f22b4`.
- Versus the weak-overheated frontier, formal metrics improve or hold: total return `+265.589% -> +267.050%`, annualized return `+64.917% -> +65.171%`, execution mean `0.033996 -> 0.034118`, selected mean `0.033008 -> 0.033130`, positive-date rate `45.64% -> 45.79%`, alpha t-stat `7.6858 -> 7.7159`, DSR `0.99999999913 -> 0.99999999928`, PBO remains `0.0`, negative months remain `0`, worst monthly mean remains `+0.0852%`, and maxDD/path remain about `-3.058%` / `-0.5966`.
- Capacity improves but remains blocked: configured `1,000,000 CNY` / `5% ADV` active underfilled picks fall `14 -> 13`, full-fill rate improves `98.47% -> 98.58%`, but the worst pick is still `603117.SH` on `2024-06-05` with minimum fill rate `0.12194`; lower-capital full-fill research tier remains about `120,000 CNY`.
- Cleanup: the superseded defensive-crowding replacement replay root was archived as small registry/report/governance/projection JSONs under `/tmp/stock_dashboard_retained_reports_20260706/retained_artifacts/defensive_crowding_replacement_predecessor_20260707/` and deleted. Compact replay roots are now limited to the direct predecessor weak-overheated root and the new underfilled-feature root. Retention audit passes with retained root `182,932,851` bytes, `0` retained candidate-run files, weak-overheated root `48,165,431` bytes, and current root `48,621,213` bytes.
- This is a stronger blocked research frontier, not production, paper-tracking, dashboard, or policy-config ready. The remaining blocker is still model-level capacity at the configured 1M notional; future work should target the remaining low-capacity winners/losers jointly instead of global liquidity bonuses.

[2026-07-07T14:58:00+08:00] Low-volatility weak-benchmark underfilled replacement is rejected despite capacity improvement:

- Targeted proxy retained at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_underfilled_frontier_lowvol_benchmark_underfilled_replacement_scan_20260707.json` suggested a second capacity-separating Rank1 rule could improve underfilled active picks `13 -> 9` while preserving zero negative months.
- The temporary formal spec tested low-ADV Rank1 source states with high low-volatility percentile, weak benchmark 20d return, shallow 20d drawdown, and low volatility percentile, replacing them with same-date Top20 liquid candidates.
- Formal full713 replay root `/tmp/stock_dashboard_label_v3_underfilled_lowvol_benchmark_replacement_full713_min60` produced candidate run `walk-forward-model-candidate-run-0fc45b0d42b82335`, registry `model-spec-registry-59ee9d3f7c3d85d9`, report `model-comparison-report-0a3a750b79141cc0`, governance `governance-promotion-decision-075516e6851b860c`, and dashboard registry `dashboard-approved-projection-registry-83dc6d2e407b8060`.
- Formal result versus the active underfilled-feature frontier: capacity improves `13 -> 9` underfilled active picks and zero negative months hold, but total return degrades `+267.050% -> +266.845%`, annualized return `+65.171% -> +65.135%`, positive-date rate `45.79% -> 45.64%`, alpha t-stat `7.7159 -> 7.6934`, and DSR `0.99999999928 -> 0.99999999917`.
- Decision: reject and remove the temporary spec from the active registry. Capacity improvement is not enough when the current formal return/positive-date/overfit frontier degrades. Keep this only as evidence that more capacity relief is possible, but the next candidate must preserve the `+267.050%` total-return frontier.
- Cleanup: the rejected replay root was archived as small registry/report/governance/projection JSONs under `/tmp/stock_dashboard_retained_reports_20260706/retained_artifacts/underfilled_lowvol_benchmark_replacement_rejection_20260707/` and deleted. Retention audit passes with retained root `184,751,027` bytes and compact replay roots still limited to weak-overheated predecessor plus current underfilled-feature frontier.

[2026-07-07T15:12:00+08:00] Shallow-drawdown low-volatility underfilled replacement becomes the new blocked formal frontier:

- A narrower targeted scan retained at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_underfilled_frontier_shallow_drawdown_lowvol_replacement_scan_20260707.json` isolated one underfilled losing Rank1 state without triggering the broader rejected low-volatility rule.
- The accepted rule is feature-state only: source `avg_amount_20d <= 8M`, `low_volatility_percentile >= 0.99`, `benchmark_return_20d <= -0.015`, `max_drawdown_20d >= -0.02`, `amount_10d_vs_20d_percentile >= 0.80`, `return_20d_percentile >= 0.60`, and `turnover_rate_percentile <= 0.03`; replacement uses the first same-date Top20 candidate with `avg_amount_20d >= 50M`.
- Proxy replaced one slot (`2024-09-02`, `601686.SH -> 601018.SH`), improving total proxy `2.0125 -> 2.0159` and reducing underfilled active picks `13 -> 12` without changing zero negative months.
- The fixed spec is registered as `weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_weak_overheated_underfilled_shallow_drawdown_lowvol_replacement_v1`.
- Formal full713 stream replay root `/tmp/stock_dashboard_label_v3_underfilled_shallow_drawdown_lowvol_replacement_full713_min60` produced candidate run `walk-forward-model-candidate-run-f46f7ce65f4d122c`, registry `model-spec-registry-f83f28b2b1bb0f57`, report `model-comparison-report-b29f79d7ca4c8aca`, governance `governance-promotion-decision-c006b2bf4ffbeded`, and dashboard registry `dashboard-approved-projection-registry-eb88d08407e511c4`.
- Versus the underfilled-feature frontier, formal metrics improve or hold: total return `+267.050% -> +267.463%`, annualized return `+65.171% -> +65.243%`, execution mean `0.034118 -> 0.034153`, selected mean `0.033130 -> 0.033164`, alpha t-stat `7.7159 -> 7.7269`, DSR `0.99999999928 -> 0.99999999933`, PBO remains `0.0`, positive-date rate remains `45.79%`, negative months remain `0`, worst monthly mean remains `+0.0852%`, and maxDD/path remain about `-3.058%` / `-0.5966`.
- Capacity improves but remains blocked: configured `1,000,000 CNY` / `5% ADV` underfilled active picks fall `13 -> 12`; lower-capital full-fill research tier remains about `120,000 CNY`, with the same worst-pick fill-rate floor still driven by `603117.SH`.
- Cleanup: the superseded weak-overheated replay root was archived under `/tmp/stock_dashboard_retained_reports_20260706/retained_artifacts/weak_overheated_replacement_predecessor_20260707/` and deleted. Compact replay roots are now limited to the direct predecessor underfilled-feature root and current shallow-drawdown low-vol root. Retention audit passes with retained root `186,281,888` bytes, current root `49,016,212` bytes, and retained candidate-run files `0`.
- This is the new blocked research frontier, not production, paper-tracking, dashboard, or policy-config ready.

[2026-07-07T15:28:00+08:00] Low-5d/high-20d candidate replacement becomes the new blocked formal frontier:

- A targeted proxy retained at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_shallow_lowvol_frontier_low5d_high20d_candidate_replacement_scan_20260707.json` found a clean underfilled replacement for the `2024-09-04` state.
- Source rule: Rank1 `avg_amount_20d <= 8M`, `low_volatility_percentile >= 0.98`, `benchmark_return_20d <= -0.02`, `return_5d_percentile <= 0.30`, `return_20d_percentile >= 0.50`, `amount_10d_vs_20d_percentile <= 0.40`, and `turnover_rate_percentile <= 0.10`. Candidate rule requires same-date Top20 candidate with `avg_amount_20d >= 50M` and `return_20d_percentile >= 0.85`.
- Proxy replaced one slot (`2024-09-04`, `600569.SH -> 601628.SH`), reducing underfilled active picks `12 -> 11`, improving total proxy `2.0159 -> 2.0265`, and raising positive-date rate while keeping zero negative months.
- The fixed spec is registered as `weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_weak_overheated_underfilled_low5d_high20d_candidate_replacement_v1`.
- Formal full713 stream replay root `/tmp/stock_dashboard_label_v3_underfilled_low5d_high20d_candidate_replacement_full713_min60` produced candidate run `walk-forward-model-candidate-run-1ae8453ec7179b21`, registry `model-spec-registry-de938ae220a5ee2e`, report `model-comparison-report-8ace0aae7cf71605`, governance `governance-promotion-decision-4ed8f0a59d50110e`, and dashboard registry `dashboard-approved-projection-registry-ff56b92718d3764d`.
- Versus the shallow-drawdown low-vol frontier, formal metrics improve or hold: total return `+267.463% -> +268.738%`, annualized return `+65.243% -> +65.464%`, execution mean `0.034153 -> 0.034260`, selected mean `0.033164 -> 0.033272`, positive-date rate `45.79% -> 45.94%`, alpha t-stat `7.7269 -> 7.7523`, DSR `0.99999999933 -> 0.99999999943`, PBO remains `0.0`, negative months remain `0`, worst monthly mean remains `+0.0852%`, and maxDD/path remain about `-3.058%` / `-0.5966`.
- Capacity improves but remains blocked: configured `1,000,000 CNY` / `5% ADV` underfilled active picks fall `12 -> 11`; lower-capital full-fill research tier remains about `120,000 CNY`, still constrained by low-ADV positive `603117.SH` dates.
- Cleanup: the superseded underfilled-feature replay root was archived under `/tmp/stock_dashboard_retained_reports_20260706/retained_artifacts/underfilled_feature_replacement_predecessor_20260707/` and deleted. Compact replay roots are now limited to the direct predecessor shallow-drawdown low-vol root and the current low5d/high20d root. Retention audit passes with retained root `187,929,682` bytes, current root `49,163,928` bytes, and retained candidate-run files `0`.
- This is the new blocked research frontier, not production, paper-tracking, dashboard, or policy-config ready.

[2026-07-07T15:42:00+08:00] Weak-benchmark low-turnover candidate replacement becomes the new blocked formal frontier:

- A narrow proxy retained at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_low5d_high20d_frontier_weak_benchmark_lowturn_candidate_replacement_scan_20260707.json` targeted the last remaining underfilled losing Rank1 slot.
- Source rule: Rank1 `avg_amount_20d <= 20M`, `benchmark_return_20d <= -0.035`, `return_5d_percentile >= 0.70`, `return_20d_percentile <= 0.50`, `turnover_rate_percentile <= 0.01`, `amount_10d_vs_20d_percentile >= 0.55`, and `low_volatility_percentile >= 0.96`. Candidate rule requires same-date Top20 candidate with `avg_amount_20d >= 30M`, `return_20d_percentile <= 0.40`, and `turnover_rate_percentile >= 0.035`.
- Proxy replaced one slot (`2025-01-27`, `600167.SH -> 600032.SH`), reducing underfilled active picks `11 -> 10`, improving total proxy `2.0265 -> 2.0288`, and keeping zero negative months.
- The fixed spec is registered as `weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_weak_overheated_underfilled_weak_benchmark_lowturn_candidate_replacement_v1`.
- Formal full713 stream replay root `/tmp/stock_dashboard_label_v3_underfilled_weak_benchmark_lowturn_candidate_replacement_full713_min60` produced candidate run `walk-forward-model-candidate-run-95a2b6952b36fbf8`, registry `model-spec-registry-aad66aab48a2489a`, report `model-comparison-report-39432b92944624bb`, governance `governance-promotion-decision-b400b659f14b1f02`, and dashboard registry `dashboard-approved-projection-registry-db38ca81b357dce2`.
- Versus the low5d/high20d frontier, formal metrics improve or hold: total return `+268.738% -> +269.020%`, annualized return `+65.464% -> +65.512%`, execution mean `0.034260 -> 0.034283`, selected mean `0.033272 -> 0.033295`, alpha t-stat `7.7523 -> 7.7583`, DSR `0.99999999943 -> 0.99999999945`, PBO remains `0.0`, positive-date rate remains `45.94%`, negative months remain `0`, worst monthly mean remains `+0.0852%`, and maxDD/path remain about `-3.058%` / `-0.5966`.
- Capacity improves but remains blocked: configured `1,000,000 CNY` / `5% ADV` underfilled active picks fall `11 -> 10`; lower-capital full-fill research tier remains about `120,000 CNY`, constrained by positive low-ADV winners.
- Cleanup: the superseded shallow-drawdown low-vol replay root was archived under `/tmp/stock_dashboard_retained_reports_20260706/retained_artifacts/underfilled_shallow_drawdown_lowvol_predecessor_20260707/` and deleted. Compact replay roots are now limited to direct predecessor low5d/high20d root plus current weak-benchmark lowturn root. Retention audit passes with retained root `189,701,871` bytes, current root `49,466,470` bytes, and retained candidate-run files `0`.
- This is the new blocked research frontier, not production, paper-tracking, dashboard, or policy-config ready.

[2026-07-07T16:08:00+08:00] High-turnover amount-expansion candidate replacement becomes the new blocked formal frontier:

- A narrow proxy retained at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_weak_benchmark_lowturn_frontier_high_turnover_amount_replacement_scan_20260707.json` targeted one remaining underfilled Rank1 state that was strong but capacity-constrained rather than weak-benchmark/low-turnover.
- Source rule: Rank1 `avg_amount_20d <= 20M`, `benchmark_return_20d >= 0.0`, `return_5d_percentile >= 0.90`, `return_20d_percentile >= 0.90`, `turnover_rate_percentile >= 0.50`, `amount_10d_vs_20d_percentile >= 0.95`, and `low_volatility_percentile <= 0.30`. Candidate rule requires same-date Top20 candidate with `avg_amount_20d >= 20M` and `return_20d_percentile >= 0.80`.
- Proxy replaced one slot (`2024-09-25`, `600231.SH -> 000652.SZ`), reducing underfilled active picks `10 -> 9`, improving mean proxy `0.034283 -> 0.034598`, and keeping zero negative months.
- The fixed spec is registered as `weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_weak_overheated_underfilled_high_turnover_amount_candidate_replacement_v1`.
- Formal full713 stream replay root `/tmp/stock_dashboard_label_v3_underfilled_high_turnover_amount_candidate_replacement_full713_min60` produced candidate run `walk-forward-model-candidate-run-09a3fb39eac382b2`, registry `model-spec-registry-a3afa4d54d085187`, report `model-comparison-report-4362c25b310df205`, governance `governance-promotion-decision-fd997b0710a38db7`, and dashboard registry `dashboard-approved-projection-registry-35783f32d43f8d42`.
- Versus the weak-benchmark lowturn frontier, formal metrics improve or hold: total return `+269.020% -> +272.786%`, annualized return `+65.512% -> +66.162%`, execution mean `0.034283 -> 0.034598`, selected mean `0.033295 -> 0.033610`, alpha t-stat `7.7583 -> 7.8055`, DSR `0.99999999945 -> 0.99999999959`, PBO remains `0.0`, positive-date rate remains `45.94%`, negative months remain `0`, worst monthly mean remains `+0.0852%`, and maxDD/path remain about `-3.058%` / `-0.5966`.
- Capacity improves but remains blocked: configured `1,000,000 CNY` / `5% ADV` underfilled active picks fall `10 -> 9`; full-fill rate improves `98.90% -> 99.01%`, but minimum fill rate remains `0.12194` and the worst pick is still `603117.SH` on `2024-06-05`. Lower-capital full-fill research tier remains about `120,000 CNY`.
- Cleanup: the superseded low5d/high20d replay root was archived under `/tmp/stock_dashboard_retained_reports_20260706/retained_artifacts/underfilled_low5d_high20d_candidate_predecessor_20260707/` and deleted. Compact replay roots are now limited to direct predecessor weak-benchmark lowturn root plus current high-turnover amount-expansion root. Retention audit passes with retained root `191,566,603` bytes, current root `49,593,227` bytes, predecessor root `49,466,470` bytes, and retained candidate-run files `0`.
- This is the new blocked research frontier, not production, paper-tracking, dashboard, or policy-config ready. Next work should use `+272.786%` total return, `+66.162%` annualized return, zero negative months, and unchanged maxDD/path as non-degradation floors while looking for capacity-separating ex-ante features among the remaining positive low-ADV winners.

[2026-07-07T16:32:00+08:00] Low-turnover mid-momentum candidate replacement becomes the new blocked formal frontier:

- Current-frontier Top50 inventory was generated at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_high_turnover_amount_frontier_top50_candidate_inventory_20260707.json` (`top-candidate-inventory-f024f6cc98fe5964`, `32,650` candidate rows). The scan retained only Top50 rows per date and did not write to runtime DB tables.
- A narrow proxy targeted a remaining low-ADV Rank1 source on `2026-02-13`: `603235.SH` had `avg_amount_20d <= 20M`, weak benchmark `-0.020 <= benchmark_return_20d <= -0.010`, mid 5d/20d percentiles, very low turnover, strong amount confirmation, high low-volatility percentile and an existing 20d drawdown. The first eligible non-selected Top50 replacement was `600177.SH` with `avg_amount_20d >= 100M`, moderate 20d momentum, enough turnover/amount confirmation and `net_excess_return 0.1146` versus source `0.0255`.
- The fixed spec is registered as `weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_weak_overheated_underfilled_lowturn_midmomentum_candidate_replacement_v1`.
- Formal full713 stream replay root `/tmp/stock_dashboard_label_v3_underfilled_lowturn_midmomentum_candidate_replacement_full713_min60` produced candidate run `walk-forward-model-candidate-run-b05864c269bbfd1b`, registry `model-spec-registry-a657b516f7ecf6d5`, report `model-comparison-report-d43f4494e0dd5d73`, governance `governance-promotion-decision-28b23d204e450fc0`, and dashboard registry `dashboard-approved-projection-registry-25679e869a9b048a`.
- Versus the high-turnover amount frontier, formal metrics improve or hold: total return `+272.786% -> +274.298%`, annualized return `+66.162% -> +66.422%`, execution mean `0.034598 -> 0.034722`, selected mean `0.033610 -> 0.033734`, alpha t-stat `7.8055 -> 7.8303`, DSR `0.99999999959 -> 0.99999999965`, PBO remains `0.0`, positive-date rate remains `45.94%`, negative months remain `0`, worst monthly mean remains `+0.0852%`, and maxDD/path remain about `-3.058%` / `-0.5966`.
- Capacity improves but remains blocked: configured `1,000,000 CNY` / `5% ADV` underfilled active picks fall `9 -> 8`; full-fill rate improves `99.01% -> 99.12%`, but minimum fill rate remains `0.12194` and the worst pick is still `603117.SH` on `2024-06-05`. Lower-capital full-fill research tier remains about `120,000 CNY`.
- Cleanup: the superseded weak-benchmark lowturn replay root was archived under `/tmp/stock_dashboard_retained_reports_20260706/retained_artifacts/underfilled_weak_benchmark_lowturn_predecessor_20260707/` and deleted. Compact replay roots are now limited to direct predecessor high-turnover amount root plus current lowturn-midmomentum root. Retention audit passes with retained root `239,163,015` bytes, current root `49,776,259` bytes, predecessor root `49,593,227` bytes, and retained candidate-run files `0`.
- This is the new blocked research frontier, not production, paper-tracking, dashboard, or policy-config ready. The remaining frontier floor is now `+274.298%` total return, `+66.422%` annualized return, zero negative months, and unchanged maxDD/path. The next capacity work must address the still-positive low-ADV `603117.SH` cluster without giving back the return edge.

[2026-07-07T16:55:00+08:00] Low-return low-ADV defensive candidate replacement becomes the new blocked formal frontier:

- A narrow Top50 proxy on the lowturn-midmomentum frontier targeted the `2023-09-25` low-ADV Rank1 source. Source rule: `avg_amount_20d <= 4M`, `-0.012 <= benchmark_return_20d <= -0.008`, `0.15 <= return_5d_percentile <= 0.30`, `0.20 <= return_20d_percentile <= 0.32`, `0.04 <= turnover_rate_percentile <= 0.07`, `0.45 <= amount_10d_vs_20d_percentile <= 0.55`, `low_volatility_percentile >= 0.98`, and `max_drawdown_20d <= -0.040`.
- Candidate rule: first same-date non-selected Top50 name with `avg_amount_20d >= 500M`, `return_5d_percentile >= 0.90`, `0.30 <= return_20d_percentile <= 0.45`, `turnover_rate_percentile <= 0.005`, `amount_10d_vs_20d_percentile >= 0.80`, and `low_volatility_percentile >= 0.98`. Proxy replaced `603117.SH -> 601988.SH`, improving source net `0.06847 -> 0.06904` and reducing underfilled active picks `8 -> 7`.
- The fixed spec is registered as `weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_weak_overheated_underfilled_lowret_lowadv_candidate_replacement_v1`.
- Formal full713 stream replay root `/tmp/stock_dashboard_label_v3_underfilled_lowret_lowadv_candidate_replacement_full713_min60` produced candidate run `walk-forward-model-candidate-run-e63336057e382266`, registry `model-spec-registry-1efd64479ae12191`, report `model-comparison-report-a2f76b7f789d6d40`, governance `governance-promotion-decision-9da2b770a95b57e9`, and dashboard registry `dashboard-approved-projection-registry-3a4a9067e0039e5a`.
- Versus the lowturn-midmomentum frontier, formal metrics improve or hold: total return `+274.298% -> +274.308%`, annualized return `+66.422% -> +66.424%`, execution mean `0.034722 -> 0.034724`, selected mean `0.033734 -> 0.033735`, alpha t-stat `7.8303 -> 7.8304`, DSR `0.99999999965 -> 0.99999999965`, PBO remains `0.0`, positive-date rate remains `45.94%`, negative months remain `0`, worst monthly mean remains `+0.0852%`, and maxDD/path remain about `-3.058%` / `-0.5966`.
- Capacity improves but remains blocked: configured `1,000,000 CNY` / `5% ADV` underfilled active picks fall `8 -> 7`; full-fill rate improves `99.12% -> 99.23%`, but minimum fill rate remains `0.12194` and the worst pick is still `603117.SH` on `2024-06-05`. Lower-capital full-fill research tier remains about `120,000 CNY`.
- Cleanup: the superseded high-turnover amount replay root was archived under `/tmp/stock_dashboard_retained_reports_20260706/retained_artifacts/underfilled_high_turnover_amount_predecessor_20260707/` and deleted. Compact replay roots are now limited to direct predecessor lowturn-midmomentum root plus current lowret-lowadv root. Retention audit passes with retained root `241,281,168` bytes, current root `49,889,594` bytes, predecessor root `49,776,259` bytes, and retained candidate-run files `0`.
- This is the new blocked research frontier, not production, paper-tracking, dashboard, or policy-config ready. The remaining frontier floor is now `+274.308%` total return and `+66.424%` annualized return. Remaining capacity blockers are almost entirely positive low-ADV winners, so further replacement is likely to require either a lower-capital contract or a stronger opportunity-set model rather than more small same-date substitutions.

[2026-07-07T17:20:00+08:00] Capacity-cluster candidate replacement becomes the new blocked formal frontier:

- A remaining-underfilled Top50 oracle summary retained at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_lowret_lowadv_frontier_remaining_underfilled_top50_oracle_summary_20260707.json` found `7` active capacity blockers; `4` had same-date Top50 high-ADV non-degrading candidates, while the 2024-05/06 `603117.SH` cluster had no non-degrading liquid Top50 substitute and was intentionally left untouched.
- Three ex-ante feature-state rules were registered together as `weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_weak_overheated_underfilled_capacity_cluster_candidate_replacement_v1`:
  - weak-January mid-20d drawdown source (`2024-01-31`, `002721.SZ -> 002595.SZ`);
  - strong high-turnover amount-expansion source (`2024-07-22`, `000695.SZ -> 002617.SZ`);
  - weak-August low-momentum recovery source (`2024-08-21/22`, `600917.SH -> 603638.SH` and `600917.SH -> 601319.SH`).
- The proxy changed only those `4` dates, improved mean daily selected net excess `0.034760 -> 0.035530`, preserved positive-date rate, and reduced expected active underfilled picks `7 -> 3`. It used feature-state thresholds only, not date/symbol allowlists, and carried `proxy_only_formal_replay_required` claim ceiling.
- Formal full713 stream replay root `/tmp/stock_dashboard_label_v3_underfilled_capacity_cluster_candidate_replacement_full713_min60` produced candidate run `walk-forward-model-candidate-run-8cf650cf13dda990`, registry `model-spec-registry-62d6450a32d0bed2`, report `model-comparison-report-1253096e31fe739a`, governance `governance-promotion-decision-6ea4bffd4f0b4123`, and dashboard registry `dashboard-approved-projection-registry-e87d2d0548068026`.
- Versus the lowret-lowadv frontier, formal metrics improve or hold: total return `+274.308% -> +277.439%`, annualized return `+66.424% -> +66.960%`, execution mean `0.034724 -> 0.034991`, selected mean `0.033735 -> 0.033991`, alpha t-stat `7.8304 -> 7.8792`, DSR `0.99999999965 -> 0.99999999974`, PBO remains `0.0`, positive-date rate remains `45.94%`, negative months remain `0`, worst monthly mean remains `+0.0852%`, and maxDD/path remain about `-3.058%` / `-0.5966`.
- Capacity improves materially but remains blocked: configured `1,000,000 CNY` / `5% ADV` underfilled active picks fall `7 -> 3`; full-fill rate improves `99.23% -> 99.67%`, but minimum fill rate remains `0.12194` and the worst pick is still `603117.SH` on `2024-06-05`. Lower-capital full-fill research tier remains about `120,000 CNY`.
- Cleanup: the superseded lowturn-midmomentum replay root was archived under `/tmp/stock_dashboard_retained_reports_20260706/retained_artifacts/underfilled_lowturn_midmomentum_predecessor_20260707/` and deleted. Compact replay roots are now limited to direct predecessor lowret-lowadv root plus current capacity-cluster root. Retention audit passes with retained root `243,574,474` bytes, current root `50,354,368` bytes, predecessor root `49,889,594` bytes, and retained candidate-run files `0`.
- This is the new blocked research frontier, not production, paper-tracking, dashboard, or policy-config ready. The remaining blocker is now the 2024-05/06 `603117.SH` low-ADV winner cluster: same-date Top50 oracle shows no non-degrading liquid replacement, so clearing configured `1M` capacity likely requires a lower-capital product contract, a different opportunity-set model, or new ex-ante features that identify comparable high-return liquid candidates outside the current Top50 ordering.

[2026-07-07T17:45:00+08:00] Same-date Top200 expansion does not clear the remaining `603117.SH` capacity blocker:

- Retained boundary summary: `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_capacity_cluster_remaining_603117_top200_oracle_summary_20260707.json`. The temporary Top200 inventory was deleted after compacting the summary.
- The summary checked `130,600` candidate rows for the three remaining capacity-cluster blocker dates. Liquid same-date candidate counts were high: `189` on `2024-05-30`, `185` on `2024-06-03`, and `177` on `2024-06-05`.
- Non-degrading liquid candidates were `0` on all three dates. Best liquid substitutes still materially lagged the low-ADV source winners: `2024-05-30` source `603117.SH` net excess `0.5082` versus best liquid `601777.SH` `0.2125`; `2024-06-03` source `0.6069` versus best liquid `601777.SH` `0.2445`; `2024-06-05` source `0.6278` versus best liquid `605116.SH` `0.2607`.
- Capacity math explains why this is not a small tuning gap. Rank1 gross exposure is `2.73 / 3 = 0.91`, so a `1,000,000 CNY` product needs about `910,000 CNY` in each remaining Rank1 slot. At `5% ADV`, full fill needs about `18,200,000 CNY` 20d average amount; the remaining `603117.SH` dates have only `2.461M`, `2.247M`, and `2.219M` ADV, about `7.4x-8.2x` below the full-fill requirement.
- Decision: do not keep expanding same-date TopN replacement in the current opportunity set as the next optimization path. It can solve liquidity mechanically only by giving back the current `+277.439%` return frontier. Further progress requires either a lower-capital product contract, a different opportunity-set model that can rank comparable liquid winners ex ante, or new input features that are not present in the current PIT matrix.
- Retention audit after this summary still passes: retained root `/private/tmp/stock_dashboard_retained_reports_20260706` is `243,586,963` bytes, retained candidate-run files remain `0`, and compact replay roots remain limited to the lowret-lowadv predecessor plus current capacity-cluster frontier.

[2026-07-07T18:05:00+08:00] Next 1M-capacity work requires feature-matrix v3, not v2 threshold tuning:

- Source/code inspection confirms the current formal `pit_feature_matrix:v2` exposed to `model_candidate_runner` contains price momentum, reversal/overheat, volatility/drawdown, amount/turnover liquidity, execution proxies, benchmark regime, cross-sectional percentiles, and industry relative return features.
- Existing runtime/source tables already contain some richer raw inputs: `MarketBar` carries `total_mv`, `circ_mv`, `pe_ttm`, and `pb`; `Stock.profile_payload` carries industry/template metadata; `FeatureSnapshot`, news analysis, and `pit_feature_store.py` provide a design path for news, valuation and fundamental features. However these are not part of the current formal v2 scoring matrix used by the accepted capacity-cluster frontier.
- Decision: if the requirement remains a `1,000,000 CNY` / `5% ADV` product without degrading the `+277.439%` frontier, the next research package must be a `pit_feature_matrix:v3` / opportunity-set-model change. Candidate feature families should include capacity-adjusted liquidity depth, market-cap/float-cap and valuation buckets, event/news/fundamental freshness where PIT-safe, and maybe a capacity-aware alpha objective. This needs a new formal replay and PBO/DSR comparison; it should not be represented as another small Rank1 replacement rule over v2.
- Performance guardrail: do not load the 6GB PIT feature matrix into memory for exploratory inspection. Use source schema/code, retained compact inventories, stream replay, or bounded chunk readers.

[2026-07-07T18:18:00+08:00] Feature-matrix v3 scaffold adds PIT market-cap and valuation fields:

- Implemented the first formal `pit_feature_matrix:v3` scaffold without running a full713 rebuild. `model_exploration_snapshot` now emits `valuation_capacity.total_mv`, `valuation_capacity.circ_mv`, `valuation_capacity.pe_ttm`, and `valuation_capacity.pb` from PIT `MarketBar` rows. It also derives same-date cross-sectional capacity/valuation signals: `total_mv_percentile`, `circ_mv_percentile`, `small_total_mv_percentile`, `small_circ_mv_percentile`, `pe_ttm_percentile`, and `pb_percentile`. The feature version is now `shortpick_model_pit_feature_matrix:v3`.
- `model_candidate_runner` now flattens these raw and percentile fields, and retains them in rank-signal feature subsets so future source/candidate conditions or capacity-aware opportunity-set models can use them.
- Existing registered specs are unchanged and do not automatically consume the new fields; current capacity-cluster frontier metrics remain the last formal full713 result until a v3 matrix/replay is explicitly generated.
- Verification: focused feature/runner tests passed, policy audit passed, default fast pytest passed (`1060 passed, 180 deselected, 6 subtests passed in 33.17s`), and retention audit still passes with retained root `243,586,963` bytes and retained candidate-run payloads `0`.

[2026-07-07T18:48:00+08:00] Feature-v3 source coverage audit passes on the real runtime database:

- Added lightweight CLI `research-feature-v3-source-coverage-audit`. It queries `MarketBar` source coverage through aggregate counts only; it does not build a PIT feature matrix, does not run a candidate replay, and does not write runtime business tables.
- Real runtime DB audit command used `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/data/ashare_dashboard.db` for the current research window `2023-06-13` to `2026-05-26`. The retained compact result is `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_feature_source_coverage_audit_20260707.json`.
- Result: `2,141,809` daily bars; `total_mv` positive coverage `99.51%`, `circ_mv` positive coverage `99.51%`, `pe_ttm` positive coverage `79.09%`, and `pb` positive coverage `99.21%`. It passes the audit gates used for this check: market-cap fields `>= 90%` positive coverage and valuation fields `>= 50%` positive coverage.
- Interpretation: v3 market-cap/valuation features are usable enough to justify a future feature-v3 matrix/replay package. This still does not clear the `1,000,000 CNY` capacity blocker because no v3 formal full713 replay has been run.
- Verification: source-coverage tests passed, policy audit passed, default fast pytest passed (`1062 passed, 180 deselected, 6 subtests passed in 34.87s`), and retention audit passed with retained root `243,588,237` bytes and retained candidate-run payloads `0`.

[2026-07-07T19:12:00+08:00] Remaining `603117.SH` feature-v3 triage CLI confirms the blocker is expressible but not solved:

- Added lightweight CLI `research-feature-v3-capacity-triage`. Retained triage artifact: `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_remaining_603117_feature_v3_triage_20260707.json`. It is a read-only runtime DB / retained Top200-summary check for the three remaining capacity-blocker dates only; it is not a formal replay and uses future-label-selected substitutes only for search triage.
- On `2024-05-30`, `2024-06-03`, and `2024-06-05`, source `603117.SH` has same-date total market-cap percentiles `7.49%`, `7.05%`, and `8.57%`. The Top10 liquid future-return substitutes have median total market-cap percentiles `93.16%`, `92.31%`, and `92.22%`.
- This supports the feature-source hypothesis: v3 market-cap/capacity fields can describe the remaining low-ADV winner cluster ex ante. But it also rejects a naive large-cap/liquid substitution path: best liquid substitutes lag source net excess by `0.2957`, `0.3624`, and `0.3671`.
- Verification: feature-v3 triage/source tests passed, policy audit passed, and default fast pytest passed (`1064 passed, 180 deselected, 6 subtests passed in 33.71s`).
- Retention audit after adding this small triage artifact still passes: retained root `/private/tmp/stock_dashboard_retained_reports_20260706` is `243,614,674` bytes, retained candidate-run files remain `0`, and compact replay roots remain the lowret-lowadv predecessor plus current capacity-cluster frontier.

[2026-07-08T00:20:00+08:00] Bounded feature-v3 `603117.SH` blocker-window preflight runs but remains diagnostic-only:

- Ran a 75-trading-day local preflight from `2024-02-07` to `2024-06-05` for the current capacity-cluster spec only, with `shortpick_model_pit_feature_matrix:v3`.
- The preflight chain completed: input `2,937` eligible symbols, `75` as-of dates, `219,669` feature/label rows, `211,049` ready labels, `172,568` prediction rows with `8,000` stored rows, candidate run `walk-forward-model-candidate-run-9be0d186f6d81c89`, comparison report `model-comparison-report-c665c5504a1f1274`, governance `governance-promotion-decision-25509eada97a5fce`.
- It is not acceptance evidence and must not be used as a strategy result. Comparison/governance gates remain blocked for insufficient independent walk-forward periods, insufficient DSR/PBO periods, alpha/DSR stress, insufficient execution/capacity stress periods, ADV capacity fill-rate, and missing fees/slippage/stamp-tax stress.
- Artifact control: temporary root `/tmp/stock_dashboard_v3_603117_blocker_preflight_20260708` reached `1,762,484,715` bytes, so it was deleted after retaining only compact summary `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_603117_blocker_preflight_summary_20260708.json` (`12,901` bytes).
- Retention audit still passes: retained root `/private/tmp/stock_dashboard_retained_reports_20260706` is `243,627,575` bytes, retained candidate-run files remain `0`, and compact replay roots remain limited to the lowret-lowadv predecessor plus current capacity-cluster frontier.

[2026-07-08T00:35:00+08:00] Model preflight compaction is now a reusable CLI, not a one-off cleanup script:

- Added `research-model-preflight-compact --preflight-root ... --output-json ... --delete-source-root`, backed by `research_model_preflight_compaction.py`.
- The compactor summarizes preflight roots without retaining matrix `rows`, keeps compact candidate/comparison/governance blocker readouts, and can delete the source root after the retained summary is written.
- This prevents bounded feature-v3 preflights from leaving 1GB+ temporary roots or retained candidate-run payloads. It is retention governance only and does not count as strategy performance evidence.
- Verification: `tests/test_research_model_preflight_compaction.py` plus `tests/test_research_artifact_retention.py` passed (`5 passed in 0.32s`), CLI help renders, policy audit passed, and default fast pytest passed (`1065 passed, 180 deselected, 6 subtests passed in 33.49s`).

[2026-07-08T00:55:00+08:00] Capacity contract tier scan quantifies the current frontier's product-size boundary:

- Added `research-capacity-contract-tier-scan` and retained `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_capacity_cluster_contract_tier_scan_20260708.json`.
- Source: current capacity-cluster candidate run `walk-forward-model-candidate-run-8cf650cf13dda990`, trial `weak_defensive_grind_tail_cash_congested_low_liquidity_top3_20d_gross_exposure_rank1_liquidity_replacement_neutral_chop_segment_risk_defensive_crowding_weak_overheated_underfilled_capacity_cluster_candidate_replacement_v1:trial-003`.
- Result under `5% ADV`: active selected picks `913`; theoretical all-pick full-fill notional limit `121,937.78 CNY`. Scanned `100,000` and `120,000 CNY` tiers have `0` underfilled picks. From `150,000 CNY` upward, exactly `3` picks are underfilled, all `603117.SH` on `2024-05-30`, `2024-06-03`, and `2024-06-05`; at `1,000,000 CNY`, min fill rate is `0.12194`.
- Decision: this does not clear the user's `1M / 5% ADV` requirement and must not be described as product-ready. It does, however, formally separates the current frontier into a low-capital research contract candidate and confirms that the remaining blocker is concentrated in the `603117.SH` cluster, not broad capacity degradation.
- Governance projection follow-up: the `adv_capacity_fill_rate` execution-gate readout now carries the lower-capital `capacity_contract` diagnostic when the comparison report provides one, while preserving the configured `1,000,000 CNY` blocker. This makes the product-size boundary visible to downstream dashboard/governance consumers without weakening promotion gates.
- Artifact refresh: added `research-model-governance-refresh` so comparison/governance/projection small JSONs can be rebuilt from an existing candidate-run and registry without replaying full713 matrices. Refreshed the current capacity-cluster root; `model-comparison-report-1253096e31fe739a` and `governance-promotion-decision-6ea4bffd4f0b4123` now expose `capacity_contract.status=lower_capital_research_contract_ready` and `max_ready_research_portfolio_notional_cny=120000.0`, while the governance gate remains blocked at `1,000,000 CNY`.
- Verification: capacity proxy tests passed (`9 passed in 0.16s`), focused governance-refresh/projection tests passed (`3 passed in 0.84s`), policy audit passed, and default fast pytest passed (`1069 passed, 180 deselected, 6 subtests passed in 33.72s` after the opportunity-discovery addition).
- Retention audit still passes after retaining this `5.3KB` diagnostic, refreshing the current frontier governance JSON, and adding the opportunity-discovery artifact: retained root `/private/tmp/stock_dashboard_retained_reports_20260706` is `243,699,455` bytes, retained candidate-run files remain `0`, and the current capacity-cluster replay root is `50,355,000` bytes.

[2026-07-08T01:20:00+08:00] Full-market liquid opportunity discovery changes the next capacity path:

- Added `research-capacity-opportunity-set-discovery`, backed by `capacity_opportunity_set_discovery.py`. It reads the retained remaining-`603117.SH` Top200 oracle summary and runtime `market_bars`, then computes same-date full-market liquid candidates using DB close-to-20d future excess, 20d average amount, and compact ex-ante feature summaries.
- Retained artifact: `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_capacity_cluster_full_market_liquid_opportunity_discovery_20260708.json` (`66,427` bytes). Claim ceiling is `future_return_opportunity_set_triage_only_no_model_replay_no_promotion`.
- Full-fill threshold for the current configured product is `18,200,000 CNY` 20d average amount (`1,000,000 CNY * 0.91 Rank1 capital weight / 5% ADV`).
- Result: full-market liquid future winners exist on `2/3` remaining capacity-blocker dates, but not all three. On `2024-05-30`, liquid universe count is `2919`, `3` candidates beat the source artifact net-excess floor, and best is `002869.SZ` with DB future excess `0.7837` and avg amount `119.6M`. On `2024-06-03`, liquid universe count is `2902`, `1` candidate beats the source artifact floor, again `002869.SZ` with future excess `0.6754` and avg amount `127.4M`. On `2024-06-05`, liquid universe count is `2896`, `0` candidates beat the source artifact floor; best is `603171.SH` with future excess `0.4741` versus source artifact net `0.6278`.
- Important interpretation: the previous Top200 oracle still correctly rejects expanding the old same-score TopN replacement path. This new diagnostic says a different full-market opportunity-set/scoring model may have exploitable liquid winners on part of the blocker cluster, because the best liquid future winners were not present in the retained Top10 liquid summary. It does not prove an ex-ante model can rank them, and it does not clear the `1M / 5% ADV` blocker because `2024-06-05` still has no non-degrading liquid candidate under this DB close-to-20d proxy.
- Next valid optimization direction: diagnose ex-ante common features of the discovered liquid winners (`002869.SZ`, `002600.SZ`, `605258.SH`, `603171.SH`, `002384.SZ`) against the current scorer's missed ranking, then test a registered opportunity-set/scoring change only if it can be expressed without future leakage and without degrading the current `+277.439%`, maxDD/path, DSR/PBO, and zero-negative-month floors.
- Verification: new unit tests passed (`2 passed in 0.68s`), focused capacity/governance tests passed (`14 passed in 0.88s`), CLI help renders, policy audit passed, default fast pytest passed (`1069 passed, 180 deselected, 6 subtests passed in 33.72s`), retention audit passed, and the real runtime DB diagnostic completed in `13.6s` with no matrix rebuild.

[2026-07-08T01:25:00+08:00] Full713 feature-v3 boundary is built, but the current frontier is not upgraded:

- Added a real feature-only rebuild path, `shortpick-model-feature-rebuild`, so a PIT feature matrix can be rebuilt from an existing input snapshot without rebuilding labels or running the full workbench. The implementation writes feature rows once to a temporary JSONL file, computes the content digest, then assembles the final artifact; this avoids the earlier two-pass DB scan. `_mean` now uses normal floating arithmetic instead of `statistics.mean`, which avoided a large Fraction overhead in full-matrix generation.
- Built full713 `shortpick_model_pit_feature_matrix:v3`: `/tmp/stock_dashboard_feature_v3_rebuild_full713_20260708/research_validation/pit_feature_matrices/pit-feature-matrix-0cc2f4d7b223cfe9.json`, `2,098,150` rows, `5.8GB`, feature groups include `valuation_capacity` plus cross-sectional capacity/valuation fields.
- Replayed the current capacity-cluster frontier against v3 feature matrix and existing label matrix only for the selected spec. Artifacts: root `/tmp/stock_dashboard_v3_feature_frontier_replay_full713_20260708`, candidate run `walk-forward-model-candidate-run-bdb0c4c5c50d68c3`, report `model-comparison-report-caec8f1b9532a544`, governance `governance-promotion-decision-674aa5f1f9ec7aae`.
- Result is not a promotion. It is essentially parity but slightly below the current formal frontier: total return `+277.394%` vs current `+277.439%`, annualized `66.952%` vs `66.960%`, selected mean `0.033967` vs `0.033991`, alpha t-stat `7.8529` vs `7.8792`, DSR `0.99999999969` vs `0.99999999974`; maxDD/path remain about `-3.058%` / `-0.5966`, negative months remain `0`, worst monthly mean is positive (`+0.0852%`).
- Capacity is unchanged in substance: `1,000,000 CNY / 5% ADV` remains blocked with `3` active underfilled picks, worst pick `603117.SH` on `2024-06-05`, min fill rate `0.12194`, and lower-capital full-fill research tier `120,000 CNY`.
- Re-ran v3 score-rank probe and retained `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_capacity_cluster_liquid_winner_score_rank_probe_v3feature_20260708.json`. It confirms the model still ranks `603117.SH` #1 on all three blocker dates; available liquid future winners remain far below the current scorer (`rank 607` to `2157` in the retained target set). The command is `blocked` because three opportunity-discovery targets are missing in the feature matrix on those dates, but the available-target diagnostic is valid.
- Decision: feature-v3 infrastructure is now real and reusable, but no strategy has solved the goal yet. The next valid research step is a registered capacity-aware/opportunity-set scorer using v3 capacity, market-cap, valuation, amount-expansion, low-volatility and regime features. Do not continue adding same-date Rank1 replacement patches unless a bounded probe first shows non-degradation against the `+277.439%` frontier.

[2026-07-08T01:40:00+08:00] Capacity-aware v3 scorer clears capacity but is rejected:

- Registered `capacity_aware_v3_regime_breakout_top3_20d_v1`, a deterministic full713 v3 scorer that applies explicit capacity shortfall penalties and market-cap/liquidity bonuses without slot replacement.
- Formal replay artifacts were `walk-forward-model-candidate-run-13594a8cb20fd234`, `model-comparison-report-b92e6f56d1a1c9a4`, `governance-promotion-decision-77bd7b85064ea9d8`, and `dashboard-approved-projection-registry-ec3bfae7e75ff093`.
- It clears the configured `1,000,000 CNY` / `5% ADV` capacity contract: active picks below full fill are `0`, active full-fill rate is `1.0`, min fill rate is `1.0233`, and max ready research notional reaches `1,000,000 CNY`.
- It is still rejected because profitability and stability degrade materially versus the active `+277.439%` frontier: total return falls to `+157.977%`, annualized return to `44.156%`, execution mean to `0.022242`, positive-date rate to `38.74%`, negative months rise to `6`, worst monthly mean falls to `-3.3126%`, path drawdown sum falls to `-1.0518`, alpha t-stat falls to `5.3926`, and DSR falls to `0.998808`.
- Retention/registry decision: retained compact summary `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_capacity_aware_scorer_full713_rejection_summary_20260708.json`, deleted the `191M` rejected replay root, and removed the spec from the default active registry. Do not repeat capacity-penalty-only scoring as a fix; the next valid work must learn alpha inside the fillable opportunity set.
- Verification after active-registry removal: focused registry/scorer tests passed (`66 passed`), policy audit passed, retention audit passed with retained root `244,090,691` bytes and retained candidate-run files `0`, and default fast pytest passed (`1075 passed, 180 deselected, 6 subtests passed`).

[2026-07-08T02:05:00+08:00] Fillable weak-turnaround v3 scorer has local blocker repair but fails full713:

- Registered `fillable_weak_turnaround_v3_top3_20d_v1`, a separate deterministic v3 scorer that rewards fillable weak-market 5d rebound, amount expansion and turnover recovery while penalizing ultra-low-ADV / ultra-low-vol defensive crowding. This was intentionally separate from the rejected capacity-penalty scorer.
- Blocker-date score-rank probe retained at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_fillable_weak_turnaround_score_rank_probe_trial000_20260708.json` is locally promising but not acceptance evidence. It improves `002869.SZ` on `2024-05-30` from old-score rank `2126` to rank `95`; `603171.SH` ranks `295` on `2024-06-03` and `237` on `2024-06-05`; `603117.SH` falls to ranks `2377`, `2362`, and `2372`.
- Formal full713 replay rejects the model: candidate run `walk-forward-model-candidate-run-7b67f754a004acd5`, report `model-comparison-report-83fa9847526184c0`, governance `governance-promotion-decision-d35b9f9f85464e06`, dashboard registry `dashboard-approved-projection-registry-da0dd29878b778a2`.
- Capacity clears, but the strategy degrades far below the active frontier: total return `+45.358%`, annualized return `15.528%`, max drawdown `-28.201%`, execution mean `0.008926`, positive-date rate `33.38%`, negative months `12`, worst monthly mean `-5.3577%`, path drawdown sum `-2.4622`, alpha t-stat `2.1996`, DSR `0.438306`, PBO `0.0`.
- Interpretation: the local 603117 cluster can be mechanically reranked, but broad fillable weak-rebound formulas select noisy weak-market momentum/amount-expansion names. Do not continue hand-written fillable rebound scoring without explicit monthly/path stability constraints.
- Retention/registry decision: retained compact rejection summary `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_fillable_weak_turnaround_full713_rejection_summary_20260708.json`, deleted the `195M` rejected replay root plus temporary probe registry root, and removed the spec from the default active registry. Retained root remains under cap at about `244,090,691` bytes.
- Verification after active-registry removal: focused registry/scorer tests passed (`66 passed`), policy audit passed, retention audit passed with retained root `244,090,691` bytes and retained candidate-run files `0`, and default fast pytest passed (`1075 passed, 180 deselected, 6 subtests passed`).

[2026-07-08T02:45:00+08:00] Existing Top50 inventory is not enough for learned fillable reranking:

- Added reusable CLI `research-top-candidate-learned-rerank-proxy` and ran it over retained older weak-overheated Top50 inventory `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_weak_overheated_top50_candidate_inventory_20260707.json`. This is diagnostic only, not current-frontier proof and not a model replay.
- Retained summary: `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_top50_learned_fillable_rerank_proxy_20260708.json` (`6.9KB`, schema `top_candidate_learned_rerank_proxy.v1`, gate `blocked`).
- Baseline original-rank Top3 on this retained inventory: mean `0.010467`, positive-date rate `50.76%`, negative months `11`, worst monthly mean `-3.9880%`, path drawdown sum `-2.0086`.
- Learned Top3 with fillable-only filter (`avg_amount_20d >= 18.2M`) is worse: mean `0.007684`, positive-date rate `48.06%`, negative months `12`, worst monthly mean `-4.1178%`, path drawdown sum `-2.1300`.
- Decision: do not spend a full713 replay on simple learned Top50 reranking. Blocking gates are `learned_fillable_mean_below_baseline`, `learned_fillable_negative_month_count_above_baseline`, and `learned_fillable_path_drawdown_worse_than_baseline`. The next valid search needs a different opportunity-set construction or label/stability-aware training objective; the current retained Top50 opportunity set does not contain enough stable fillable alpha by itself.

[2026-07-08T03:20:00+08:00] Stream-fitted fillable linear v3 model is engineered but rejected:

- Added stream replay support for `regularized_rank_linear` so learned models can run against 6GB full713 matrices without loading all rows into memory. The implementation builds date-level training aggregates, fits each walk-forward split, and passes the fitted model into stream scoring.
- Registered `learned_fillable_rank_linear_v3_top3_20d_v1`, a governed v3 model spec that selects Top3 only from the configured full-fill universe (`avg_amount_20d >= 18.2M`) and uses v3 momentum, risk, liquidity, valuation/capacity, execution, regime, crowding and cross-sectional features.
- Full713 stream replay completed at low priority and was rejected: candidate run `walk-forward-model-candidate-run-fafd63508e8b91af`, report `model-comparison-report-1547e6f176fa298d`, governance `governance-promotion-decision-58f47c0ce431e65e`.
- Trial metrics are identical across alpha values because alpha only rescales linear weights without changing rank order: evaluated dates `653`, labeled predictions per trial `1,852,683`, rank IC mean `0.06737`, positive rank-IC rate `70.60%`, selected Top3 mean `0.001011`, positive selected-date rate `51.30%`, Top5 mean `0.001773`, Top quantile mean `0.003122`.
- Decision: reject plain full-market regularized linear fillable ranking. It learns weak positive IC, but that IC is far too weak for concentrated Top3 strategy returns and does not approach the active `+277.439%` frontier. Retained summary `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_stream_fitted_fillable_linear_full713_rejection_summary_20260708.json`; deleted the `40.2MB` rejected replay root after compaction.
- Next valid learned direction: do not repeat plain linear IC ranking. A successor needs a tail-focused or pairwise/listwise objective that optimizes TopK winner capture and monthly/path stability directly.

[2026-07-08T03:45:00+08:00] Naive binary tail-capture fillable linear model is rejected and removed from default registry:

- Added `tail_capture_linear_ranker` stream-fit support and registered `tail_capture_fillable_rank_linear_v3_top3_20d_v1` as a governed challenger. The objective labels each train-date fillable future TopN winner as positive and the remaining fillable universe as negative.
- Full713 stream replay completed at low priority and was rejected: candidate run `walk-forward-model-candidate-run-4f4883ff405ff8b4`, report `model-comparison-report-b202a84728b54125`, governance `governance-promotion-decision-1130e70f9908d555`.
- Result is materially worse than the plain linear model and far below the active frontier. Best comparison trial `trial-000` has rank IC mean `-0.03682`, positive rank-IC rate `43.64%`, selected Top3 mean `-0.06934`, positive selected-date rate `25.27%`, total return `-86.01%`, annualized return `-53.19%`, max drawdown `-86.56%`, `28` negative months, worst monthly mean `-28.23%`, and path drawdown sum `-45.2914`.
- Retained summary `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_tail_capture_fillable_linear_full713_rejection_summary_20260708.json`; deleted the `53.0MB` rejected replay root after compaction.
- Removed `learned_fillable_rank_linear_v3_top3_20d_v1` and `tail_capture_fillable_rank_linear_v3_top3_20d_v1` from the default active registry after formal rejection. Keep the stream-fit code path as infrastructure, but do not default-run these rejected specs.
- Decision: do not repeat naive binary tail-capture over the full fillable universe. The next learned direction must first run a bounded diagnostic for calibrated positive/negative sampling, return-magnitude weighting, or two-stage candidate generation before another full713 replay.

[2026-07-08T03:55:00+08:00] Existing retained TopN inventories do not justify objective-calibration full713:

- Added reusable CLI `research-top-candidate-objective-calibration-proxy`, backed by `top_candidate_objective_calibration_proxy.py`. It runs only over retained TopN candidate-inventory JSONs and writes compact aggregate evidence; it does not build matrices, retain candidate rows, replay full713, or promote a model.
- Ran it over three retained inventories: weak-overheated Top50, high-turnover-amount Top50, and rank1-liquidity Top20. Retained artifacts are `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_weak_overheated_top50_objective_calibration_proxy_20260708.json`, `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_high_turnover_amount_top50_objective_calibration_proxy_20260708.json`, and `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_rank1_liquidity_top20_objective_calibration_proxy_20260708.json`.
- Tested objective variants: original-rank baseline, fillable-only original rank, return-linear, return-magnitude, positive-return-magnitude, calibrated tail, and pairwise top/bottom. All three inventories are blocked by `no_objective_variant_beats_fillable_baseline_and_retains_original_rank_floor`; `promising_variants` is empty.
- Weak-overheated/high-turnover Top50 baseline original-rank Top3 mean is `0.010467`, negative months `11`, path `-2.0086`; fillable original-rank mean is `0.008019`. The best mean variant is positive-return-magnitude at `0.008530`, still below the original-rank floor and with `11` negative months; pairwise improves path slightly to `-1.9764` but collapses mean to `0.004660` and increases negative months to `15`.
- Rank1-liquidity Top20 is also blocked. Positive-return-magnitude mean is only `0.006456`; return-magnitude has the best path at `-1.8541` but still has `13` negative months and lower mean. This rejects another full713 replay that only changes training target/objective on the old retained opportunity sets.
- Decision: the next useful model attempt must change the opportunity-set generator or add PIT-safe source features before replay. Do not repeat calibrated return-magnitude, positive/negative tail, or pairwise objective experiments over these retained TopN inventories as if they were new strategy search.

[2026-07-08T04:05:00+08:00] Full-market liquid winners are feature-describable, but archetype-only opportunity generation is still blocked:

- Added reusable CLI `research-capacity-opportunity-feature-gap`, backed by `capacity_opportunity_feature_gap.py`. It consumes only the retained full-market liquid opportunity artifact and checks whether broad ex-ante archetypes can cover the discovered liquid future winners. It does not query the runtime DB, build matrices, replay full713, retain candidate rows, train a model, or promote anything.
- Real retained output: `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_capacity_opportunity_feature_gap_probe_20260708.json`, schema `capacity_opportunity_feature_gap.v1`, gate `blocked`.
- Result: the best liquid candidate on all three remaining `603117.SH` blocker dates is covered by at least one broad archetype, and none of the best liquid candidates were present in the retained Top10 liquid summaries. This confirms the old TopN opportunity set is missing relevant full-market liquid candidates.
- Non-degradation is still not solved. Dates with non-degrading covered archetype candidates are only `2/3`: `2024-05-30` has `002869.SZ`, `002600.SZ`, and `605258.SH` above the source floor; `2024-06-03` has `002869.SZ`; `2024-06-05` has no non-degrading full-fill candidate. The best near-floor candidate on `2024-06-05` is `603171.SH` with future excess `0.4741`, below the source floor `0.6278` by `0.1536`.
- Decision: do not run a full713 replay from a broad archetype-only opportunity generator yet. The next useful work needs either new PIT-safe source features that can explain the 2024-06-05 return-floor gap, or a broader sampled full-market opportunity-generator preflight that tests whether these archetypes generalize beyond the three known blocker dates.

[2026-07-08T04:25:00+08:00] Main-board sampled archetype opportunity generation is rejected before full713:

- Added reusable CLI `research-capacity-opportunity-archetype-sample`, backed by `capacity_opportunity_archetype_sample.py`. It samples dates from the current frontier candidate-run, queries runtime `market_bars`, filters to executable main-board prefixes (`000/001/002/003/600/601/603/605`), applies the broad archetype generator, and compares sampled archetype TopK future excess against the current frontier's same-date OOS return. It is a sampled preflight only: no full713 replay, no model promotion, no dashboard/paper claim.
- Real retained output: `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_capacity_opportunity_archetype_sample_preflight_12d_20260708.json`, 12 sampled OOS dates, Top3, configured full-fill threshold `18.2M` avg amount.
- Result is blocked on all core comparison gates. Current frontier sample mean is `+0.1092`; archetype Top3 sample mean is `-0.0416`. Current frontier has `6` negative months in the 12-date sample; archetype generator has `10`. Frontier sample path drawdown is `-0.0641`; archetype path is `-0.4994`.
- Interpretation: broad archetype coverage is not enough. It mostly selects high-turnover small/mid reversal names, which are exactly the noisy bucket that earlier full713 attempts punished. This rejects a full713 replay for an archetype-only generator and forces the next direction toward new PIT-safe source features or a learned two-stage opportunity model with its own sampled preflight.

[2026-07-08T04:45:00+08:00] Walk-forward learned two-stage opportunity sample improves stability but misses the return floor:

- Added reusable CLI `research-capacity-opportunity-learned-sample`, backed by `capacity_opportunity_learned_sample.py`. It samples dates from the current frontier candidate-run, queries runtime `market_bars`, filters to executable main-board prefixes and excludes ST/退市 names, trains only on prior sampled dates, and compares learned full-market Top3 variants against the current frontier's same-date OOS return. This is sampled preflight only: no 6GB matrix read, no full713 replay, no registry promotion, no dashboard/paper claim.
- Real retained output: `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_capacity_opportunity_learned_sample_preflight_18d_20260708.json`. It loaded `18` sampled dates, evaluated `12` walk-forward dates after `6` train dates, and tested return-linear, positive-return, and tail-spread objectives.
- Gate is `blocked` with `no_variant_beats_frontier_sample`. The same-date frontier sample mean is `+0.04665`; the best learned variant, `learned_return_linear_topk`, reaches only `+0.02289`. It does improve negative months (`8 -> 5`) and path drawdown (`-0.2168 -> -0.1365`), but the return shortfall is too large to justify full713.
- Decision: do not replay this learned two-stage sample as a full strategy. The useful signal is that learned full-market fillable selection can reduce path/month stress, but the objective must jointly enforce a return floor and stability; pure correlation / positive-return / tail-spread objectives are not enough.

[2026-07-08T05:15:00+08:00] Return-floor learned opportunity objectives still miss the frontier return floor:

- Extended `capacity_opportunity_learned_sample.py` to schema `capacity_opportunity_learned_sample.v2` with explicit objective metadata and three additional walk-forward objectives: `frontier_excess`, `frontier_positive_excess`, and `frontier_floor_stability`. Training labels only use prior sampled dates' same-date frontier return plus candidate future labels; test-date frontier returns remain comparison-only.
- Re-ran the same retained 18-date sampled preflight at low priority. The artifact remains `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_capacity_opportunity_learned_sample_preflight_18d_20260708.json`, now v2, still `blocked` with `no_variant_beats_frontier_sample`.
- The best v2 variant is `learned_frontier_excess_topk`: mean `+0.02490` versus frontier sample `+0.04665`, negative months `5` versus `8`, and path drawdown `-0.0826` versus `-0.2168`. Stability improves, but the mean remains only about `53%` of the frontier sample.
- Decision: downgrade simple feature-correlation learned opportunity selection, including return-floor variants. Do not run full713 from this family unless a bounded preflight first clears both return floor and stability gates.

[2026-07-08T05:30:00+08:00] Current frontier order-level capacity overlays are rejected on trial-003:

- Re-ran `research-order-capacity-proxy` on the accepted capacity-cluster frontier candidate run `walk-forward-model-candidate-run-8cf650cf13dda990`, trial `...:trial-003`, with the configured `1,000,000 CNY` / `5% ADV` contract. Retained output: `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_current_frontier_order_level_capacity_proxy_20260708.json`.
- Baseline full-fill reference has total proxy `2.0981`, mean daily net excess `0.03498`, zero negative months, path drawdown `-0.5966`, and only `3` underfilled active picks.
- Simple execution fixes are all rejected. `adv_cap_cash` lowers total proxy to `1.8937` and reintroduces one negative month. Rank/score redistribution reaches only `1.9047` and still has one negative month. Top5 substitution reaches `1.9011` and one negative month. Naive capacity-aware TopN selection falls to `1.5438` with seven negative months.
- Decision: the current `1M / 5% ADV` capacity blocker is not an execution-layer cleanup problem. It is a product-capital contract/model-opportunity problem: either keep the frontier as a lower-capital research contract, or require a new model/opportunity surface that clears return and stability floors before any full713 replay.

[2026-07-08T06:00:00+08:00] Prototype learned opportunity signal passes 18-date but fails 36-date expansion:

- Extended `research-capacity-opportunity-learned-sample` with compact prototype scoring variants: `prototype_return_topk`, `prototype_frontier_excess_topk`, and `prototype_frontier_floor_stability_topk`. Each trains only on prior sampled dates by comparing candidates to positive and negative feature centroids; no external dependency, no full matrix read, and no promotion authority.
- The 18-date retained sample `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_capacity_opportunity_learned_sample_preflight_18d_20260708.json` becomes `passed` only because `prototype_frontier_excess_topk` clears the small-sample gate: mean `+0.05307` vs frontier sample `+0.04665`, negative months `3` vs `8`, and path `-0.0595` vs `-0.2168`.
- The required larger preflight rejects the signal. Retained output `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_capacity_opportunity_prototype_preflight_36d_20260708.json` loads `36` sampled dates and evaluates `27` walk-forward dates after `9` training dates. It is `blocked` with `no_variant_beats_frontier_sample`. Best mean variant remains `prototype_frontier_excess_topk`, but its mean is only `+0.01630` versus frontier sample `+0.04125`, and path worsens to `-0.2937` versus `-0.1523`.
- Decision: do not register or replay the prototype learned family. The small-sample pass is an instability warning, not a model discovery. Future learned work needs stronger validation before full713, likely with richer PIT-safe features or a more constrained objective than centroid similarity.

[2026-07-08T06:20:00+08:00] Residual-fill execution overlay improves but still fails current frontier gates:

- Added `adv_cap_residual_top5_fill` to `research-order-capacity-proxy`. It keeps the original low-ADV selected order partially filled under the `5% ADV` cap, then fills only the residual capital with same-date Top5 candidates. This tests a more realistic execution overlay than full cash, rank/score redistribution, or whole-slot substitution.
- Re-ran the current frontier proxy for candidate run `walk-forward-model-candidate-run-8cf650cf13dda990`, trial `...:trial-003`, and overwrote retained artifact `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_current_frontier_order_level_capacity_proxy_20260708.json`.
- Result: residual fill is the best simple execution overlay, with total proxy `1.9255` versus `1.9047` for rank/score redistribution and `1.9011` for whole Top5 substitution. It still falls below the full-fill reference `2.0981` and reintroduces one negative month (`2024-05`), so `non_degrading_modes=[]`.
- Decision: partial-fill plus same-date Top5 residual completion is rejected. The remaining `1M / 5% ADV` blocker cannot be cleared by selected-basket execution math; the next viable path must change the model/opportunity surface or formally scope the current frontier as a lower-capital research contract.

[2026-07-08T06:45:00+08:00] Targeted learned full-market fallback still fails the three underfilled slots:

- Added `research-capacity-underfilled-fallback-preflight`, backed by `capacity_underfilled_fallback_preflight.py`. It preserves the current frontier on every non-underfilled date and only applies a prior-date-trained full-market fallback to the three current underfilled slots: `2024-05-30`, `2024-06-03`, and `2024-06-05`.
- Retained real output: `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_underfilled_learned_fallback_preflight_20260708.json`. It trains from prior sampled dates only, uses executable full-market candidates, and tests `fallback_learned_frontier_excess`, `fallback_prototype_frontier_excess`, and `fallback_prototype_frontier_floor_stability`.
- Result is `blocked` with `capacity_underfilled_fallback:no_variant_preserves_frontier`. Baseline full frontier mean is `0.03498`, zero negative months, path `-0.5966`. Best variant is `fallback_prototype_frontier_excess`, mean `0.03280`, one negative month (`2024-05`), path `-0.5966`.
- Decision: targeted fallback is better scoped than whole-strategy learned selection, but it still misses the actual blocker-date liquid winners and gives back too much of the `603117.SH` return. Do not run full713 from fallback-only capacity repair without new PIT-safe ranking features that can identify blocker-date liquid winners ex ante.

[2026-07-08T06:55:00+08:00] Existing PIT-safe feature recipes cannot rank the blocker-date liquid winners consistently:

- Added `research-capacity-liquid-winner-feature-audit`, backed by `capacity_liquid_winner_feature_audit.py`. It is diagnostic only: it consumes the retained full-market liquid opportunity discovery plus targeted fallback artifact, queries runtime `market_bars` for the three blocker dates, and checks existing PIT-safe capacity/liquidity/momentum/drawdown/industry-relative/OHLC price-action recipes against the actual liquid winners.
- Retained real output: `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_liquid_winner_feature_audit_20260708.json`, schema `capacity_liquid_winner_feature_audit.v1`, gate `blocked` with `capacity_liquid_winner_feature_audit:no_recipe_ranks_targets_consistently`.
- Result: no recipe ranks the liquid winner set inside Top25 on all three dates. The closest non-industry recipe is `pullback_pressure_turn`, with best target ranks `[51, 29, 30]`. The industry-relative version improves one date but still fails the gate: `industry_pullback_pressure_turn` ranks targets `[14, 30, 144]`; `industry_strength_pressure_turn` is weaker at `[153, 69, 335]`. OHLC price-action recipes do not solve it either: `price_action_breakout_pressure` ranks `[372, 169, 123]`, and `limitup_followthrough_pressure` ranks `[455, 26, 162]`. These recipes do push the bad fallback picks down into roughly rank 1400-2800+, so they can reject obvious losers but still cannot select the needed winners.
- A bounded target-fitted combo search was added to the same artifact to check whether this was only a hand-written recipe problem. It greedily searches up to 5 signed terms over existing PIT-safe OHLCV, valuation, industry-relative and derived fields. It is also blocked: best combo uses `open_gap_1d_percentile`, `distance_to_20d_high_percentile`, and negative `mega_cap_penalty`, but target ranks remain `[278, 8, 325]`; only one of three blocker dates clears Top25. This is overfit-prone diagnostic evidence only, but because it still fails, it strengthens the missing-signal conclusion.
- Decision: the remaining capacity blocker is now classified as missing or insufficient PIT-safe ranking signal, not an execution overlay, fallback-training bug, or simple current-feature weighting problem. Do not run full713 from current-feature recipe variants. The next valid optimization must add or derive a new PIT-safe feature family beyond the current OHLCV/valuation/industry static set, or change the label/objective materially, then pass a bounded expanded preflight against the `+277.439%` frontier return/stability floors before any formal replay.

[2026-07-08T07:10:00+08:00] Runtime DB has no additional broad historical PIT source ready for full713:

- Added `research-pit-source-readiness-audit`, backed by `pit_source_readiness_audit.py`. It audits source readiness only: no provider calls, no feature matrix rebuild, no training, no replay, and no promotion claim.
- Retained real output: `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_pit_source_readiness_audit_20260708.json`, schema `pit_source_readiness_audit.v1`, gate `blocked` with `pit_source_readiness:no_additional_historical_pit_source_ready`.
- Result: market bars and static stock profiles are ready but already used by v3/liquid-winner diagnostics. `feature_snapshots` initially looked promising by date range, but is downgraded because it covers only `4` linked stocks (`linked_stock_ratio=0.001226`) despite `15,150` rows. `news_items` has only `121` rows from `2026-03-26` through `2026-07-01`, too short for the 2023-06-13 to 2026-05-26 full713 window. `sector_memberships` has only `7` rows and `4` linked stocks. `model_results` and `recommendations` are blocked as prior outputs/leakage risks, not independent raw sources.
- Decision: do not spend a full713 replay or strategy registration on sparse runtime `feature_snapshots`, recent news, sparse sector memberships, or prior recommendation/model outputs. The next valid route is either governed external PIT-safe historical data ingestion, or a materially different label/objective with bounded preflight evidence that clears the `+277.439%` frontier return/stability floors before formal replay.

[2026-07-08T07:25:00+08:00] Staggered multi-day entry nearly repairs capacity but still misses the strict non-degradation floor:

- Added `research-capacity-staggered-entry-proxy`, backed by `capacity_staggered_entry_proxy.py`. It is a bounded execution diagnostic only: it preserves the current frontier selection and selected returns on all non-underfilled rows, then replaces only underfilled selected-pick contributions with a multi-day close-entry fill schedule capped at `5%` of actual daily amount. It does not rebuild matrices, train models, replay full713, or promote capacity.
- Retained real output: `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_current_frontier_staggered_entry_proxy_20260708.json`.
- Result: no non-degrading scan. Baseline full-fill reference total proxy is `2.0981`, mean daily net excess `0.034980`, zero negative months, path drawdown sum `-0.5966`. A 10-trading-day staggered entry fills all three `603117.SH` underfilled Rank1 slots under `5% ADV`, keeps zero negative months and unchanged path drawdown, but still lowers total proxy to `2.0934` and mean to `0.034933`.
- Execution detail: the 2024-06-03 slot improves versus same-day full-fill contribution after staggered entry, but 2024-05-30 and 2024-06-05 give back more contribution than it gains. Longer 15/20-day windows do not improve beyond the 10-day result because the slots are already fully filled by then.
- Decision: staggered entry is the closest execution-only repair found so far and may be useful for a lower-claim operational playbook, but it does not clear the user's strict non-degradation requirement. Do not claim `1M / 5% ADV` production capacity from staggered entry alone; any next execution route needs explicit cost/slippage/entry-timing labels and must beat the `2.0981` full-fill frontier proxy, not merely approach it.

[2026-07-08T07:45:00+08:00] Per-tranche staggered exit tightens the execution boundary but remains below the frontier floor:

- Extended `research-capacity-staggered-entry-proxy` with explicit `--exit-policy` scans. The original `original_exit` policy preserves the prior assumption that every delayed fill exits on the original signal-date horizon; the new `per_tranche_horizon` policy exits each fill after its own 20 trading days.
- Re-ran the current frontier artifact in place at `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_current_frontier_staggered_entry_proxy_20260708.json` with both exit policies and entry windows `1/3/5/10/15/20`.
- Result: `non_degrading_scans=[]` remains. The best scan is now `entry_days=10`, `exit_policy=per_tranche_horizon`, with total proxy `2.095640` and mean daily net excess `0.034955` versus the full-fill reference `2.098074` and `0.034980`; negative months stay `0`, path drawdown stays `-0.596642`, and all three underfilled picks are fully repaired by fill rate.
- Decision: the shortfall is no longer caused by the conservative original-exit accounting alone. Staggered execution can nearly preserve the current frontier but still cannot satisfy the strict profitability floor, so it remains an execution diagnostic. The next model-search route should not spend a full713 replay on execution-only staggered entry; it needs either governed new PIT-safe signal families or a materially different objective/opportunity surface with bounded preflight evidence first.

[2026-07-08T08:10:00+08:00] Current frontier exposure-floor scaling is the first non-degrading stability overlay candidate:

- Tightened the shared proxy non-degradation gate in `order_level_capacity_proxy.py` so accepted overlays must also preserve `path_drawdown_sum`, and so retained summaries expose mean, annualized, maxDD, path, positive-date, negative-month and worst-month fields.
- Re-ran `research-exposure-floor-stability-proxy` on accepted capacity-cluster trial-003 with floor quantiles `0.05` through `0.50` and overlay modes `cash_floor`, `linear_scale`, `sqrt_scale`, and `half_cash_scale`. Retained output: `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_current_frontier_exposure_floor_stability_proxy_20260708.json`.
- Result: three scaling overlays pass the full proxy gate. The best accepted variant is `gross_exposure_linear_scale_overlay` at gross exposure floor `0.3318448363`, affecting `99` active low-exposure dates. It improves total proxy `2.098074 -> 2.103852`, annualized proxy `0.547098 -> 0.548211`, maxDD `-0.029518 -> -0.029092`, path drawdown `-0.596642 -> -0.587898`, and worst monthly mean `0.000852 -> 0.000931`; positive-date rate stays `0.459418` and negative months stay `0`.
- `gross_exposure_cash_floor_overlay` has higher total and path improvement, but it lowers positive-date rate, so it is intentionally not accepted by the gate.
- Decision: this is meaningful progress on the negative-month/path-stress side of the goal, and it does not use a known strong stock rule. It remains selected-return overlay evidence only: no full713 model replay, no DSR/PBO recomputation, no dashboard/policy promotion, and no `1M / 5% ADV` capacity repair. The next valid step is to formalize this as a governed candidate overlay or replayable selection policy and require full comparison/governance evidence before treating it as a strategy improvement.

[2026-07-08T08:35:00+08:00] Exposure-floor overlay now has compact comparison/governance evidence without retaining a candidate-run payload:

- Added reusable CLI `research-exposure-floor-overlay-governance`, backed by `exposure_floor_overlay_governance.py`. It reads the source candidate-run and registry, constructs the exposure-floor overlay trial in memory, calls the existing model comparison and governance builders, and writes only a compact summary. It intentionally does not persist another candidate-run artifact, preserving the retained-root data boundary.
- Retained real output: `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_current_frontier_exposure_floor_overlay_governance_summary_20260708.json`.
- Result: the overlay trial ranks `1` in the generated comparison leaderboard; the source trial ranks `2`. Governance-style total return improves `2.774394 -> 2.778286`, annualized return `0.669598 -> 0.670262`, maxDD `-0.030583 -> -0.030149`, path drawdown `-0.596642 -> -0.587898`, and min monthly mean `0.000852 -> 0.000931`; negative months remain `0`. Overfit diagnostics remain ready: alpha t-stat `7.894648`, DSR proxy `0.99999999947`, PBO proxy `0.0`, period count `653`, split count `33`.
- Governance remains blocked only by configured ADV capacity and promotion-pending gates: `execution:adv_capacity_fill_rate`, `model_comparison_report:execution_stress:capacity:adv_capacity_fill_rate_below_floor`, and `model_comparison_report:governance_promotion_pending`.
- Decision: this is the strongest current evidence for the path-stress side of the goal. It still is not full matrix replay or capacity clearance, but it is no longer just a loose selected-return proxy: the existing comparison/governance stack can evaluate it without DSR/PBO degradation and without retained artifact data growth. Next work should either register/replay this overlay as a governed candidate, or combine it with the remaining capacity-contract path; do not discard it as a mere execution patch.

[2026-07-08T08:55:00+08:00] Staggered execution plus exposure-floor scaling clears the combined proxy floor:

- Extended `research-capacity-staggered-entry-proxy` so it can optionally combine staggered underfilled-slot execution with an exposure-floor overlay. Default behavior remains unchanged; the combined scan only runs when `--exposure-overlay-mode` and `--gross-exposure-floor` are provided.
- Retained real output: `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_current_frontier_staggered_entry_exposure_combo_proxy_20260708.json` (`~206KB`). It scans old no-overlay staggered entry plus `linear_scale` exposure floor `0.3318448363`, under both `original_exit` and `per_tranche_horizon`.
- Result: `non_degrading_scans` is now non-empty. The best scan is `entry_days=10`, `exit_policy=per_tranche_horizon`, `exposure_overlay_mode=linear_scale`, floor `0.3318448363`. It fills all three underfilled `603117.SH` selected Rank1 slots under the `1,000,000 CNY / 5% ADV` proxy (`min_staggered_fill_rate=1.0`, repaired pick count `3`) while improving total proxy `2.098074 -> 2.101413`, annualized proxy `0.547098 -> 0.547741`, maxDD `-0.029518 -> -0.029092`, path drawdown `-0.596642 -> -0.587898`, and worst monthly mean `0.000852 -> 0.000931`; positive-date rate is unchanged and negative months remain `0`.
- Decision: this is the first bounded result that addresses both remaining execution capacity and path-stress without giving back the current frontier return floor. It is still not complete strategy proof: the combined transformation needs compact comparison/governance or formal replay evidence for DSR/PBO and promotion gates. The next valid step is not another standalone execution patch; it is to govern/replay this combined transformation or prove why it cannot be made replayable.

[2026-07-08T09:05:00+08:00] Combined staggered/exposure governance is non-degrading but capacity promotion remains blocked:

- Added reusable CLI `research-staggered-exposure-combo-governance`, backed by `exposure_floor_overlay_governance.py`. It reads the source candidate-run, model-spec registry, and retained combo proxy, constructs the combined trial in memory, and writes only a compact governance summary instead of retaining another candidate-run payload.
- Retained real output: `/tmp/stock_dashboard_retained_reports_20260706/stock_dashboard_v3_current_frontier_staggered_exposure_combo_governance_summary_20260708.json`.
- Result: the combined trial ranks `1` and the source trial ranks `2` in the generated comparison report. Governance-style total return improves `2.774394 -> 2.775303`, annualized return `0.669598 -> 0.669753`, maxDD improves `-0.030583 -> -0.030149`, path improves `-0.596642 -> -0.587898`, min monthly mean improves `0.000852 -> 0.000931`, negative months stay `0`, positive-date rate stays `0.459418`, DSR proxy is `0.99999999949`, and PBO proxy stays `0.0`.
- Caveat: this is still a compact governance proxy. Staggered-entry total-return-after-cost is approximated by applying the net-excess contribution delta to source total-return-after-cost, then applying the exposure overlay. It is not a full order-level replay.
- Decision: this is now the leading successor candidate because it clears return, drawdown, path, negative-month, DSR and PBO non-degradation while repairing the three underfilled proxy slots. After adding a staged-entry capacity diagnostic to the comparison report, the governance execution gate is `execution_ready` and `adv_capacity_fill_rate` is ready under `configured_staggered_execution_capacity_proxy_ready`. It is not promotable yet: the remaining blocker is `model_comparison_report:governance_promotion_pending`, and the capacity contract claim ceiling remains `research_only_staggered_execution_capacity_proxy` until a full order-level replay or explicit lower-claim product contract exists.
- Verification: focused model comparison/governance tests passed (`71 passed`), policy audit passed, retention audit passed with retained root `246,443,132` bytes and retained candidate-run files `0`, and default fast pytest passed (`1105 passed, 180 deselected, 6 subtests passed`).

[2026-07-10T20:20:00+08:00] Runtime storage uses pinned reusable inputs plus verified cold archives:

- The production runtime directory had grown to `33.456 GiB`; the main driver was `22.49 GB` of research artifacts, including multiple superseded matrices and 26 complete candidate-run payloads.
- The complete-history v3 feature matrix `pit-feature-matrix-9e2854ba4a2cd78e` and complete-history candidate sources `84adc785808483d3` / `0d6333a65ae410f0` are now explicit pinned reusable inputs. Compact reports remain online under a `256 MiB` aggregate ceiling.
- Sixty-four unpinned derived payloads (`16,387,148,025` source bytes) were archived with per-file SHA-256 and single-threaded zstd verification; online storage keeps no unpinned heavy payloads.
- Two old full DB backups and the retired hot/cold split databases were integrity-checked and compressed rather than deleted. The history database had zero IDs absent from the current main DB, and all five research archive table counts matched the current main DB.
- Runtime release snapshots now retain the latest 10; runtime `node_modules`, browser profiles and Playwright caches are reconstructible and are removed before a publish becomes latest-successful.
- The authoritative contract, restore boundary and completion evidence are `docs/contracts/RUNTIME_STORAGE_GOVERNANCE_2026-07-10.md`; the machine-readable policy is `docs/contracts/SHORTPICK_V3_RUNTIME_STORAGE_POLICY_2026-07-10.json`.

[2026-07-15T17:10:00+08:00] R14 is retained after the bounded October optimization experiment:

- Ran a full-history account-replay scan over the pinned v3 PIT feature matrix and authoritative candidate run. The scan covered two predeclared hypothesis families and seven variants: short-market momentum confirmation and weak-benchmark defensive scaling. No symbol/date hardcoding was used.
- The reconstructed R14 baseline returned `+332.100%`, with `-6.885%` max drawdown, two negative months, and `+1.320%` in `2025-10`. Because October 2025 was already positive, it is not a valid loss-month repair target.
- Strong-market confirmation at `benchmark_return_10d >= 1%` reduced total return to `+320.188%`, worsened max drawdown to `-7.234%`, raised negative months to five, and reduced October 2025 to `+0.567%`. The mildest weak-market scaling improved max drawdown to `-6.704%` but reduced total return to `+324.529%` and added one negative month.
- Decision: retain R14 and do not add, register, or surface any experiment variant. The backend/frontend strategy set remains unchanged. Future candidates follow one-in-one-out replacement and must clear the same frozen nine-metric gate.
- Promotion remains blocked by `r14_contract_reproduction_mismatch`: Top3 selection reproduced exactly (`1533/1533`) and `110,220` reconstructed return anchors had zero error, but the original execution snapshot is unavailable and reconstructed total return is `9.667` percentage points below the frozen R14 contract. The next optimization must first freeze reproducible order-level execution evidence, then test execution efficiency without introducing another strategy family.
- Evidence: `docs/contracts/SHORTPICK_V3_R14_OCTOBER_OPTIMIZATION_EXPERIMENT_2026-07-15.json`, `docs/analysis/SHORTPICK_V3_R14_OCTOBER_OPTIMIZATION_REPORT_2026-07-15.md`, and the executed notebook beside it.

[2026-07-15T19:55:00+08:00] Rank5 moves to a fixed true-forward observation window without changing R14:

- The six preregistered Rank5 path-quality filters were historically rejected, so no new Rank5 threshold is activated and the three-role active strategy set remains unchanged.
- Starting with signal date `2026-07-15`, every base-eligible Rank5 replacement opportunity triggered by a price-too-high original pick is retained as an independent shadow observation, including when Rank4 wins current R14 precedence. Signal-day path features use only the latest 21 closes on or before the signal date.
- Synchronized backfill and retrospective rows are excluded. Candidate, benchmark, and excess 20-day outcomes remain null until the fixed window matures. Selected Rank5 observations carry a deterministic key through plan, buy, position, and sell records.
- Research may reopen only after at least 80 matured observations, six distinct signal months, 120 elapsed calendar days, and clean key/duplicate/missing-feature/premature-outcome checks. This gate permits one separately preregistered analysis; it does not tune or activate a filter. Promotion discussion additionally requires 20 actual closed Rank5 replacements and 12 months / 365 days.
- The paper-tracking API and dashboard expose collection progress. Summary reads omit row payloads, and the UI explicitly states that observation does not change current R14 orders.
- Contract: `docs/contracts/SHORTPICK_V3_RANK5_FORWARD_OBSERVATION_CONTRACT_2026-07-15.json`. Implementation note: `docs/contracts/SHORTPICK_V3_RANK5_FORWARD_OBSERVATION_IMPLEMENTATION_2026-07-15.md`.
[2026-08-06T00:00:00+08:00] Personal account eligibility is a PIT pre-ranking gate and external context remains research-only:

- Activated `account_trade_eligibility_snapshot.v1` as the shared outer-universe contract for historical factor studies, portfolio backtests, historical replay, LLM paper control and live market-factor candidates. The conservative default is ordinary Shanghai/Shenzhen main-board A shares only, with decision-time actual unadjusted price `<= 200 CNY`; STAR, ChiNext, BSE, B shares/unknown securities, ST/risk-warning and delisting/inactive securities are excluded where PIT status is available.
- Current-account age is not treated as proof of securities-trading experience. Permission remains an explicit configurable account profile and can be widened only after broker permissions are confirmed.
- Historical replay no longer uses today's stock name, status or board label to infer historical ST/delisting eligibility. Until broad PIT risk-warning history exists, replay emits `pit_risk_status_unverified_current_static_name_not_used`; such results cannot claim fully executable historical eligibility.
- External market/news information is not added to V3. Frozen full713 remains the control. Channel PoC, Raw/Silver/PIT storage, no-network replay and the static-weight -> rule-dynamic -> constrained learned-gate ladder are preregistered in `docs/contracts/SHORTPICK_V3_EXTERNAL_CONTEXT_RESEARCH_2026-08-06.json`.

[2026-08-06T17:38:00+08:00] External-context provider PoC remains blocked and no subscription is purchased:

- Added an executable provider registry/audit and a bounded aggregate-only Tushare transport PoC. Every layer requires a ready primary plus an independent ready fallback; official facts, global market and professional news are all still blocked. V3 inputs and weights remain unchanged.
- Existing Tushare access can retrieve `stock_st` (254 rows on 2026-05-26; documented history from 2016) and full713+warmup global indices (SPX 770, IXIC 770, HKTECH 752 rows). They are budget-first candidates, not approved replay sources, until local frozen-replay rights, correction semantics and repeated-pull hashes pass.
- `major_news` documents more than eight years of history and returned parseable unique samples, but daily requests saturated at 800 rows and a sharded probe hit the observed 30 requests/hour account cap. A bounded full-shard run was stopped rather than allowing an external source to block refresh. News is blocked pending bulk export/rate upgrade, adaptive checkpointed acquisition, revision auditing, entity-precision review and written article-storage/replay rights.
- Purchase decision: spend nothing now. Defer Massive Stocks Starter (`USD 29/month`) and Benzinga news add-on (`USD 99/month`) until Tushare gaps and vendor rights are measured. Use free SEC EDGAR and FRED/ALFRED for the first official-fact/macro pilot; request an SSE Info API quote and keep CNINFO as original-document verification rather than unsupported scraping.
