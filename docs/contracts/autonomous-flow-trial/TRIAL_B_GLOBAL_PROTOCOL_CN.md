# Trial B 全局协议基线

状态：Trial B draft  
适用项目：`stock_dashboard` / A 股研究与决策看板  
适用阶段：自运行开发流程试验田的第二轮重跑输入，不代表 production 合同。  
上游输入：`AUTONOMOUS_DEVELOPMENT_FLOW_CN.md`、`AUTONOMOUS_FLOW_TRIAL_2026-05-20_CN.md`、Trial A 全局协议和 Phase 5 纵向切片设计。

## 1. 目标

本文件修复 Trial A 暴露的协议问题：模块文档在全局协议之外临时声明事件，且 registry 只能人工阅读，不能被脚本稳定检查。

Trial B 的目标是建立一份可被后续模块设计引用和机器扫描的全局协议基线：

- 正式注册 Phase 5 自运行纵向切片所需事件，并统一使用版本化 canonical id。
- 注册本轮允许引用的 artifact family 与 module interface id。
- 给后续 Trial B 模块设计提供硬约束：只能引用本文件已经注册的事件、artifact family 和 interface id。
- 保留 `stock_dashboard` 当前业务边界：A 股研究、Phase 5、Short Pick Lab、manual LLM review、simulation-only、runtime publish 与 claim ceiling。
- 继续限制在 `partial -> usable`，不宣称自运行平台、组合策略或 promotion gate 已达到 production。

## 2. 非目标

- 不替代正式 JSON Schema、数据库表或事件总线实现。
- 不实现调度器、ledger、publisher、reviewer 或前端代码。
- 不批准真实交易、真实下单、自动实盘组合或生产级投资承诺。
- 不提升 `Phase 5 holding policy`、`promotion gate`、`topic registry` 或自运行编排的成熟度。
- 不要求子进程启动服务、发布 runtime、提交 git，或更新 `PROJECT_STATUS.json` / `PROCESS.md` / `DECISIONS.md`。
- 不把 Trial A 已有草案包装成最终架构；本文件只是 Trial B 的协议基线。

## 3. Trial A 问题与 Trial B 修复

| Trial A 问题 | Trial B 修复 |
| --- | --- |
| Phase 5 模块文档自行声明 `phase5.*` 事件，未先进入全局事件表。 | 本文件正式注册 `phase5.*.v1` 事件，后续模块只能引用版本化 id。 |
| Registry 主要面向人工阅读，难以脚本检查未注册引用。 | 第 12 节新增机器可校验 registry appendix，所有 canonical id 均放在反引号中。 |
| 全局协议和模块设计并行生成，存在时序漂移。 | Trial B 先生成本文件，模块设计必须把本文件作为只读上游合同。 |
| 开放问题可能混入后续实现阻塞。 | 继续按 `architecture_decision`、`implementation_choice`、`research_unknown` 分类。 |

## 4. 成熟度与设计深度

| 能力域 | Trial B 成熟度 | 允许设计深度 | 禁止事项 |
| --- | --- | --- | --- |
| `autonomous_flow_orchestration` | scaffold | 全局协议、owned file、registry 检查、重跑规则。 | production SLA、全自动发布承诺、无人事故恢复承诺。 |
| `phase5_cycle_ledger` | partial | cycle 状态、输入合同版本、下一步动作、失败分类。 | 复杂任务平台、分布式锁、跨项目调度。 |
| `phase5_research_validation` | usable | artifact lineage、coverage gate、claim ceiling 降级。 | 无 artifact 的 verified 声明。 |
| `phase5_policy_governance` | partial | non-promotion、needs-redesign、实验建议。 | 自动批准 simulation policy 晋级。 |
| `frontend_projection` | partial | 只读投影、staleness、source artifact 追溯。 | 页面请求内跑研究、扫大表或写库。 |
| `runtime_publish_verification` | usable | repo/runtime/localhost/canonical 分层验收。 | 子进程执行发布或把 degraded 标记为 completed。 |
| `manual_llm_review` | usable | 手动触发、source packet、disagreement 展示。 | 参与 core quant、validation gate 或自动调仓。 |
| `shortpick_lab_feedback` | partial | official/diagnostic 分口径验证和投影。 | 回写主推荐、生产权重或 Phase 5 晋级门禁。 |

## 5. 术语基线

