# Trial A 全局协议基线

状态：Trial A draft  
适用项目：`stock_dashboard` / A 股研究与决策看板  
适用阶段：自运行开发流程试验田，先作为并行模块设计前的统一协议输入，不代表生产完成。  

## 1. 目标

本文件定义 Trial A 在重新生成模块设计前必须共享的全局协议基线，避免子进程各自定义术语、事件、artifact、接口和成熟度，导致后续实现阶段出现“单模块成立、系统拼不起来”的问题。

本项目不是通用任务平台试验，而是一个已经有真实业务约束的 A 股研究系统。因此协议必须服从以下事实：

- 当前主线是 `Phase 5 - Real Validation Rebuild and Model Portfolio Policy Research`。
- 产品入口是 `https://hernando-zhao.cn/stocks`，运行时挂载仍是 `/projects/ashare-dashboard/`。
- 用户可见能力必须区分研究候选、验证中、已验证和已废弃，不得把研究草案包装成正式投资能力。
- `core_quant / evidence / risk / historical_validation / manual_llm_review` 是 recommendation 的当前主语义分层。
- Short Pick Lab、主 recommendation、simulation、portfolio、manual LLM review 互相隔离，除非合同明确批准。

## 2. 非目标

- 不重新设计全站架构。
- 不替代 `PHASE5_RESEARCH_CONTRACT.md`、`PHASE1_PHASE2_ARTIFACT_CONTRACT.md` 或短投试验田专项合同。
- 不批准任何 `production` 级能力。
- 不新增真实交易、真实下单或自动实盘路由。
- 不要求子进程启动服务、发布 runtime、修改 `PROJECT_STATUS.json` / `PROCESS.md` / `DECISIONS.md`。
- 不把当前已有代码、页面或脚本的存在视为成熟度证明。

## 3. 术语表

| 术语 | 定义 | 当前成熟度 | 协议约束 |
| --- | --- | --- | --- |
| `research_validation` | 使用 point-in-time 数据和 rolling / walk-forward 口径验证模型或策略的研究层。 | usable | 可用作研究事实源，但每个结论必须绑定 artifact。 |
| `watchlist_tracking` | 用户自选池加入后的产品跟踪表现。 | partial | 只能从加入自选池日期开始计算，不能回填加入前历史美化表现。 |
| `recommendation` | 单票分析与建议展示的产品壳，包含量化、证据、风险、验证和人工研究层。 | usable | 不允许把 LLM 或兼容字段混入 `core_quant.score`。 |
| `core_quant` | recommendation 中唯一承载量化结论的层。 | usable | 只能来自可复现模型、规则基线或 artifact-backed 结果。 |
| `evidence` | recommendation 中解释“为什么成立”的证据层。 | usable | 证据措辞不能强于 `historical_validation.status`。 |
| `risk` | recommendation 中解释失效条件、降级条件和 coverage gap 的风险层。 | usable | 风险必须可观察、可回查，不能只是文案提示。 |
| `historical_validation` | 对单票、排序、组合或 replay 结果的历史验证摘要。 | partial | `verified` 必须绑定 validation manifest / metrics artifact。 |
| `manual_llm_review` | 用户手动触发的 LLM 附加研究。 | usable | 不参与主评分、不反写推荐分、不作为 promotion gate 依据。 |
| `Short Pick Lab` | 短投试验田，用于开放候选、历史回放、模型反馈和多 benchmark 后验观察。 | partial | 与主 recommendation、生产权重、模拟盘自动调仓隔离。 |
| `simulation` | Web 模拟盘与模型组合自动持仓研究轨。 | partial | 只允许模拟成交，不允许真实订单路由。 |
| `artifact` | 可序列化、可追溯、可被消费者引用的研究或运行产物。 | usable | 任何产品层 verified 声明必须能追溯 artifact。 |
| `projection` | 从 artifact / DB / ledger 投影到前端轻量 API 的数据视图。 | partial | 首屏和聚合接口不应临时扫大表或实时跑研究链。 |
| `claim ceiling` | 某能力在用户可见层允许表达的最高强度。 | partial | 由研究状态、样本数、benchmark、成本和 gate 共同约束。 |
| `promotion gate` | 判断研究候选能否晋级产品能力的门禁。 | scaffold | 当前仅作为 draft diagnostic，不自动批准 promotion。 |
| `runtime` | 用户可见运行副本，位于 `~/codex/runtime/projects/ashare-dashboard`。 | usable | live-facing 任务必须发布并验收，Trial A 子进程豁免。 |

## 4. 状态与成熟度矩阵

### 4.1 通用状态枚举

