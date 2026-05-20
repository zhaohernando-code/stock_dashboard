# Trial B Phase 5 自运行纵向切片设计

状态：Trial B draft  
所属流程：`docs/contracts/AUTONOMOUS_DEVELOPMENT_FLOW_CN.md`  
上游协议：`docs/contracts/autonomous-flow-trial/TRIAL_B_GLOBAL_PROTOCOL_CN.md`  
适用范围：`stock_dashboard` Phase 5 研究、artifact、gate、projection、发布验收与回放调度的无人介入纵向闭环  
成熟度：`partial -> usable`，不声明 production SLA

## 1. 目标

本设计重跑 Trial A 的 Phase 5 纵向切片，目标是保留 Trial A 中有价值的最小闭环，同时修复“模块文档自行声明事件和接口”的问题。

本轮目标：

- 让 Phase 5 在无人持续介入时，按“启动周期 -> 产出 artifact -> 评估 gate -> 刷新 projection -> 记录恢复 -> 安排下一轮”的最小链路推进。
- 所有跨模块事件、artifact family、module interface 只引用 Trial B 全局协议中已经注册的 id。
- 把 `Phase5Cycle`、`ResearchArtifact`、`GateReadout`、`ProjectionSnapshot`、`RecoveryTicket` 保留为逻辑实体，并明确映射到 Trial B registry。
- 保留 `simulation_only`、manual LLM review 不进入核心评分、holding-policy 不提升 claim ceiling 的边界。
- 在外部数据、LLM、SQLite 写锁、artifact 缺失、schema 漂移、发布验收阻塞时，优先自动降级、重试、记录 ticket 或安排下一轮任务，不等待人工口头介入。

## 2. 非目标

- 不实现真实交易、券商路由、实盘自动下单或自动组合调仓。
- 不把 Phase 5 holding policy、promotion gate、topic registry 或自运行编排声明为 production。
- 不新增 Trial B 全局协议之外的事件、artifact family 或接口。
- 不重写现有研究算法、页面、发布脚本或数据库结构。
- 不把 watchdog 单一开关作为自恢复核心机制。
- 不要求子进程启动服务、发布 runtime、提交 git，或更新 `PROJECT_STATUS.json`、`PROCESS.md`、`DECISIONS.md`。

## 3. 当前成熟度

Phase 5 当前处于 `partial`，目标是通过本切片收敛到 `usable` 前置条件。

已具备：

- 已有 validation、holding-policy、portfolio backtest、replay、frontend projection 等 artifact 或投影路径。
- 已有 runtime publish、localhost/canonical served 验收和 artifact-backed validation 的项目规则。
- 已有 Short Pick Lab、manual LLM review、simulation-only、claim ceiling 等边界经验。

仍不足：

- 自运行 cycle、recovery、gate readout 还没有统一 durable ledger。
- Trial A 的模块文档曾引用未注册事件，说明全局协议和模块设计之间缺少硬约束。
- Registry 仍是 Markdown appendix，暂时只适合轻量脚本扫描，尚未升级为 JSON Schema 或 DB 表。
- 发布验收、canonical route、SQLite 写锁和样本窗口不足仍需要分层降级，不能包装成稳定生产 SLA。

因此本设计只写到 `partial -> usable`：允许定义状态、失败恢复、测试门禁和最小接口语义，不写容量指标、事故演练、权限审计或 production SLA。

## 4. 引用协议清单

本文只引用下列 Trial B 已注册 id。后续检查脚本可以按本节和 `TRIAL_B_GLOBAL_PROTOCOL_CN.md` 第 12 节做 allowlist 校验。

### 4.1 Registered Events

