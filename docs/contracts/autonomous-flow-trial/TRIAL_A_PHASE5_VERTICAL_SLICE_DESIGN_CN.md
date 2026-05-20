# Trial A Phase 5 自运行纵向切片设计

状态：Trial A draft  
所属流程：`docs/contracts/AUTONOMOUS_DEVELOPMENT_FLOW_CN.md`  
适用范围：`Phase 5 - Real Validation Rebuild and Model Portfolio Policy Research` 的研究、投影、发布、回放纵向链路  
成熟度：`partial`，目标是通过最小闭环推进到 `usable`

## 1. 目标

本设计定义一个最小但完整的 Phase 5 自运行纵向切片，让系统在无人持续介入时，能够围绕“研究 -> durable artifact -> 前端投影 -> 发布/验收 -> 回放/复盘 -> 下一轮调度”持续往下走。

重点目标：

- 让 holding-policy redesign、horizon study、validation manifest、historical replay 和 frontend projection 使用同一批 Phase 5 合同语义。
- 在外部数据、LLM、浏览器验收、样本不足或 SQLite 写锁等常见故障出现时，先自动降级、重试或跳过非关键环节，而不是等待人工。
- 保证每个关键中间结果都有 durable artifact 或 projection 可回查，避免长会话上下文漂移。
- 明确什么时候可以继续推进下一步，什么时候必须停止在 non-promotion / insufficient-evidence / needs-redesign 状态。
- 把发布与回放作为链路结果验证，而不是只看脚本是否运行完成。

## 2. 非目标

- 不设计真实下单、券商交易路由或任何实盘自动执行能力。
- 不把当前 Phase 5 策略提升为 production 级自动持仓承诺。
- 不重写已有研究算法、前端页面或刷新脚本。
- 不用 watchdog 单一开关作为恢复机制。
- 不把 LLM 重新放回核心评分、validation 指标或 policy 晋级逻辑。
- 不承诺固定收益、固定 horizon、固定调仓周期或生产 SLA。

## 3. 当前成熟度

当前 Phase 5 链路整体处于 `partial`：

- 已有 durable artifact 雏形，包括 validation、horizon、holding-policy、replay feedback、strategy slice 和 frontend projection 等路径。
- 已有真实 runtime 发布和 served 页面验收经验，但验收经常受认证、隧道、浏览器状态和数据窗口影响。
- holding-policy 仍是 `research_candidate_only`，promotion gate 当前不是晋级机制，而是 non-promotion / redesign 诊断机制。
- replay 与 validation 的部分阻塞来自真实样本窗口不足，不应由自动化流程强行绕过。
- 目前还缺一层稳定的“自运行编排账本”：记录每轮从研究到发布的 step 状态、输入 artifact、输出 artifact、失败分类、恢复动作和下一步决策。

因此本切片不应写成 production 级平台，而应交付一个 `usable` 前置闭环：能自动运行、自动降级、自动记录、自动决定下一步任务，但仍保留金融研究结论的保守上限。

## 4. 领域模型

为控制 Trial A 复杂度，本切片只引入 5 个核心实体。

### 4.1 `Phase5Cycle`

表示一次 Phase 5 自运行周期。

关键字段：

- `cycle_id`：稳定 ID，例如 `phase5:2026-05-20:postmarket`。
- `trigger`：`scheduled_postmarket | manual_trial | artifact_backfill | recovery_retry`。
- `scope`：本轮覆盖的研究和发布范围。
- `status`：`planned | running | degraded | blocked | completed`。
- `started_at / finished_at`。
- `input_contract_versions`：引用 Phase 5 研究合同、流程合同和 policy config 版本。

### 4.2 `ResearchArtifact`

表示可回查的研究或验证产物。

关键字段：

- `artifact_id`。
- `artifact_type`：`validation_manifest | horizon_study | holding_policy_study | replay_feedback | strategy_slice | frontend_projection`。
- `as_of_date`。
- `benchmark_id`。
- `coverage_status`。
- `payload_schema_version`。
- `source_cycle_id`。