| 状态 | 含义 | 用户可见规则 |
| --- | --- | --- |
| `pending_rebuild` | 旧能力已识别为不可信，真实验证尚未重建完成。 | 只能展示说明和待补原因。 |
| `synthetic_demo` | 演示或合成逻辑。 | 不得展示为真实研究结论。 |
| `research_candidate` | 有研究候选或实验结果，但未达到产品批准标准。 | 可在研究页或运营页展示，默认不能作为正式主结论。 |
| `verified` | 有真实 artifact，且通过研究门禁。 | 可进入用户主视图，但仍需显示适用范围。 |
| `deprecated` | 废弃字段或旧口径。 | 仅兼容，不作为新设计依赖。 |
| `blocked` | gate 或数据质量阻断。 | 必须显示阻断原因，不能静默降级成成功。 |
| `insufficient_history` | 历史样本不满足当前研究基线。 | 不得输出 verified 指标。 |

### 4.2 模块成熟度矩阵

| 模块 | 当前成熟度 | 允许设计深度 | 禁止事项 |
| --- | --- | --- | --- |
| Recommendation 语义层 | usable | 状态机、失败处理、前端投影、测试门禁。 | 把 compat 字段当新事实源。 |
| Phase 5 rolling validation | usable | artifact schema、split plan、coverage gate、重跑策略。 | 用随机切分或无 manifest 指标。 |
| Portfolio / simulation policy research | partial | 研究候选、gate 诊断、redesign 实验菜单。 | 宣称自动组合策略已生产可用。 |
| Short Pick Lab validation | partial | validation mode、tradeability、multi-benchmark、topic artifact。 | 回写主推荐、生产权重或模拟盘。 |
| Manual LLM review | usable | 手动触发、source packet、冲突展示、失败降级。 | 参与核心评分或自动调仓。 |
| Frontend workbench | partial | PC/手机独立信息架构、claim ceiling 展示、局部滚动。 | 用占位状态暗示后端已接入。 |
| Runtime publish / served verification | usable | 发布、回滚、浏览器验收。 | Trial A 子进程执行发布或服务操作。 |
| Autonomous flow orchestration | scaffold | 全局协议、owned files、重跑规则、评审标准。 | 设计 production SLA 或无人值守承诺。 |

## 5. 事件注册表

事件名采用 `domain.object.action.vN`。Trial A 模块设计只能引用本表事件；新增事件必须先更新全局协议，不得在模块文档中临时发明。

| 事件 | Provider | Consumer | Payload 最小字段 | 失败语义 | 当前级别 |
| --- | --- | --- | --- | --- | --- |
| `data.market_snapshot.refreshed.v1` | data refresh pipeline | recommendation、validation、simulation、frontend projection | `snapshot_id`, `as_of_time`, `available_time`, `source_status`, `symbol_count` | 外部源失败可 fail-open，但必须写 `source_status`。 | partial |
| `artifact.validation_manifest.created.v1` | validation runner | recommendation projection、research review、operations | `artifact_id`, `experiment_version`, `split_plan_id`, `universe_definition`, `generated_at` | 无 manifest 时不得生成 `verified`。 | usable |
| `artifact.validation_metrics.created.v1` | validation runner | historical validation、claim gate、frontend projection | `artifact_id`, `manifest_id`, `status`, `sample_count`, `coverage_ratio`, `metrics_ref` | 指标缺 coverage / turnover 时保持 `research_candidate`。 | usable |
| `artifact.portfolio_backtest.created.v1` | portfolio research runner | simulation policy gate、operations workbench | `artifact_id`, `manifest_id`, `strategy_definition`, `cost_definition`, `gate_readout_ref` | benchmark 或成本不完整时不能晋级。 | partial |
| `artifact.holding_policy_study.created.v1` | phase5 holding policy runner | policy governance、operations workbench | `artifact_id`, `policy_type`, `gate_status`, `governance_action`, `redesign_focus_areas` | gate blocked 时默认进入 redesign，不进入 promotion。 | partial |
| `recommendation.projected.v1` | recommendation projection | frontend、manual LLM context pack | `recommendation_key`, `core_quant`, `evidence`, `risk`, `historical_validation`, `claim_ceiling` | 缺验证时输出降级状态，不补假数值。 | usable |
| `manual_llm_review.requested.v1` | frontend / user action | manual review worker | `request_id`, `target_login`, `symbol`, `context_packet_id`, `requested_at` | 缺个人模型 key 时进入失败/待配置，不影响 core quant。 | usable |
| `manual_llm_review.completed.v1` | manual review worker | recommendation projection、frontend | `request_id`, `model_label`, `summary`, `risks`, `disagreements`, `source_packet_ref` | 与量化冲突时显示 `disagreements`，不覆盖分数。 | usable |
| `shortpick.run.completed.v1` | shortpick lab runner | validation queue、topic classifier、feedback projection | `run_id`, `signal_available_at`, `provider_set`, `candidate_count`, `source_packet_ref` | source/search 不足时 fail closed。 | partial |
| `shortpick.validation_snapshot.created.v1` | shortpick validation worker | model feedback、history replay、frontend | `snapshot_id`, `run_id`, `symbol`, `validation_mode`, `tradeability_status`, `benchmark_map` | official aggregation 排除无效交易假设。 | partial |
| `shortpick.topic_registry.updated.v1` | topic normalization worker | model feedback、history replay | `registry_artifact_id`, `topic_cluster_id`, `status`, `evidence_count` | AI 分类失败后标记 `unclassified`，不人工等待。 | scaffold |
| `frontend.projection.updated.v1` | projection builder | API / SPA shell | `projection_name`, `version`, `generated_at`, `source_artifact_ids`, `staleness_status` | 投影缺失时显示待补，不在请求路径补跑研究。 | partial |
| `runtime.publish.verified.v1` | main process closeout | project status、process log | `commit_id`, `release_manifest`, `localhost_result`, `canonical_result` | Trial A 子进程不得产生此事件。 | usable |