| id | 本文用途 |
| --- | --- |
| `phase5.cycle.started.v1` | 标记一轮 Phase 5 自运行周期启动。 |
| `phase5.artifact.produced.v1` | 标记研究、回放、投影源 artifact 已持久化。 |
| `phase5.gate.evaluated.v1` | 标记 claim ceiling、gate 状态和下一步动作已确定。 |
| `phase5.projection.refreshed.v1` | 标记 Phase 5 面向发布验收的 projection 已刷新。 |
| `phase5.recovery.recorded.v1` | 标记失败分类和自动恢复动作已落 durable 记录。 |
| `artifact.validation_manifest.created.v1` | 标记 rolling / walk-forward 实验 manifest 已生成。 |
| `artifact.validation_metrics.created.v1` | 标记 validation metrics 已生成。 |
| `artifact.portfolio_backtest.created.v1` | 标记组合回测 artifact 已生成。 |
| `artifact.holding_policy_study.created.v1` | 标记 holding-policy 研究 artifact 已生成。 |
| `frontend.projection.updated.v1` | 标记 API / SPA 可读的轻量投影已更新。 |
| `runtime.publish.verified.v1` | 只作为主进程发布验收事实引用，Trial B 子进程不得产生。 |

### 4.2 Registered Artifact Families

| id | 本文用途 |
| --- | --- |
| `phase5_cycle_ledger` | 持久化 `Phase5Cycle`。 |
| `phase5_recovery_ticket` | 持久化 `RecoveryTicket`。 |
| `phase5_gate_readout` | 持久化 `GateReadout`。 |
| `rolling_validation_manifest` | 表达 Phase 5 validation manifest。 |
| `validation_metrics` | 表达 Phase 5 validation 结果。 |
| `phase5_holding_policy_study` | 表达 holding-policy gate、governance 和 redesign 事实。 |
| `portfolio_backtest` | 表达 simulation portfolio 路径和成本后表现。 |
| `replay_alignment` | 表达单票 recommendation replay 与标签对齐。 |
| `frontend_projection_manifest` | 持久化 `ProjectionSnapshot` 的最小清单。 |
| `autonomous_flow_trial_report` | 主进程汇总 Trial B 评审与重跑依据。 |

### 4.3 Registered Interfaces

| id | 本文用途 |
| --- | --- |
| `iface.scheduler.phase5-cycle-ledger.v1` | 调度器创建 cycle ledger 的合同。 |
| `iface.runner.phase5-artifact-ledger.v1` | runner 向 ledger / reviewer 报告 registered artifact 的合同。 |
| `iface.gate.phase5-scheduler.v1` | gate evaluator 向 scheduler / projection builder 输出 gate readout 的合同。 |
| `iface.projection.publish-verifier.v1` | projection builder 向 publish verifier / frontend 输出投影的合同。 |
| `iface.recovery.scheduler-reviewer.v1` | recovery runner 向 scheduler / reviewer 记录恢复事实的合同。 |
| `iface.validation.recommendation-projection.v1` | validation runner 向 recommendation projection 提供验证事实的合同。 |
| `iface.policy.operations-workbench.v1` | phase5 policy runner 向 operations workbench 输出 policy 事实的合同。 |
| `iface.projection.api-spa.v1` | projection builder 向 API / SPA 提供只读小 payload 的合同。 |
| `iface.main.subagent-contract.v1` | 主进程约束子进程 owned file、成熟度和 registered id 的合同。 |

## 5. 领域模型

为保持 `partial -> usable` 成熟度，本切片只保留 5 个逻辑实体。

### 5.1 `Phase5Cycle`

含义：一次 Phase 5 自运行周期，覆盖研究、artifact、gate、projection、发布验收和下一轮调度。

持久化映射：

- 必须映射到 `phase5_cycle_ledger`。
- 落库位置仍属于 `architecture_decision`，可以是现有 typed artifact store、ops ledger 或后续正式表，但不能只留在会话上下文。

最小字段：

- `cycle_id`
- `trigger`
- `scope`
- `status`
- `started_at`
- `finished_at`
- `input_contract_versions`
- `next_action`

状态上限：

- `planned`
- `running`
- `degraded`
- `blocked`
- `completed`

### 5.2 `ResearchArtifact`

含义：Phase 5 周期中产生的可追溯研究、验证、回放或投影源产物。