| Canonical Term | 定义 | Trial B 约束 |
| --- | --- | --- |
| `Phase5Cycle` | 一次 Phase 5 自运行周期，覆盖研究、artifact、gate、projection、发布验收和回放调度。 | 必须有 `cycle_id`，且能追溯输入合同版本。 |
| `ResearchArtifact` | 可追溯的研究、验证、回放或投影源产物。 | 用户可见强结论必须能追溯 artifact。 |
| `GateReadout` | 对当前研究事实、claim ceiling 和 next action 的结构化读数。 | 不通过时只能输出 non-promotion、continue tracking、redesign 或 degraded。 |
| `ProjectionSnapshot` | 面向 API / SPA 的轻量只读投影。 | 页面请求不得临时跑研究、LLM、行情同步或 DB 写入。 |
| `RecoveryTicket` | 自动恢复动作的 durable 记录。 | 恢复动作不得提升 claim ceiling。 |
| `claim_ceiling` | 用户可见表达强度上限。 | 不得用文案绕开验证状态。 |
| `simulation_only` | 只允许模拟研究和纸面路径，不接真实交易。 | Phase 5 和 Short Pick Lab 默认保持此边界。 |

## 6. Canonical Event Registry

事件 id 采用 `domain.object.action.vN`。Trial B 认为 Trial A 的五个 Phase 5 事件语义合理，但必须改为版本化 id 后注册。后续模块文档不得继续引用无版本的 `phase5.cycle.started` 等旧写法。

| Canonical Event ID | Provider | Consumer | 最小 payload | 失败语义 | 成熟度 |
| --- | --- | --- | --- | --- | --- |
| `phase5.cycle.started.v1` | Phase 5 scheduler / main autonomous process | operations workbench、cycle ledger、reviewer | `cycle_id`, `trigger`, `scope`, `input_contract_versions`, `started_at` | 无法创建 cycle 时不得启动研究链路。 | partial |
| `phase5.artifact.produced.v1` | validation runner、holding policy runner、replay runner、projection builder | projection builder、reviewer、cycle ledger | `cycle_id`, `artifact_id`, `artifact_family`, `schema_version`, `as_of_date`, `lineage_ref` | artifact schema 无法识别时触发 recovery，不进入 verified。 | partial |
| `phase5.gate.evaluated.v1` | gate evaluator | scheduler、frontend projection、reviewer | `cycle_id`, `gate_id`, `gate_status`, `claim_ceiling`, `next_action`, `blocking_reasons` | gate 缺关键输入时输出 `insufficient_evidence` 或 `blocked`。 | partial |
| `phase5.projection.refreshed.v1` | projection builder | publish verifier、API / SPA、operations workbench | `cycle_id`, `projection_id`, `projection_family`, `source_artifact_ids`, `freshness_at`, `staleness_status` | 缺 source artifact 时只能输出 degraded projection。 | partial |
| `phase5.recovery.recorded.v1` | recovery runner / main autonomous process | scheduler、reviewer、trial report | `cycle_id`, `ticket_id`, `failed_step`, `failure_class`, `recovery_action`, `final_status` | 连续恢复失败升级为 blocked，不等待人工口头介入。 | partial |
| `artifact.validation_manifest.created.v1` | validation runner | recommendation projection、Phase 5 gate、research review | `artifact_id`, `experiment_version`, `split_plan_id`, `universe_definition`, `generated_at` | 无 manifest 时不得生成 `verified`。 | usable |
| `artifact.validation_metrics.created.v1` | validation runner | historical validation、claim gate、frontend projection | `artifact_id`, `manifest_id`, `status`, `sample_count`, `coverage_ratio`, `metrics_ref` | coverage 或 turnover 缺失时保持 `research_candidate`。 | usable |
| `artifact.portfolio_backtest.created.v1` | portfolio research runner | simulation policy gate、operations workbench | `artifact_id`, `manifest_id`, `strategy_definition`, `cost_definition`, `gate_readout_ref` | benchmark 或成本不完整时不能晋级。 | partial |
| `artifact.holding_policy_study.created.v1` | phase5 policy runner | policy governance、operations workbench | `artifact_id`, `policy_type`, `gate_status`, `governance_action`, `redesign_focus_areas` | gate blocked 时默认进入 redesign，不进入 promotion。 | partial |
| `recommendation.projected.v1` | recommendation projection | frontend、manual LLM context pack | `recommendation_key`, `core_quant`, `evidence`, `risk`, `historical_validation`, `claim_ceiling` | 缺验证时输出降级状态，不补假数值。 | usable |
| `manual_llm_review.requested.v1` | frontend / user action | manual review worker | `request_id`, `target_login`, `symbol`, `context_packet_id`, `requested_at` | 缺个人模型 key 时失败或待配置，不影响 core quant。 | usable |
| `manual_llm_review.completed.v1` | manual review worker | recommendation projection、frontend | `request_id`, `model_label`, `summary`, `risks`, `disagreements`, `source_packet_ref` | 与量化冲突时显示 disagreement，不覆盖分数。 | usable |
| `shortpick.run.completed.v1` | shortpick lab runner | validation queue、topic classifier、feedback projection | `run_id`, `signal_available_at`, `provider_set`, `candidate_count`, `source_packet_ref` | source/search 不足时 fail closed。 | partial |
| `shortpick.validation_snapshot.created.v1` | shortpick validation worker | model feedback、history replay、frontend | `snapshot_id`, `run_id`, `symbol`, `validation_mode`, `tradeability_status`, `benchmark_map` | official aggregation 排除无效交易假设。 | partial |
| `frontend.projection.updated.v1` | projection builder | API / SPA | `projection_name`, `version`, `generated_at`, `source_artifact_ids`, `staleness_status` | 投影缺失时显示待补，不在请求路径补跑研究。 | partial |
| `runtime.publish.verified.v1` | main process closeout | project status、process log | `commit_id`, `release_manifest`, `localhost_result`, `canonical_result` | Trial B 子进程不得产生此事件。 | usable |