## 6. Artifact Schema Registry

artifact id 采用 `<family>:<scope>:<date-or-run>:<version-or-hash>`。消费者必须通过 `artifact_id` 或 `manifest_id` 引用，不直接复制完整研究 payload 到产品壳。

| Artifact Family | 用途 | 最小 schema | Provider | Consumer | 当前状态 |
| --- | --- | --- | --- | --- | --- |
| `rolling_validation_manifest` | 定义 rolling / walk-forward 实验如何产生。 | `artifact_id`, `artifact_type`, `experiment_version`, `model_version`, `policy_version`, `data_snapshot_id`, `universe_definition`, `availability_rule`, `feature_set_version`, `label_definition`, `benchmark_definition`, `cost_definition`, `rebalance_definition`, `split_plan` | validation runner | validation metrics、recommendation、research review | usable |
| `validation_metrics` | 汇总验证表现。 | `artifact_id`, `manifest_id`, `status`, `sample_count`, `coverage_ratio`, `turnover_mean`, `rank_ic_mean`, `rank_ic_ir`, `bucket_spread_mean`, `period_metrics`, `market_regime_metrics` | validation runner | historical validation、claim gate | usable |
| `portfolio_backtest` | 组合策略路径和成本后表现。 | `artifact_id`, `artifact_type`, `manifest_id`, `strategy_definition`, `position_limit_definition`, `execution_assumptions`, `benchmark_definition`, `cost_definition`, `annualized_excess_return`, `max_drawdown`, `turnover`, `capacity_note` | portfolio runner | simulation policy、operations | partial |
| `replay_alignment` | 单票 recommendation replay 与标签对齐。 | `artifact_id`, `manifest_id`, `recommendation_key`, `label_definition`, `entry_rule`, `exit_rule`, `hit_definition`, `validation_status`, `stock_return`, `benchmark_return`, `excess_return` | replay runner | frontend replay、historical validation | partial |
| `phase5_holding_policy_study` | simulation policy 研究、gate、governance、redesign 事实源。 | `artifact_id`, `policy_type`, `portfolio_count`, `mean_annualized_excess_return_after_baseline_cost`, `mean_invested_ratio`, `gate_status`, `governance_action`, `redesign_focus_areas`, `redesign_primary_experiment_ids` | phase5 policy runner | operations、policy redesign | partial |
| `shortpick_validation_snapshot` | 短投候选的 official / diagnostic 后验验证。 | `snapshot_id`, `run_id`, `candidate_id`, `symbol`, `validation_mode`, `signal_available_at`, `entry_trade_day`, `exit_trade_day`, `tradeability_status`, `benchmark_map`, `official_inclusion_status` | shortpick validation worker | shortpick feedback、history replay | partial |
| `shortpick_topic_registry` | AI 生成题材注册表。 | `registry_artifact_id`, `topic_cluster_id`, `label_zh`, `description`, `known_aliases`, `evidence_count`, `status`, `created_by_run_id`, `last_confirmed_at` | topic normalization worker | shortpick feedback、topic replay | scaffold |
| `manual_llm_source_packet` | 手动 LLM 研究上下文和来源包。 | `source_packet_id`, `target_login`, `symbol`, `recommendation_key`, `as_of_time`, `core_quant_ref`, `evidence_ref`, `risk_ref`, `source_links`, `packet_hash` | context pack builder | manual review worker | usable |
| `frontend_projection_manifest` | 前端首屏和聚合读数的轻量投影清单。 | `projection_name`, `version`, `generated_at`, `source_artifact_ids`, `row_count`, `staleness_status`, `fallback_reason` | projection builder | API / SPA | partial |
| `autonomous_flow_trial_report` | 自运行流程试验每轮评估与重跑依据。 | `trial_id`, `flow_version`, `input_contracts`, `subtask_outputs`, `review_scores`, `rerun_triggers`, `accepted_outputs`, `rejected_outputs` | main autonomous process | PROCESS / DECISIONS 固化前审阅 | scaffold |