### 4.3 `GateReadout`

表示当前研究事实允许系统做什么。

关键字段：

- `gate_id`。
- `gate_status`：`pass | blocked | insufficient_history | insufficient_evidence | needs_redesign | degraded`。
- `failing_gate_ids`。
- `incomplete_gate_ids`。
- `claim_ceiling`：`observe_only | research_candidate | paper_tracking | promotable_candidate`。
- `next_action`：`continue_tracking | run_redesign | expand_sample | rebuild_projection | publish | stop`。

### 4.4 `ProjectionSnapshot`

表示用户可见或运营可见的轻量投影。

关键字段：

- `projection_id`。
- `projection_type`：`shortpick_replay_summary | operations_summary | simulation_workspace_summary | model_feedback_summary`。
- `source_artifact_ids`。
- `freshness_at`。
- `render_contract_version`。
- `degradation_reason`。

### 4.5 `RecoveryTicket`

表示一次自动恢复动作。

关键字段：

- `ticket_id`。
- `cycle_id`。
- `failed_step`。
- `failure_class`：`external_data_timeout | llm_timeout | db_lock | insufficient_sample | browser_auth | schema_mismatch | artifact_missing | publish_failed`。
- `recovery_action`。
- `retry_count`。
- `final_status`：`recovered | degraded_continue | blocked`。

## 5. 核心流程

本切片只定义 3 条核心流程，避免过早扩成完整调度平台。

### 5.1 流程 A：盘后研究到投影

目标：把 Phase 5 研究链路自动推进到可展示、可回放的 durable 状态。

步骤：

1. 创建 `Phase5Cycle`，冻结本轮输入合同版本。
2. 读取当前可用行情、watchlist、模拟盘和历史 artifact。
3. 生成或刷新 `validation_manifest`，若不足 `480/120/60` 基线则标记 `insufficient_history`。
4. 生成或刷新 `horizon_study`，只允许输出 research leader，不允许在 `pending_phase5_selection` 下批准产品周期。
5. 生成或刷新 `holding_policy_study`，继续写入 `gate_status / governance_status / redesign_diagnostics`。
6. 计算 `GateReadout`，给出本轮 `claim_ceiling` 和 `next_action`。
7. 基于已完成 artifact 刷新 `ProjectionSnapshot`；缺字段时投影缺失原因，不临时跑研究任务。

继续条件：

- 关键 artifact 可写入 durable store。
- schema version 可识别。
- gate readout 能给出明确 `next_action`。

降级条件：

- 外部数据失败但不影响已有 artifact 复用时，继续投影并标记 stale/degraded。
- LLM 失败不阻断主流程，因为 LLM 只属于手动附加分析。
- 样本不足时进入 `insufficient_history`，不视为工程失败。

### 5.2 流程 B：投影发布到 served 验收

目标：确保用户看到的是本轮 durable 结果，而不是 repo-only 或 stale runtime。

步骤：

1. 检查工作树是否可发布；若发布源不干净，由主进程决定是否创建 clean snapshot，本子切片只记录需求。
2. 发布前执行快回归和 policy audit。
3. 发布到 runtime。
4. 验证 localhost API 返回的 projection source artifact 与本轮 `cycle_id` 对齐。
5. 验证 canonical route；认证或隧道异常时分层记录为 `browser_auth` 或 `canonical_route_unverified`，不能直接标记完成。
6. 写入发布验收摘要，供下一轮 cycle 判断是否需要重试发布或只补验收。

继续条件：

- runtime API 能读到目标 projection。
- served 页面不展示强于 `claim_ceiling` 的结论。

降级条件：

- canonical route 因认证阻塞但 localhost served 验证通过时，状态为 `degraded`，下一轮优先补 canonical 验收。
- repo 文档变更不影响 runtime 时，不触发重复发布。

### 5.3 流程 C：回放复盘到下一轮调度

目标：让 historical replay 和 paper tracking 结果自动进入下一轮研究选择，而不是靠人工回忆。