## 7. Artifact Schema Registry

artifact family id 采用小写蛇形命名。后续模块文档只能引用本节或第 12 节中已注册的 artifact family。

| Artifact Family ID | 用途 | 最小 schema | Provider | Consumer | 成熟度 |
| --- | --- | --- | --- | --- | --- |
| `phase5_cycle_ledger` | 记录一轮 Phase 5 自运行周期。 | `cycle_id`, `trigger`, `scope`, `status`, `started_at`, `finished_at`, `input_contract_versions`, `next_action` | main autonomous process / scheduler | operations、reviewer、next cycle planner | partial |
| `phase5_recovery_ticket` | 记录一次失败分类和自动恢复动作。 | `ticket_id`, `cycle_id`, `failed_step`, `failure_class`, `recovery_action`, `retry_count`, `final_status` | recovery runner | scheduler、reviewer、trial report | partial |
| `phase5_gate_readout` | 记录 claim ceiling、gate 状态和下一步动作。 | `gate_id`, `cycle_id`, `gate_status`, `failing_gate_ids`, `incomplete_gate_ids`, `claim_ceiling`, `next_action` | gate evaluator | projection builder、scheduler、operations | partial |
| `rolling_validation_manifest` | 定义 rolling / walk-forward 实验如何产生。 | `artifact_id`, `experiment_version`, `model_version`, `data_snapshot_id`, `universe_definition`, `availability_rule`, `split_plan` | validation runner | validation metrics、recommendation、research review | usable |
| `validation_metrics` | 汇总验证表现。 | `artifact_id`, `manifest_id`, `status`, `sample_count`, `coverage_ratio`, `turnover_mean`, `rank_ic_mean`, `period_metrics`, `market_regime_metrics` | validation runner | historical validation、claim gate | usable |
| `phase5_holding_policy_study` | simulation policy 研究、gate、governance、redesign 事实源。 | `artifact_id`, `policy_type`, `portfolio_count`, `mean_annualized_excess_return_after_baseline_cost`, `mean_invested_ratio`, `gate_status`, `governance_action`, `redesign_focus_areas` | phase5 policy runner | operations、policy redesign | partial |
| `portfolio_backtest` | 组合策略路径和成本后表现。 | `artifact_id`, `manifest_id`, `strategy_definition`, `position_limit_definition`, `execution_assumptions`, `benchmark_definition`, `cost_definition`, `max_drawdown`, `turnover` | portfolio runner | simulation policy、operations | partial |
| `replay_alignment` | 单票 recommendation replay 与标签对齐。 | `artifact_id`, `manifest_id`, `recommendation_key`, `label_definition`, `entry_rule`, `exit_rule`, `validation_status`, `stock_return`, `benchmark_return` | replay runner | frontend replay、historical validation | partial |
| `frontend_projection_manifest` | 前端首屏和聚合读数的轻量投影清单。 | `projection_name`, `version`, `generated_at`, `source_artifact_ids`, `row_count`, `staleness_status`, `fallback_reason` | projection builder | API / SPA | partial |
| `manual_llm_source_packet` | 手动 LLM 研究上下文和来源包。 | `source_packet_id`, `target_login`, `symbol`, `recommendation_key`, `as_of_time`, `core_quant_ref`, `source_links`, `packet_hash` | context pack builder | manual review worker | usable |
| `shortpick_validation_snapshot` | 短投候选的 official / diagnostic 后验验证。 | `snapshot_id`, `run_id`, `candidate_id`, `symbol`, `validation_mode`, `signal_available_at`, `entry_trade_day`, `tradeability_status`, `benchmark_map` | shortpick validation worker | shortpick feedback、history replay | partial |
| `autonomous_flow_trial_report` | 自运行流程试验每轮评估与重跑依据。 | `trial_id`, `flow_version`, `input_contracts`, `subtask_outputs`, `review_scores`, `rerun_triggers`, `accepted_outputs`, `rejected_outputs` | main autonomous process | PROCESS / DECISIONS 固化前审阅 | scaffold |