持久化映射：

- validation manifest 映射到 `rolling_validation_manifest`。
- validation metrics 映射到 `validation_metrics`。
- holding-policy study 映射到 `phase5_holding_policy_study`。
- portfolio path / simulation study 映射到 `portfolio_backtest`。
- recommendation replay 映射到 `replay_alignment`。
- 面向前端的轻量投影清单映射到 `frontend_projection_manifest`。

最小字段：

- `artifact_id`
- `artifact_family`
- `schema_version`
- `as_of_date`
- `lineage_ref`
- `source_cycle_id`

### 5.3 `GateReadout`

含义：当前研究事实允许系统对用户表达到什么强度，以及下一步应自动推进什么任务。

持久化映射：

- 必须映射到 `phase5_gate_readout`。
- 与 holding-policy 相关的事实源可以追溯到 `phase5_holding_policy_study`。

最小字段：

- `gate_id`
- `cycle_id`
- `gate_status`
- `failing_gate_ids`
- `incomplete_gate_ids`
- `claim_ceiling`
- `next_action`

约束：

- gate 不通过时只能输出 non-promotion、continue tracking、redesign 或 degraded。
- recovery 不得提升 `claim_ceiling`。
- LLM manual review 不得覆盖 `GateReadout`。

### 5.4 `ProjectionSnapshot`

含义：面向 API / SPA / operations workbench 的只读轻量投影。

持久化映射：

- 必须映射到 `frontend_projection_manifest`。

最小字段：

- `projection_name`
- `version`
- `generated_at`
- `source_artifact_ids`
- `row_count`
- `staleness_status`
- `fallback_reason`

约束：

- 页面请求不得临时跑研究、行情同步、LLM 或 DB 写入。
- 缺 source artifact 时只能输出 degraded projection。

### 5.5 `RecoveryTicket`

含义：一次失败分类、自动恢复动作和最终推进状态。

持久化映射：

- 必须映射到 `phase5_recovery_ticket`。
- 落库位置仍属于 `architecture_decision`，但必须能被下一轮 cycle 查询。

最小字段：

- `ticket_id`
- `cycle_id`
- `failed_step`
- `failure_class`
- `recovery_action`
- `retry_count`
- `final_status`

约束：

- 恢复动作不得绕过 gate。
- 连续恢复失败升级为 `blocked`，不等待人工口头介入。

## 6. 核心流程

本切片只定义 3 条核心流程，避免把当前阶段扩成完整任务平台。

### 6.1 流程 A：cycle 启动到 artifact 产出

目标：冻结输入合同，生成或复用 Phase 5 研究 artifact，并让后续 gate 和 projection 能追溯来源。

步骤：

1. 调度器按 `iface.scheduler.phase5-cycle-ledger.v1` 创建 `phase5_cycle_ledger`。
2. 记录 `phase5.cycle.started.v1`，payload 至少包含 `cycle_id`、`trigger`、`scope`、`input_contract_versions`、`started_at`。
3. validation runner 生成 `rolling_validation_manifest`，并记录 `artifact.validation_manifest.created.v1`。
4. validation runner 生成 `validation_metrics`，并记录 `artifact.validation_metrics.created.v1`。
5. phase5 policy runner 生成 `phase5_holding_policy_study`，并记录 `artifact.holding_policy_study.created.v1`。
6. portfolio runner 需要组合路径时生成 `portfolio_backtest`，并记录 `artifact.portfolio_backtest.created.v1`。
7. replay runner 有可用前向窗口时生成 `replay_alignment`。
8. runner 按 `iface.runner.phase5-artifact-ledger.v1` 为每个 registered artifact 记录 `phase5.artifact.produced.v1`。

继续条件：

- artifact family 在 Trial B registry 中已注册。
- artifact schema version 可识别。
- lineage 能追溯到本轮 `cycle_id` 或明确的历史 artifact。

降级条件：