## 7. 模块接口矩阵

| Provider 模块 | Consumer 模块 | 合同对象 | 所有者 | 失败 / 降级规则 |
| --- | --- | --- | --- | --- |
| Data Refresh Pipeline | Validation Runner | `data.market_snapshot.refreshed.v1` + `data_snapshot_id` | data pipeline owner | 外部源失败不阻断全部刷新，但相关 symbol / benchmark 标记 pending。 |
| Validation Runner | Recommendation Projection | `rolling_validation_manifest`, `validation_metrics` | research validation owner | 缺 artifact 时 `historical_validation.status != verified`。 |
| Validation Runner | Portfolio Backtest Runner | `manifest_id`, `benchmark_definition`, `cost_definition` | research validation owner | benchmark / cost 口径不一致时拒绝 backtest 晋级。 |
| Portfolio Backtest Runner | Simulation Policy Governance | `portfolio_backtest`, `phase5_holding_policy_study` | portfolio research owner | gate blocked 时输出 non-promotion，不进入用户主承诺。 |
| Recommendation Projection | Frontend Workbench | `recommendation.projected.v1` | product projection owner | claim ceiling 低于 verified 时隐藏或降级强指标。 |
| Recommendation Projection | Manual LLM Context Builder | `manual_llm_source_packet` | manual review owner | source packet 缺失时人工研究请求失败，不影响主推荐。 |
| Manual LLM Worker | Recommendation Projection | `manual_llm_review.completed.v1` | manual review owner | 仅写 manual layer 和 disagreements，不反写 core quant。 |
| Short Pick Runner | Short Pick Validation Worker | `shortpick.run.completed.v1` | shortpick owner | search/source 不足时 failed diagnostics，不生成官方样本。 |
| Short Pick Validation Worker | Short Pick Feedback Projection | `shortpick_validation_snapshot` | shortpick validation owner | official 聚合只读 official mode + tradeable 样本。 |
| Topic Normalization Worker | Short Pick Feedback Projection | `shortpick_topic_registry` | topic registry owner | `candidate` / `unclassified` 不进入题材级正式表现。 |
| Projection Builder | API / SPA | `frontend_projection_manifest` | frontend projection owner | API 只读投影，缺投影显示待补，不同步跑研究任务。 |
| Autonomous Main Process | Subagents | `Context Pack`, `owned_files`, `maturity_matrix` | main autonomous owner | 子进程越权文件或引用未注册协议时触发重跑。 |
| Subagents | Autonomous Reviewer | module design docs | subtask owner | 子进程只产出 owned file，不提交、不发布。 |

## 8. 冲突与锁域

### 8.1 文件锁域

| 锁域 | 资源 | 并行规则 |
| --- | --- | --- |
| `canonical_status_docs` | `PROJECT_STATUS.json`, `PROCESS.md`, `DECISIONS.md`, `PROJECT_PLAN.md` | 只允许主进程在固化阶段写。子进程禁止写。 |
| `global_protocol` | 本文件及后续全局 registry 文档 | 同一轮只能由一个全局协议子任务写。模块子任务只读。 |
| `module_design_docs` | `docs/contracts/autonomous-flow-trial/TRIAL_*_*.md` | 可并行，但每个子任务必须 owned file disjoint。 |
| `runtime_publish` | `~/codex/runtime/projects/ashare-dashboard`、release manifest、LaunchAgent | 只允许主进程 closeout，Trial A 子进程禁止。 |
| `artifact_data` | `data/artifacts`、runtime artifact store、DB artifact tables | 设计任务只读；实现任务需声明 writer 和 lock。 |
| `frontend_shell` | React SPA shell、PC / mobile 工作台入口 | 设计任务可并行，代码实现需按文件和路由隔离。 |

### 8.2 业务锁域