步骤：

1. 读取上一轮 `GateReadout` 与 replay/paper tracking artifact。
2. 判断是否满足 20 交易日前向窗口、样本覆盖、benchmark 和 cost contract。
3. 若 replay 可用，刷新 replay feedback 和 strategy slice projection。
4. 若 holding-policy gate 仍被 after-cost profitability 或 portfolio construction 阻塞，则自动排入 redesign 实验：优先 `profitability_signal_threshold_sweep_v1` 和 `construction_max_position_count_sweep_v1`。
5. 若 horizon 仍 split leadership，则排入扩大样本或双轨规则收敛任务。
6. 输出下一轮 `Phase5Cycle` 的 `planned` 任务清单。

继续条件：

- 阻塞能分类为数据窗口不足、研究证据不足或工程失败。
- 下一步能落到明确任务类型：继续观察、扩大样本、重建投影、redesign、补验收。

降级条件：

- 样本窗口不足时只进入继续观察，不启动无意义重跑。
- replay artifact schema 不匹配时，先创建 schema repair 任务，不刷新用户可见结论。

## 6. 依赖的全局协议

本设计依赖以下全局协议。若这些协议尚未在仓库中完整落地，本 Trial A 文档只声明依赖，不自建另一套命名体系。

| 协议 | 当前来源 | 本切片用法 |
| --- | --- | --- |
| 成熟度模型 | `AUTONOMOUS_DEVELOPMENT_FLOW_CN.md` | 限制本设计为 `partial -> usable`，不引入 production SLA |
| Phase 5 研究合同 | `PHASE5_RESEARCH_CONTRACT.md` | 锁定 benchmark、horizon、LLM 边界、simulation-only 执行边界 |
| 可信度整改路线 | `PHASE5_CREDIBILITY_REMEDIATION_PLAN.md` | 决定 P0/P1 优先级和 claim ceiling |
| 流程经验 | `PROCESS.md` | 约束 runtime publish、artifact、SQLite、短投回放和浏览器验收 |
| 项目计划 | `PROJECT_PLAN.md` | 约束 Phase 5 是模拟交易和验证研究，不是实盘交易 |

缺口：

- 还需要正式的 event registry。
- 还需要 artifact schema registry。
- 还需要 module interface matrix。
- 还需要统一的 cycle ledger 存储位置。

这些缺口属于 `architecture_decision`，必须由主进程收敛后再进入实现。

## 7. 数据 / API / 事件契约

### 7.1 数据契约

最小数据写入原则：

- 每轮 cycle 必须有一个 durable `Phase5Cycle` 记录。
- 每个研究结果必须以 `ResearchArtifact` 或现有 typed artifact 形式持久化。
- 每个用户可见摘要必须来自 `ProjectionSnapshot`，页面 API 不临时跑大研究。
- 每个失败恢复必须留下 `RecoveryTicket`，避免下一轮重复卡在同一问题上。

推荐存储映射：

| 逻辑实体 | 可复用现有位置 | Trial A 要求 |
| --- | --- | --- |
| `Phase5Cycle` | 可先落在 artifact metadata 或新增 cycle ledger | 必须可按日期、trigger、status 查询 |
| `ResearchArtifact` | `data/artifacts/` typed artifact store | 必须带 schema version、benchmark、coverage |
| `GateReadout` | `phase5_holding_policy_study` payload + projection summary | 必须显式输出 claim ceiling |
| `ProjectionSnapshot` | `frontend_projections` | 必须只读、小 payload、可追源 |
| `RecoveryTicket` | 可先落 artifact metadata 或 ops ledger | 必须记录失败分类和恢复结果 |

### 7.2 API 契约

Trial A 不要求立刻新增 API，但后续实现必须满足以下读取语义：