## 8. Module Interface Matrix

接口 id 采用 `iface.provider.consumer.contract.vN`。这里的接口是设计合同，不代表已经存在代码 API。

| Interface ID | Provider | Consumer | Contract Object | 失败 / 降级规则 | 成熟度 |
| --- | --- | --- | --- | --- | --- |
| `iface.scheduler.phase5-cycle-ledger.v1` | Phase 5 scheduler | cycle ledger / operations | `phase5.cycle.started.v1`, `phase5_cycle_ledger` | cycle 无法落库时停止本轮。 | partial |
| `iface.runner.phase5-artifact-ledger.v1` | Phase 5 runners | cycle ledger / reviewer | `phase5.artifact.produced.v1`, registered artifact families | artifact 不可解析时触发 recovery。 | partial |
| `iface.gate.phase5-scheduler.v1` | gate evaluator | scheduler / projection builder | `phase5.gate.evaluated.v1`, `phase5_gate_readout` | blocked / insufficient 时只能降级推进。 | partial |
| `iface.projection.publish-verifier.v1` | projection builder | publish verifier / frontend | `phase5.projection.refreshed.v1`, `frontend_projection_manifest` | 投影 stale 时页面显示待补，不请求内补跑。 | partial |
| `iface.recovery.scheduler-reviewer.v1` | recovery runner | scheduler / reviewer | `phase5.recovery.recorded.v1`, `phase5_recovery_ticket` | 连续失败升级为 blocked。 | partial |
| `iface.validation.recommendation-projection.v1` | validation runner | recommendation projection | `rolling_validation_manifest`, `validation_metrics` | 缺 artifact 时 `historical_validation.status != verified`。 | usable |
| `iface.policy.operations-workbench.v1` | phase5 policy runner | operations workbench | `phase5_holding_policy_study`, `artifact.holding_policy_study.created.v1` | gate blocked 时输出 non-promotion。 | partial |
| `iface.recommendation.manual-llm-context.v1` | recommendation projection | manual LLM context builder | `manual_llm_source_packet`, `recommendation.projected.v1` | source packet 缺失时手动研究失败，不影响主推荐。 | usable |
| `iface.manual-llm.recommendation-projection.v1` | manual LLM worker | recommendation projection / frontend | `manual_llm_review.completed.v1` | 只写 manual layer 和 disagreements。 | usable |
| `iface.shortpick.validation-feedback.v1` | shortpick validation worker | feedback projection / history replay | `shortpick_validation_snapshot`, `shortpick.validation_snapshot.created.v1` | official 聚合只读 official + tradeable 样本。 | partial |
| `iface.projection.api-spa.v1` | projection builder | API / SPA | `frontend_projection_manifest`, `frontend.projection.updated.v1` | API 只读小 payload，缺投影显示待补。 | partial |
| `iface.main.subagent-contract.v1` | main autonomous process | subagents | Context Pack、owned files、maturity matrix、registered ids | 越权文件或未注册引用触发重跑。 | scaffold |

## 9. 冲突与锁域