| 锁域 | 说明 | 冲突判定 |
| --- | --- | --- |
| `recommendation_claim_ceiling` | 用户可见推荐强度上限。 | 任何模块提升表达强度都必须引用同一 gate。 |
| `phase5_policy_gate` | simulation policy 晋级门禁。 | backtest、governance、frontend 不得各自定义晋级条件。 |
| `shortpick_official_validation_mode` | 短投 official 聚合口径。 | validation、feedback、UI 必须共用 `after_close_t_plus_1_close_entry_v1` 或后续批准版本。 |
| `benchmark_definition` | 主研究 benchmark、市场参考、短投三维 benchmark。 | 不能用 CSI300 替代 active watchlist 主研究 benchmark，也不能用沪深300替代缺失的同板块基准。 |
| `account_scope` | root / member / act_as / target_login。 | 个人模型 key、manual review、关注池必须按账号隔离。 |
| `sqlite_write_lock` | 日刷、短投验证、历史回放、投影重建。 | 不允许把长维护任务挂在热路径，写任务需排队或维护窗口。 |

## 9. 开放问题分类

### 9.1 architecture_decision

这些问题必须由主进程或后续决策文档收敛后，才能进入实现。

| 问题 | 影响范围 | 推荐处理 |
| --- | --- | --- |
| 自运行流程的 trial report 是否作为长期 artifact family 保留。 | 流程平台、审计、重跑依据。 | Trial A/B 结束后决定是否纳入 `docs/contracts/` 正式合同。 |
| 全局事件注册表未来是单文件、JSON schema，还是数据库表。 | 多 agent 并行设计与实现。 | 当前先以 Markdown 注册表运行，进入实现前锁定机器可校验格式。 |
| claim ceiling 是否统一成代码中的公共 gate 服务。 | recommendation、Short Pick Lab、simulation、frontend。 | 当前文档只定义语义，后续实现需决定落点。 |
| artifact registry 是否继续文件路径语义，还是迁移到 DB / object store。 | 研究产物追溯、runtime publish、清理策略。 | 保留 `artifact_id` 语义，存储后端另行决策。 |

### 9.2 implementation_choice

这些问题可由实现阶段按现有模式选择，但必须保持协议语义。

| 问题 | 约束 |
| --- | --- |
| `frontend_projection_manifest` 存 DB、JSON 文件还是内存缓存。 | API 不得在首屏请求里跑重计算。 |
| 事件是先通过日志、artifact manifest，还是轻量表记录。 | 必须可审计、可查询、可供重跑判断。 |
| topic registry 的 AI verifier 使用哪个模型。 | 必须有 schema 校验和 fail-closed 策略。 |
| 子进程评审脚本先用 Markdown 规则还是 AST / schema。 | 必须检查 owned file、章节、未注册事件和成熟度越界。 |

### 9.3 research_unknown

这些问题必须通过数据或试验回答，不能靠文案决定。

| 问题 | 所需证据 |
| --- | --- |
| Phase 5 主 horizon 最终选 `10 / 20 / 40` 还是双轨。 | 扩大样本后的 rolling validation artifact。 |
| simulation policy 是否能通过 after-cost gate。 | `profitability_signal_threshold_sweep_v1` 与 `construction_max_position_count_sweep_v1` 结果。 |
| Short Pick Lab 题材聚合是否能稳定提升反馈解释力。 | 多轮 topic registry artifact 与 official sample 表现。 |
| claim ceiling 对用户理解是否足够清晰。 | 前端可用性测试和 served 页面验证。 |

## 10. Trial A 子任务引用规则

后续 Trial A 模块设计文档必须满足：

- 所有新术语优先引用第 3 节；确需新增时必须标记 `proposed_term`，不得假装已注册。
- 所有跨模块事件必须来自第 5 节。
- 所有持久产物必须来自第 6 节。
- 所有接口依赖必须能映射到第 7 节。
- 所有成熟度声明必须能映射到第 4 节，不得把 partial/scaffold 能力写成 production。
- 所有开放问题必须归类到 `architecture_decision`、`implementation_choice` 或 `research_unknown`。
- 任何用户可见能力都必须说明 claim ceiling，不得用“智能推荐”“自动策略”等强表达绕开验证状态。

## 11. 验收标准

- 本文件覆盖术语表、事件注册表、artifact schema registry、模块接口矩阵、成熟度矩阵、冲突/锁域和开放问题分类。
- 文档中的事件、artifact 和模块接口均与 `stock_dashboard` 当前 Phase 5、Short Pick Lab、manual LLM review、runtime publish 约束相关。
- 文档没有宣称当前自运行流程、promotion gate、topic registry 或 simulation policy 已达到 production。
- 后续子进程可直接把本文件作为输入合同，产出 owned module docs。