- 外部数据超时时复用未过期历史 artifact，并在后续 gate 中标记 stale/degraded。
- 样本不足时保持 research candidate 或 continue tracking，不生成强结论。
- LLM 失败不阻塞本流程，因为 LLM 不属于核心评分。

### 6.2 流程 B：gate 评估到 projection 刷新

目标：把研究事实转成用户可见表达上限和只读投影，不让页面请求补跑重任务。

步骤：

1. gate evaluator 读取 `rolling_validation_manifest`、`validation_metrics`、`phase5_holding_policy_study`、`portfolio_backtest`、`replay_alignment`。
2. gate evaluator 生成 `phase5_gate_readout`。
3. 记录 `phase5.gate.evaluated.v1`，payload 至少包含 `cycle_id`、`gate_id`、`gate_status`、`claim_ceiling`、`next_action`、`blocking_reasons`。
4. projection builder 只读取 registered artifacts 和 `phase5_gate_readout`，生成 `frontend_projection_manifest`。
5. 记录 `phase5.projection.refreshed.v1`，payload 至少包含 `cycle_id`、`projection_id`、`projection_family`、`source_artifact_ids`、`freshness_at`、`staleness_status`。
6. API / SPA 只通过 `iface.projection.api-spa.v1` 读取 `frontend_projection_manifest`。
7. 面向前端聚合更新时，可以记录 `frontend.projection.updated.v1`。

继续条件：

- projection 能追溯 source artifact。
- 用户可见文案不强于 `claim_ceiling`。
- 缺字段能以 `fallback_reason` 表达，而不是返回裸 500 或假数据。

降级条件：

- 缺 source artifact 时生成 degraded projection。
- gate blocked 时显示 non-promotion / needs-redesign / continue tracking，不显示 promotion。
- projection stale 时页面显示业务时间和待补原因，不在请求路径补跑研究。

### 6.3 流程 C：发布验收到恢复与下一轮调度

目标：把发布验收、失败恢复和下一轮任务都变成 durable 事实，避免卡在人工等待。

步骤：

1. projection builder 按 `iface.projection.publish-verifier.v1` 把 `frontend_projection_manifest` 提供给 publish verifier。
2. 子进程只设计合同；真正发布和 `runtime.publish.verified.v1` 只能由主进程 closeout 产生。
3. 若发布、canonical route、localhost API、schema 或 DB lock 失败，recovery runner 生成 `phase5_recovery_ticket`。
4. 记录 `phase5.recovery.recorded.v1`，payload 至少包含 `cycle_id`、`ticket_id`、`failed_step`、`failure_class`、`recovery_action`、`final_status`。
5. scheduler 读取 `phase5_gate_readout`、`phase5_recovery_ticket` 和 projection 状态，安排下一轮 `continue_tracking`、`run_redesign`、`expand_sample`、`rebuild_projection`、`retry_publish_verification` 或 `stop`。

继续条件：

- 失败能分类，且恢复动作不会提升 claim ceiling。
- localhost / canonical 验收阻塞能分层记录，不把 repo-only 误判为完成。
- 下一步任务能落到明确 action。

降级条件：

- canonical route 因认证或隧道阻塞时，状态为 degraded，等待主进程补验收，不标记 fully completed。
- SQLite 写锁连续失败时转入 blocked 或维护窗口任务，不在前台热路径忙等。
- 样本窗口不足时进入 continue tracking，不重跑无意义研究。

## 7. 依赖协议

| 协议 | 本文用法 |
| --- | --- |
| `AUTONOMOUS_DEVELOPMENT_FLOW_CN.md` | 限制流程阶段、子进程职责、成熟度深度、重跑条件和自恢复策略。 |
| `AUTONOMOUS_FLOW_TRIAL_2026-05-20_CN.md` | 继承 Trial A 评分、重跑触发项和 Trial B 硬约束。 |
| `TRIAL_B_GLOBAL_PROTOCOL_CN.md` | 作为唯一 registry 来源，本文不得引用未注册 id。 |
| `PROJECT_RULES.md` | 继承 runtime publish、canonical served 验收、policy audit、UI 和 live-facing 完成定义。 |
| `PROCESS.md` | 继承 SQLite 写锁、projection read-only、artifact lineage、浏览器验收、短投回放等反回归原则。 |