| Lock Domain | 资源 | Trial B 并行规则 |
| --- | --- | --- |
| `canonical_status_docs` | `PROJECT_STATUS.json`, `PROCESS.md`, `DECISIONS.md`, `PROJECT_PLAN.md` | 只允许主进程在固化阶段写，子进程禁止写。 |
| `global_protocol` | `TRIAL_B_GLOBAL_PROTOCOL_CN.md` 和后续正式 registry | 同一轮只能一个子任务写；模块任务只读。 |
| `module_design_docs` | `TRIAL_B_*_DESIGN_CN.md` | 可并行，但 owned file 必须 disjoint。 |
| `artifact_data` | `data/artifacts`、runtime artifact store、DB artifact tables | 设计任务只读；实现任务必须声明 writer。 |
| `sqlite_write_lock` | 日刷、短投验证、历史回放、投影重建 | 写任务不能无脑并行，需排队或维护窗口。 |
| `runtime_publish` | `~/codex/runtime/projects/ashare-dashboard`、release manifest、LaunchAgent | Trial B 子进程禁止发布。 |
| `claim_ceiling` | 用户可见表达强度 | 任一模块提升表达强度都必须引用同一 gate readout。 |

## 10. Trial B 引用规则

后续 Trial B 模块设计必须遵守：

- 所有跨模块事件只能引用第 6 节和第 12.1 节已注册的 `Canonical Event ID`。
- 所有 durable artifact 只能引用第 7 节和第 12.2 节已注册的 `Artifact Family ID`。
- 所有模块接口只能引用第 8 节和第 12.3 节已注册的 `Interface ID`。
- 禁止继续使用 Trial A 未版本化事件：`phase5.cycle.started`、`phase5.artifact.produced`、`phase5.gate.evaluated`、`phase5.projection.refreshed`、`phase5.recovery.recorded`。
- 如确需新增 id，模块文档只能写入 `proposed_event` / `proposed_artifact_family` / `proposed_interface`，不得把它当成已注册依赖。
- 模块文档的开放问题必须分类为 `architecture_decision`、`implementation_choice` 或 `research_unknown`。
- 任一引用未注册 id 的模块设计必须触发重跑，不能靠最终汇总口头解释。

## 11. 开放问题分类

### 11.1 `architecture_decision`

| 问题 | 影响范围 | Trial B 处理 |
| --- | --- | --- |
| Registry 的正式形态是 Markdown、JSON Schema，还是 DB 表。 | 多 agent 设计、实现验收、脚本检查。 | Trial B 先用 Markdown appendix，后续实现前必须决定机器格式。 |
| `phase5_cycle_ledger` 和 `phase5_recovery_ticket` 的持久化位置。 | 调度、恢复、回放、审计。 | 当前只注册 artifact family，不决定落库实现。 |
| `claim_ceiling` 是否抽成公共 gate 服务。 | recommendation、Phase 5、Short Pick Lab、frontend。 | 当前只定义 gate readout 语义。 |
| `runtime.publish.verified.v1` 是否进入 cycle ledger。 | 发布验收、项目状态、复盘。 | 子进程不产生该事件，主进程固化时再决定。 |

### 11.2 `implementation_choice`

| 问题 | 约束 |
| --- | --- |
| Markdown registry 检查脚本用 `rg`、markdown parser 还是后续 JSON 转换。 | 必须能检查反引号中的 canonical id。 |
| `cycle_id` 使用交易日 slot 还是 manifest hash。 | 必须稳定、可排序、可追溯输入合同版本。 |
| projection freshness 阈值如何配置。 | 页面显示必须用业务时间，不暴露内部算法。 |
| recovery retry 间隔和次数如何配置。 | 不得让长任务堵住 SQLite 热路径。 |

### 11.3 `research_unknown`

| 问题 | 所需证据 |
| --- | --- |
| holding-policy redesign 是否能改善 after-cost profitability。 | `profitability_signal_threshold_sweep_v1` 和 `construction_max_position_count_sweep_v1` artifact。 |
| `10d / 20d / 40d` horizon 是否收敛。 | 扩大样本后的 rolling validation artifact。 |
| Short Pick Lab official 样本能否支持题材聚合结论。 | 多轮 official validation snapshot 与 topic registry evidence。 |
| claim ceiling 文案是否足够清晰。 | PC / 手机 served 页面可用性验证。 |

## 12. 机器可校验 Registry Appendix

本节是 Trial B 的脚本扫描入口。后续检查脚本可以只读取本节表格中反引号包裹的 id，构建 allowlist。模块设计引用 registry id 时必须使用完全一致的反引号 id。

### 12.1 Canonical Event IDs