| API 语义 | Consumer | 要求 |
| --- | --- | --- |
| `GET latest phase5 cycle` | operations / 调度器 | 返回最新 cycle 状态、输入合同版本、下一步动作 |
| `GET phase5 projections` | 前端 | 只读 projection，不触发研究、行情同步、LLM 或 DB 写入 |
| `GET artifact lineage` | reviewer / operations | 能从 projection 追溯到 source artifact 和 cycle |
| `POST run phase5 cycle` | 调度器或人工试运行 | 只能触发 simulation/research 链路，不触发实盘交易 |

错误响应：

- API 错误必须使用 `detail` 字段。
- 样本不足、canonical 未验收、外部数据超时应返回结构化降级原因，而不是裸 500。

### 7.3 事件契约

在正式 event registry 落地前，本切片只声明最小事件名，后续必须注册后才能实现。

| 事件 | 生产者 | 消费者 | 语义 |
| --- | --- | --- | --- |
| `phase5.cycle.started` | 调度器 | operations / ledger | 一轮 Phase 5 自运行开始 |
| `phase5.artifact.produced` | research runner | projection builder / reviewer | 研究 artifact 已持久化 |
| `phase5.gate.evaluated` | gate evaluator | scheduler / frontend projection | 当前 claim ceiling 与 next action 已确定 |
| `phase5.projection.refreshed` | projection builder | publish verifier / frontend | 用户可见投影已刷新 |
| `phase5.recovery.recorded` | recovery runner | scheduler / reviewer | 失败已分类并执行恢复动作 |

事件约束：

- 事件只描述事实，不携带大 payload。
- 事件必须引用 `cycle_id` 和相关 `artifact_id`。
- 未注册事件不得被子任务自行扩展为实现依赖。

## 8. 失败与恢复

| 失败类型 | 默认恢复动作 | 继续推进条件 | 阻塞条件 |
| --- | --- | --- | --- |
| 外部数据超时 | 使用上一轮 artifact，标记 stale/degraded，并安排下轮补抓 | 已有 artifact 未过期且 claim ceiling 不增强 | 无可用历史 artifact 且本轮必须生成研究结论 |
| LLM 超时 | 跳过 LLM 附加分析，记录失败 | 主评分、validation、policy gate 不依赖 LLM | 用户明确要求的手动研究结果必须产出 |
| SQLite 写锁 | 退避重试，避开短投验证和刷新写任务 | 重试后可读 projection 或 artifact | 连续写入失败导致 artifact 不完整 |
| 样本不足 | 标记 `insufficient_history` 或 `insufficient_evidence` | 能输出继续观察或扩大样本任务 | 页面仍试图展示强结论 |
| artifact 缺失 | 从 typed store 按 lineage 重查，必要时只重建缺失 projection | source artifact 可定位 | source artifact 与 projection 无法对齐 |
| schema 漂移 | 按 schema version 走兼容解析，记录 repair 任务 | 可安全降级显示 | 同一字段被多个 consumer 解释成不同语义 |
| 发布失败 | 不改 runtime，保留 repo 状态，生成补发布任务 | 失败发生在非用户可见文档变更 | 用户可见代码已改但无法发布验证 |
| canonical 验证异常 | 分层检查 auth、tunnel、hydration、route | localhost served 验证通过且 canonical 问题可分类 | localhost 与 canonical 都不可验证 |

关键原则：

- 恢复动作不能提升结论强度。
- 恢复动作不能绕过 Phase 5 claim ceiling。
- 恢复动作必须有 ticket，不能只留在会话上下文。

## 9. 验收标准

Trial A 设计验收：

- 本文档包含流程合同要求的 11 个章节。
- 当前成熟度明确为 `partial -> usable`，没有 production 级 SLA 承诺。
- 核心实体不超过 5 个，核心流程不超过 3 条。
- 所有开放问题按类型分类。
- Phase 5 研究合同中的 benchmark、horizon、LLM 边界和 simulation-only 边界没有被覆盖。

后续实现验收：