## 8. 数据 / API / 事件契约

### 8.1 数据契约

| 逻辑实体 | Trial B registered artifact family | 最小要求 | 未决项 |
| --- | --- | --- | --- |
| `Phase5Cycle` | `phase5_cycle_ledger` | 可按 `cycle_id` 查询状态、输入合同版本和下一步动作。 | 落库位置是 `architecture_decision`。 |
| `ResearchArtifact` | `rolling_validation_manifest` / `validation_metrics` / `phase5_holding_policy_study` / `portfolio_backtest` / `replay_alignment` | 必须有 schema version、lineage、source cycle 或历史来源。 | 历史 artifact 兼容策略是 `implementation_choice`。 |
| `GateReadout` | `phase5_gate_readout` | 必须显式输出 `claim_ceiling`、`gate_status` 和 `next_action`。 | 是否抽成公共 gate 服务是 `architecture_decision`。 |
| `ProjectionSnapshot` | `frontend_projection_manifest` | 必须只读、小 payload、可追 source artifacts。 | freshness 阈值是 `implementation_choice`。 |
| `RecoveryTicket` | `phase5_recovery_ticket` | 必须记录失败分类、恢复动作、重试次数和最终状态。 | 落库位置是 `architecture_decision`。 |

### 8.2 API 契约

本文不要求立刻新增 HTTP API，但后续实现必须满足这些读取语义：

| API 语义 | Consumer | 约束 |
| --- | --- | --- |
| latest Phase 5 cycle | operations / scheduler | 返回 `phase5_cycle_ledger` 最新状态、输入合同版本、next action。 |
| Phase 5 projection | API / SPA | 只读 `frontend_projection_manifest`，不得触发研究、行情同步、LLM 或 DB 写入。 |
| artifact lineage | reviewer / operations | 从 projection 追溯到 registered artifact family 和 source artifact ids。 |
| recovery status | scheduler / reviewer | 返回 `phase5_recovery_ticket`，用于自动重试或 blocked 判断。 |

错误响应约束：

- API 错误必须使用 `detail` 字段。
- 样本不足、外部数据超时、canonical 未验收、projection stale 应返回结构化降级原因。
- 不允许用空值、0 或强文案掩盖缺失数据。

### 8.3 事件契约

本文事件只能使用第 4.1 节列出的 registered events。

| 事件 | 生产者 | 消费者 | 最小 payload |
| --- | --- | --- | --- |
| `phase5.cycle.started.v1` | scheduler | cycle ledger / operations | `cycle_id`, `trigger`, `scope`, `input_contract_versions`, `started_at` |
| `artifact.validation_manifest.created.v1` | validation runner | validation metrics / gate evaluator | `artifact_id`, `experiment_version`, `split_plan_id`, `universe_definition`, `generated_at` |
| `artifact.validation_metrics.created.v1` | validation runner | gate evaluator / projection builder | `artifact_id`, `manifest_id`, `status`, `sample_count`, `coverage_ratio`, `metrics_ref` |
| `artifact.holding_policy_study.created.v1` | phase5 policy runner | gate evaluator / operations | `artifact_id`, `policy_type`, `gate_status`, `governance_action`, `redesign_focus_areas` |
| `artifact.portfolio_backtest.created.v1` | portfolio runner | gate evaluator / operations | `artifact_id`, `manifest_id`, `strategy_definition`, `cost_definition`, `gate_readout_ref` |
| `phase5.artifact.produced.v1` | Phase 5 runners | cycle ledger / reviewer / projection builder | `cycle_id`, `artifact_id`, `artifact_family`, `schema_version`, `as_of_date`, `lineage_ref` |
| `phase5.gate.evaluated.v1` | gate evaluator | scheduler / projection builder | `cycle_id`, `gate_id`, `gate_status`, `claim_ceiling`, `next_action`, `blocking_reasons` |
| `phase5.projection.refreshed.v1` | projection builder | publish verifier / API / SPA | `cycle_id`, `projection_id`, `projection_family`, `source_artifact_ids`, `freshness_at`, `staleness_status` |
| `frontend.projection.updated.v1` | projection builder | API / SPA | `projection_name`, `version`, `generated_at`, `source_artifact_ids`, `staleness_status` |
| `phase5.recovery.recorded.v1` | recovery runner | scheduler / reviewer | `cycle_id`, `ticket_id`, `failed_step`, `failure_class`, `recovery_action`, `final_status` |
| `runtime.publish.verified.v1` | main process closeout | project status / process log | `commit_id`, `release_manifest`, `localhost_result`, `canonical_result` |