| id | status |
| --- | --- |
| `phase5.cycle.started.v1` | registered |
| `phase5.artifact.produced.v1` | registered |
| `phase5.gate.evaluated.v1` | registered |
| `phase5.projection.refreshed.v1` | registered |
| `phase5.recovery.recorded.v1` | registered |
| `artifact.validation_manifest.created.v1` | registered |
| `artifact.validation_metrics.created.v1` | registered |
| `artifact.portfolio_backtest.created.v1` | registered |
| `artifact.holding_policy_study.created.v1` | registered |
| `recommendation.projected.v1` | registered |
| `manual_llm_review.requested.v1` | registered |
| `manual_llm_review.completed.v1` | registered |
| `shortpick.run.completed.v1` | registered |
| `shortpick.validation_snapshot.created.v1` | registered |
| `frontend.projection.updated.v1` | registered |
| `runtime.publish.verified.v1` | registered |

### 12.2 Artifact Family IDs

| id | status |
| --- | --- |
| `phase5_cycle_ledger` | registered |
| `phase5_recovery_ticket` | registered |
| `phase5_gate_readout` | registered |
| `rolling_validation_manifest` | registered |
| `validation_metrics` | registered |
| `phase5_holding_policy_study` | registered |
| `portfolio_backtest` | registered |
| `replay_alignment` | registered |
| `frontend_projection_manifest` | registered |
| `manual_llm_source_packet` | registered |
| `shortpick_validation_snapshot` | registered |
| `autonomous_flow_trial_report` | registered |

### 12.3 Module Interface IDs

| id | status |
| --- | --- |
| `iface.scheduler.phase5-cycle-ledger.v1` | registered |
| `iface.runner.phase5-artifact-ledger.v1` | registered |
| `iface.gate.phase5-scheduler.v1` | registered |
| `iface.projection.publish-verifier.v1` | registered |
| `iface.recovery.scheduler-reviewer.v1` | registered |
| `iface.validation.recommendation-projection.v1` | registered |
| `iface.policy.operations-workbench.v1` | registered |
| `iface.recommendation.manual-llm-context.v1` | registered |
| `iface.manual-llm.recommendation-projection.v1` | registered |
| `iface.shortpick.validation-feedback.v1` | registered |
| `iface.projection.api-spa.v1` | registered |
| `iface.main.subagent-contract.v1` | registered |

### 12.4 Deprecated Trial A Event IDs

这些 id 只用于迁移检查，不允许 Trial B 模块继续引用。

| id | replacement |
| --- | --- |
| `phase5.cycle.started` | `phase5.cycle.started.v1` |
| `phase5.artifact.produced` | `phase5.artifact.produced.v1` |
| `phase5.gate.evaluated` | `phase5.gate.evaluated.v1` |
| `phase5.projection.refreshed` | `phase5.projection.refreshed.v1` |
| `phase5.recovery.recorded` | `phase5.recovery.recorded.v1` |

## 13. 验收标准

- 本文件正式注册 Trial A 中合理的 Phase 5 事件，并提供版本化替代。
- 本文件包含 canonical event ids、artifact family ids 和 module interface ids 的机器可校验 appendix。
- 后续 Trial B 模块设计可以用第 12 节作为 allowlist，检查未注册引用。
- 文档保留 `stock_dashboard` 的 Phase 5、Short Pick Lab、manual LLM review、runtime publish、simulation-only 和 claim ceiling 边界。
- 文档没有宣称 production，没有新增真实交易能力，没有要求子进程发布 runtime。

## 14. 子进程自评

改动文件：

- `docs/contracts/autonomous-flow-trial/TRIAL_B_GLOBAL_PROTOCOL_CN.md`

自评风险：

- Registry appendix 仍是 Markdown 表格，只能支持轻量脚本扫描，不等于正式 schema 系统。
- `phase5_cycle_ledger`、`phase5_recovery_ticket`、`phase5_gate_readout` 的落库位置仍是架构决策，不能直接进入实现。
- 事件 payload 只定义最小字段，后续实现前需要补 schema 校验和兼容策略。
- 本文件允许 `runtime.publish.verified.v1` 作为主进程事件，但 Trial B 子进程仍禁止发布或产生该事件。

未做事项：

- 未修改代码。
- 未启动服务。
- 未发布 runtime。
- 未运行浏览器验收。
- 未提交 git。
- 未更新 `PROJECT_STATUS.json`、`PROCESS.md`、`DECISIONS.md`。