- 一次 `Phase5Cycle` 能从研究触发推进到 projection 刷新，并能追溯 source artifact。
- holding-policy gate 被阻塞时，系统自动给出 redesign 或 continue-tracking，而不是等待人工判断。
- 样本不足时，页面和 projection 自动降级，不展示强于研究事实的结论。
- replay 可用时自动刷新回放投影；不可用时说明数据窗口或 schema 缺口。
- 发布链路能区分 repo-only、runtime published、localhost verified、canonical verified 四种状态。
- 任一失败都至少落一条 `RecoveryTicket` 或同等 durable 记录。

## 10. 测试与门禁

最小测试门禁：

- Markdown 结构检查：章节完整、开放问题已分类。
- artifact contract 测试：`phase5_holding_policy_study`、horizon、validation、projection 的关键字段可解析。
- policy audit：新增或修改阈值、gate、公式、字面量时必须通过项目 policy audit。
- projection read-only 测试：前端 projection API 不触发写库、大研究、行情同步或 LLM。
- gate 降级测试：`insufficient_history`、`draft_gate_blocked`、`needs_redesign` 不会生成强产品结论。
- recovery 分类测试：外部数据超时、LLM 超时、DB lock、artifact missing 至少能落到结构化失败类型。

发布门禁：

- live-facing 代码变更必须发布到 runtime。
- localhost served API 必须验证 projection 与 artifact lineage。
- canonical route 必须验证；若认证或隧道阻塞，状态只能是 degraded，不得标记 fully completed。

Trial A 子进程豁免：

- 不启动服务。
- 不发布 runtime。
- 不跑浏览器验收。
- 不提交 git。
- 不更新 `PROJECT_STATUS.json`、`PROCESS.md`、`DECISIONS.md`。

## 11. 开放问题

### 11.1 `architecture_decision`

- `Phase5Cycle` 和 `RecoveryTicket` 应落在现有 typed artifact store、`frontend_projections` 旁路表，还是新增独立 ops ledger？
- event registry、artifact schema registry 和 module interface matrix 的正式文件路径与 owner 是什么？
- publish verification summary 是否也应纳入 cycle ledger，还是继续保留在 release manifest 与 PROCESS 经验之间？
- 调度器是否以 LaunchAgent 为第一实现，还是应先由 repo 内 CLI + automation wrapper 承担？

### 11.2 `implementation_choice`

- `cycle_id` 使用交易日 + slot，还是使用 UTC manifest id？
- projection freshness 的默认过期阈值如何与当前页面“截至 MM/DD HH:MM”文案对齐？
- DB lock 退避次数和退避间隔是否复用已有刷新脚本配置？
- `artifact lineage` 在 API 中返回完整链路，还是只返回 current source ids 并由下钻接口展开？

### 11.3 `research_unknown`

- holding-policy redesign 的两个 primary experiments 是否足以改善 after-cost profitability 和 portfolio construction？
- 扩大样本后，`10d / 20d / 40d` horizon 是否能从 split leadership 收敛为单一主 horizon？
- replay 前向窗口积累速度是否足以支撑短期自动复盘，还是需要更明确的 continue-observation 机制？
- 当前 active watchlist universe 是否足以作为 Phase 5 研究 universe，还是需要在 P1 引入更宽的研究样本边界？

## 12. Trial A 子进程自评

改动文件：

- `docs/contracts/autonomous-flow-trial/TRIAL_A_PHASE5_VERTICAL_SLICE_DESIGN_CN.md`

自评风险：

- 本设计引用了尚未正式落地的 event registry、artifact schema registry 和 module interface matrix，只能作为依赖声明，不能直接进入实现。
- `Phase5Cycle` / `RecoveryTicket` 的落库位置仍是架构决策，后续主进程必须先收敛。
- 当前设计按 `partial -> usable` 控制复杂度，没有覆盖 production 级安全、容量、审计和演练细节。

未做事项：

- 未修改代码。
- 未启动服务。
- 未发布 runtime。
- 未运行浏览器验收。
- 未提交 git。
- 未更新 `PROJECT_STATUS.json`、`PROCESS.md`、`DECISIONS.md`。