事件约束：

- 事件只描述事实，不携带大 payload。
- 事件必须引用 `cycle_id` 或对应 `artifact_id`。
- Trial B 子进程不得产生 `runtime.publish.verified.v1`。

## 9. 失败与恢复

| 失败类型 | 默认恢复动作 | 继续推进条件 | 阻塞条件 |
| --- | --- | --- | --- |
| 外部数据超时 | 复用未过期 artifact，projection 标记 stale/degraded，并安排下轮补抓。 | claim ceiling 不提升，source lineage 可追溯。 | 无可用历史 artifact 且本轮必须生成研究结论。 |
| LLM 超时 | 跳过 manual layer，记录恢复 ticket。 | core quant、validation、policy gate 不依赖 LLM。 | 用户显式要求的手动研究无法产出，且无可降级展示。 |
| SQLite 写锁 | 退避重试，避开短投验证、盘后刷新和投影重建热路径。 | 可读现有 projection 或重试后写入成功。 | 连续失败导致 artifact 不完整。 |
| 样本不足 | gate 输出 insufficient evidence / continue tracking。 | 能安排扩大样本或继续观察。 | 页面仍试图展示强结论。 |
| artifact 缺失 | 按 lineage 重新定位 source artifact，必要时只重建 projection。 | source artifact 可定位或可安全降级。 | projection 与 source artifact 无法对齐。 |
| schema 漂移 | 按 schema version 兼容解析，记录 repair 任务。 | 可安全降级显示。 | 同一字段被多个 consumer 解释成不同语义。 |
| 发布验收阻塞 | 分层记录 repo、runtime、localhost、canonical 状态。 | localhost served 通过且 canonical 阻塞原因明确。 | 用户可见代码已改但无法验证真实 served 页面。 |

恢复记录要求：

- 每次恢复必须写入 `phase5_recovery_ticket`。
- 每次恢复必须记录 `phase5.recovery.recorded.v1`。
- 恢复动作不能提升 `claim_ceiling`。
- 连续恢复失败时，scheduler 必须把下一步设为 blocked 或维护窗口任务，不等待人工口头介入。

## 10. 验收标准

Trial B 文档验收：

- 文档包含目标、非目标、当前成熟度、领域模型、核心流程、依赖协议、数据/API/事件契约、失败与恢复、验收标准、测试与门禁、开放问题分类。
- 文档明确写出引用协议清单。
- 文档只引用 `TRIAL_B_GLOBAL_PROTOCOL_CN.md` 已注册的 event ids、artifact family ids 和 module interface ids。
- 文档保留 `partial -> usable` 成熟度，不写 production SLA。
- `Phase5Cycle`、`ResearchArtifact`、`GateReadout`、`ProjectionSnapshot`、`RecoveryTicket` 都映射到 registered artifact family 或 `architecture_decision`。

后续实现验收：

- 一轮 cycle 能产生 `phase5_cycle_ledger`，并可追溯输入合同版本。
- registered artifact 产出后能记录 `phase5.artifact.produced.v1`。
- gate evaluator 能生成 `phase5_gate_readout`，并阻止强于 `claim_ceiling` 的用户可见表达。
- projection builder 能生成 `frontend_projection_manifest`，API / SPA 只读投影，不触发研究或写库。
- 任一失败至少生成 `phase5_recovery_ticket`，下一轮能据此继续、降级或 blocked。
- live-facing 实现只有在主进程发布 runtime 并完成 served 验证后，才能被标记完成。

## 11. 测试与门禁

文档门禁：

- `git diff --check` 必须通过。
- 必需章节必须全部存在。
- 检查本文反引号中的 event ids、artifact family ids、module interface ids，必须均存在于 `TRIAL_B_GLOBAL_PROTOCOL_CN.md` 第 12 节。
- 不得出现 Trial A 的未版本化事件引用。
- 不得新增未注册 event、artifact family 或 interface。

实现门禁：

- artifact contract 测试覆盖 `phase5_cycle_ledger`、`phase5_gate_readout`、`phase5_recovery_ticket`、`frontend_projection_manifest`。
- projection read-only 测试确认页面 API 不触发研究、行情同步、LLM 或 DB 写入。
- gate 降级测试覆盖 insufficient evidence、needs redesign、degraded、blocked。
- recovery 分类测试覆盖外部数据超时、LLM 超时、SQLite 写锁、artifact 缺失、schema 漂移、发布验收阻塞。
- policy audit 在任何阈值、gate、公式、字面量变更后必须通过。
- live-facing 代码变更必须由主进程执行 runtime publish、localhost served 验证和 canonical route 验证；子进程豁免。

## 12. 开放问题分类

### 12.1 `architecture_decision`

- `phase5_cycle_ledger`、`phase5_recovery_ticket`、`phase5_gate_readout` 的正式持久化位置：typed artifact store、ops ledger，还是新增 DB 表。
- Registry 的正式形态：继续 Markdown appendix，还是升级为 JSON Schema / DB registry / 代码生成 allowlist。
- `runtime.publish.verified.v1` 是否进入 `phase5_cycle_ledger`，还是只保留在主进程 closeout 和项目状态中。
- `claim_ceiling` 是否抽成跨 recommendation、Phase 5、Short Pick Lab 的公共 gate 服务。

### 12.2 `implementation_choice`

- `cycle_id` 使用交易日 slot、manifest hash，还是二者组合。
- projection freshness 阈值如何和页面“截至 MM/DD HH:MM”文案对齐。
- SQLite 写锁退避次数、间隔和维护窗口如何配置。
- artifact lineage API 返回完整链路，还是返回 source ids 后由下钻接口展开。
- Markdown registry 检查脚本使用 `rg`、markdown parser，还是后续 JSON 转换。

### 12.3 `research_unknown`

- holding-policy redesign 是否能改善 after-cost profitability 和 portfolio construction。
- 扩大样本后，`10d / 20d / 40d` horizon 是否能从 split leadership 收敛。
- replay 前向窗口积累速度是否足以支撑自动复盘，还是需要更保守的 continue tracking 机制。
- Phase 5 当前 active watchlist universe 是否足以作为研究 universe，还是需要更宽样本边界。

## 13. 子进程自评

改动文件：

- `docs/contracts/autonomous-flow-trial/TRIAL_B_PHASE5_VERTICAL_SLICE_DESIGN_CN.md`

自评风险：

- 本文已经按 Trial B registry 收敛引用，但 registry 仍是 Markdown appendix，不是正式 schema 系统。
- `phase5_cycle_ledger`、`phase5_recovery_ticket`、`phase5_gate_readout` 的落库位置仍是 `architecture_decision`，实现前必须由主进程收敛。
- 本文只覆盖 `partial -> usable` 纵向切片，没有覆盖 production 级 SLA、安全审计、容量预算或事故演练。

未做事项：

- 未修改代码。
- 未启动服务。
- 未发布 runtime。
- 未运行浏览器验收。
- 未提交 git。
- 未更新 `PROJECT_STATUS.json`、`PROCESS.md`、`DECISIONS.md`。
