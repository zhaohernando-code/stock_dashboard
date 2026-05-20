# Trial C Registry 与 Claim Ceiling Gate 架构决策

状态：Trial C decision draft  
适用项目：`stock_dashboard` / A 股研究与决策看板  
上游输入：`TRIAL_C_CONTEXT_PACK_CN.md`、`TRIAL_B_GLOBAL_PROTOCOL_CN.md`、`TRIAL_B_PHASE5_VERTICAL_SLICE_DESIGN_CN.md`  
成熟度：`partial -> usable`，不声明 production SLA

## 1. 决策范围

本文只回答两类实现前置架构问题：

- Registry 的正式形态、文件布局和检查策略。
- `claim_ceiling` 是否抽成公共 gate，以及该 gate 的输入、输出和调用点。

本文不修改业务代码、不启动服务、不发布 runtime、不提交 git，也不更新 `PROJECT_STATUS.json`、`PROCESS.md` 或 `DECISIONS.md`。

## 2. 推荐方案

### 2.1 Registry 正式形态

推荐采用“JSON allowlist + JSON Schema 为机器真值源，Markdown appendix 保留为人工镜像”的方案。

核心决策：

- 保留 Markdown appendix，但它只作为人读摘要和设计评审入口，不再作为实现阶段的唯一真值源。
- 引入 JSON allowlist，作为 canonical registry source，覆盖 events、artifact families、module interfaces、deprecated ids、maturity 和 owner。
- 引入 JSON Schema，先覆盖 registry 自身结构和关键 artifact family 的最小字段，不在 Trial C 一次性覆盖所有 payload。
- 暂不引入 DB registry。当前 registry 仍是设计和实现门禁，不是运行态事件查询系统。
- 后续 Context Pack 必须由 JSON allowlist 派生，子进程不得手写 allowlist。

建议文件布局：

| 文件 | 角色 | 阶段 |
| --- | --- | --- |
| `docs/contracts/registry/autonomous_flow_registry.v1.json` | events、artifact families、interfaces、deprecated ids 的 canonical allowlist。 | Trial C 后进入实现前置 |
| `docs/contracts/registry/schemas/autonomous_flow_registry.schema.json` | registry 文件自身 schema。 | Trial C 后进入实现前置 |
| `docs/contracts/registry/schemas/phase5_cycle_ledger.schema.json` | `phase5_cycle_ledger` 最小字段 schema。 | 第一批 |
| `docs/contracts/registry/schemas/phase5_gate_readout.schema.json` | `phase5_gate_readout` 最小字段 schema。 | 第一批 |
| `docs/contracts/registry/schemas/phase5_recovery_ticket.schema.json` | `phase5_recovery_ticket` 最小字段 schema。 | 第一批 |
| `docs/contracts/autonomous-flow-trial/TRIAL_B_GLOBAL_PROTOCOL_CN.md` | 历史设计基线和人工阅读入口。 | 保留 |

### 2.2 Claim Ceiling Gate 正式形态

推荐将 `claim_ceiling` 抽成公共 gate，但第一阶段不是独立网络服务，而是确定性、无副作用的 domain service：

- 形态：纯函数库 + CLI 检查入口 + 可被 scheduler / projection builder / reviewer 调用的内部模块。
- 不读网络、不调用 LLM、不写数据库、不直接发布 runtime。
- 输入必须是已注册 artifact、projection manifest、runtime publish verification 或明确的缺失状态。
- 输出统一落到 `phase5_gate_readout`，并通过 `phase5.gate.evaluated.v1` 表达。
- 任何用户可见强结论、策略晋级、Phase 5 readout、Short Pick Lab 聚合结论，都必须经过该 gate。

是否抽成服务的结论：

- 抽成“公共 gate 服务边界”：是。
- 抽成独立 HTTP / daemon 服务：否，至少在 `partial -> usable` 阶段不做。
- 后续只有当多个 runtime 进程、跨项目调用或审计查询需要共享运行态状态时，才升级为独立服务。

## 3. 备选方案

| 方案 | 描述 | 结论 |
| --- | --- | --- |
| 继续只用 Markdown appendix | 沿用 Trial B 第 12 节，用脚本扫描反引号 id。 | 不推荐。足以做 Trial B 重跑，但实现阶段仍容易漏掉 schema、owner、maturity 和 deprecated replacement。 |
| JSON allowlist + JSON Schema | 用 JSON 作为机器真值源，Markdown 保留为摘要。 | 推荐。迁移成本低，能支撑无人检查和子进程 Context Pack 生成。 |
| DB registry | 将 registry 放入 SQLite 或运行态 DB。 | 暂不推荐。当前 registry 是开发合同，不是高频运行态查询；DB 会放大迁移、锁和发布成本。 |
| 代码生成 allowlist | 从 registry 生成 Python/TypeScript 常量。 | 第二阶段可做。应先稳定 JSON registry，再生成代码，避免生成物反过来变成第二真值源。 |
| Claim gate 内嵌在每个模块 | recommendation、Phase 5、Short Pick Lab 各写自己的 ceiling 规则。 | 不推荐。会出现文案绕 gate、同一证据不同结论、无人流程无法统一降级。 |
| Claim gate 独立 HTTP 服务 | 把 gate 做成常驻服务供各模块调用。 | 暂不推荐。当前没有跨进程强需求，会增加部署、健康检查和发布验收负担。 |
| Claim gate 纯函数 / CLI / 内部模块 | gate 逻辑集中、确定性、可测试，各调用点传入 artifact-backed 输入。 | 推荐。足以统一结论强度，又不扩大运行复杂度。 |

## 4. 取舍依据

### 4.1 与项目约束一致

- 页面 API 不能在请求路径跑研究、行情同步、LLM 或 DB 写入，因此 gate 必须消费预计算 artifact 和 projection。
- SQLite 写锁、短投验证、历史回放和 projection rebuild 不可无脑并发，因此 registry / gate 不应引入新的运行态写热点。
- LLM 不进入核心评分、validation gate 或自动调仓，因此 manual LLM review 只能作为 disagreement 或解释层输入，不能提升 `claim_ceiling`。
- Phase 5 和 Short Pick Lab 保持 simulation-only / research / paper tracking 边界，gate 必须默认 fail closed。

### 4.2 对无人介入能力的提升

JSON registry 能让主进程自动完成以下判断：

- 子进程是否引用未注册 event、artifact family 或 interface。
- 子进程是否继续使用 deprecated id。
- 模块设计是否越过 maturity 上限。
- artifact schema 是否缺少最小字段。
- Context Pack 是否来自同一版本 registry。

公共 claim gate 能让系统自动完成以下判断：

- 当前事实允许显示什么强度的结论。
- 是否只能输出 degraded、continue tracking、non-promotion 或 redesign。
- 缺 artifact、stale projection、runtime publish 未验证时是否必须降级。
- manual LLM review 与 core quant 冲突时是否只能展示 disagreement。

## 5. Registry 文件与检查策略

### 5.1 Registry 最小结构

`autonomous_flow_registry.v1.json` 至少包含：

- `registry_version`
- `generated_from`
- `events`
- `artifact_families`
- `interfaces`
- `deprecated_ids`
- `maturity_domains`
- `claim_ceiling_levels`

每个 event 至少包含：

- `id`
- `status`
- `provider`
- `consumers`
- `min_payload_fields`
- `maturity`

每个 artifact family 至少包含：

- `id`
- `status`
- `schema_ref`
- `provider`
- `consumers`
- `maturity`

每个 interface 至少包含：

- `id`
- `status`
- `provider`
- `consumer`
- `contract_objects`
- `maturity`

### 5.2 检查策略

建议新增一个 registry checker，作为实现前置门禁的一部分。Trial C 只做决策，不实现脚本。

检查输入：

- JSON registry。
- 被检查的合同文档。
- 可选的 owned file 列表。

必须检查：

- 文档中反引号包裹的 registry-like id 是否在 JSON allowlist 中。
- 文档是否引用 deprecated id。
- 文档是否使用 `proposed_*` 但又把它当成 registered dependency。
- 模块声明的 maturity 是否超过 registry 允许上限。
- `phase5_gate_readout`、`phase5_cycle_ledger`、`phase5_recovery_ticket` 是否引用对应 schema。
- 子进程是否只修改 assigned owned file。

建议命令形态：

```bash
python -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial \
  --fail-on-unregistered \
  --fail-on-deprecated \
  --fail-on-maturity-overreach
```

### 5.3 Markdown Appendix 保留策略

Markdown appendix 保留，但规则调整为：

- 允许人工阅读和评审使用。
- 允许作为历史 Trial 文档证据保留。
- 不允许作为实现阶段唯一 allowlist。
- 新增或修改 id 时，必须先改 JSON registry，再同步 Markdown 摘要。
- 如果 JSON registry 与 Markdown appendix 冲突，JSON registry 胜出，Markdown 触发修复任务。

## 6. Claim Ceiling Gate 输入输出

### 6.1 输入

Claim Ceiling Gate 输入必须是结构化对象，不允许直接读取页面文案或 LLM 自由文本。

最小输入：

| 输入 | 来源 | 要求 |
| --- | --- | --- |
| `target_domain` | 调用方 | 枚举：Phase 5、recommendation、Short Pick Lab、frontend projection。 |
| `source_artifact_refs` | `phase5.artifact.produced.v1` 或相关 artifact family | 必须是 registered artifact family。 |
| `validation_status` | `validation_metrics` 或 replay / backtest artifact | 缺失时不能输出强结论。 |
| `simulation_boundary` | 调用方和 registry | Phase 5 / Short Pick Lab 默认 simulation-only。 |
| `staleness_status` | `frontend_projection_manifest` | stale 或 missing 时降级。 |
| `manual_llm_layer` | manual review projection | 只能作为 disagreement / explanation，不能提升 ceiling。 |
| `publish_verification` | `runtime.publish.verified.v1` 或缺失状态 | 用户可见 live-facing 结论需要发布验收事实。 |
| `blocking_reasons` | 调用方 | 外部数据失败、schema 漂移、SQLite 写锁、样本不足等。 |

### 6.2 输出

Gate 输出必须能落到 `phase5_gate_readout`，并可产生 `phase5.gate.evaluated.v1`。

最小输出：

| 字段 | 含义 |
| --- | --- |
| `gate_id` | 本次 gate 判断 id。 |
| `cycle_id` | 所属 `Phase5Cycle`，无 cycle 时使用明确的 standalone evaluation id。 |
| `gate_status` | `passed`、`degraded`、`blocked`、`insufficient_evidence`。 |
| `claim_ceiling` | 用户可见表达强度上限。 |
| `allowed_claims` | 允许输出的结论类型。 |
| `forbidden_claims` | 禁止输出的结论类型。 |
| `failing_gate_ids` | 未通过的 gate。 |
| `incomplete_gate_ids` | 缺输入的 gate。 |
| `next_action` | `continue_tracking`、`redesign`、`non_promotion`、`retry`、`block`。 |
| `source_refs` | 支撑本次判断的 artifact / projection / publish verification 引用。 |

### 6.3 Claim Ceiling Levels

建议第一阶段只保留四级：

| Level | 允许表达 | 禁止表达 |
| --- | --- | --- |
| `blocked` | 无法给出结论，只能显示缺失或阻塞原因。 | 任何策略有效、验证通过、可执行建议。 |
| `research_observation` | 观察性研究、样本不足、待继续跟踪。 | 稳定策略、生产证明、自动晋级。 |
| `paper_tracking_candidate` | 纸面跟踪候选、simulation-only、需要继续验证。 | 实盘建议、真实交易、生产级胜率承诺。 |
| `validated_readout` | 有 artifact-backed validation 的有限结论。 | 超出 artifact 覆盖范围的泛化结论或投资承诺。 |

Phase 5 和 Short Pick Lab 默认最高不超过 `paper_tracking_candidate`，除非后续 registry 显式提升 maturity 并具备 production 级验收。Trial C 不做该提升。

## 7. Claim Ceiling Gate 调用点

| 调用点 | 触发时机 | 输入 | 输出使用方 |
| --- | --- | --- | --- |
| Phase 5 gate evaluator | artifact 产出后、projection 刷新前 | `validation_metrics`、`phase5_holding_policy_study`、`portfolio_backtest`、`replay_alignment` | scheduler、projection builder、operations workbench |
| recommendation projection builder | recommendation 投影前 | validation artifact、core quant evidence、manual LLM disagreement | frontend projection、manual review packet |
| Short Pick Lab feedback projection | official / diagnostic 聚合前 | Short Pick Lab validation artifact、tradeability status、source packet status；如后续需要正式注册，可使用 `proposed_artifact_family.shortpick_validation_snapshot` | Short Pick Lab 页面投影 |
| runtime publish closeout | live-facing 发布验收后 | `runtime.publish.verified.v1` 或缺失状态 | cycle ledger、project closeout、用户可见完成状态 |
| autonomous reviewer | 子进程输出评审时 | registry check 结果、artifact refs、maturity | Trial report、rerun trigger |

调用规则：

- projection builder 必须消费 gate 输出，不能自己提升文案强度。
- recovery runner 可以降低或阻塞 claim ceiling，不能提升 claim ceiling。
- manual LLM review 不能直接写 gate 输出，只能提供解释、风险和 disagreement。
- runtime publish 未验证时，live-facing 相关结论不能标记为 completed。

## 8. 迁移步骤

### 8.1 Step 1：冻结 Trial C 设计决策

- 主进程评审本文和其他 Trial C 文档。
- 将被接受的方案固化到正式 `DECISIONS.md` 或后续 architecture doc。
- 不在子进程阶段提交或发布。

### 8.2 Step 2：建立 JSON Registry

- 从 Trial B appendix 迁移 registered events、artifact families 和 interfaces。
- 加入 `runtime.publish.verified.v1`、`frontend.projection.updated.v1` 等 Trial C context pack 已允许 id。
- 记录 deprecated Trial A event replacements。
- 为 `phase5_cycle_ledger`、`phase5_gate_readout`、`phase5_recovery_ticket` 补最小 schema。

### 8.3 Step 3：建立 Registry Checker

- 先检查 Trial C 文档和后续 Context Pack。
- 再接入 pre-implementation gate。
- 失败时触发重跑，不进入代码实现。

### 8.4 Step 4：实现 Claim Ceiling Gate 最小库

- 实现确定性纯函数。
- 用 fixture 覆盖 blocked、research_observation、paper_tracking_candidate、validated_readout。
- 禁止 gate 函数读取 DB、网络、当前时间、环境变量或 LLM。

### 8.5 Step 5：接入 Projection / Scheduler

- Phase 5 projection 前必须有 gate readout。
- recommendation 和 Short Pick Lab 投影必须消费公共 gate 输出。
- 页面只读 projection，不能在请求路径补跑 gate 输入。

### 8.6 Step 6：无人流程验收

- 主进程用 registry checker 生成 Context Pack。
- 子进程只读 Context Pack 和 owned file。
- 主进程自动评估未注册引用、deprecated id、maturity overreach 和 gate 缺失。
- 失败进入下一轮重跑，而不是要求人工口头判断。

## 9. 风险

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| JSON registry 与 Markdown appendix 漂移 | 子进程引用旧 id，评审口径不一致。 | JSON 胜出；检查脚本发现漂移后阻断实现。 |
| Schema 一次性铺太大 | Trial C 变成 production 级 schema 工程。 | 第一阶段只覆盖 registry 自身和三类 Phase 5 core artifact。 |
| Claim gate 被调用方绕过 | 页面或投影出现强结论漂移。 | projection builder 和 reviewer 都检查 `phase5_gate_readout` 引用。 |
| Claim gate 过早做成 HTTP 服务 | 增加部署、健康检查、发布验收和故障面。 | 先做纯函数库 / CLI，后续有跨进程强需求再服务化。 |
| Manual LLM 输出影响 ceiling | LLM 间接进入核心评分。 | manual LLM 只能降低、补充风险或展示 disagreement，不能提升 ceiling。 |
| Runtime publish 事实未进入 gate | 用户可见完成状态和实际 served 验证不一致。 | live-facing closeout 必须输入 `runtime.publish.verified.v1` 或明确缺失状态。 |
| Registry checker 误扫普通代码片段 | 误判文档中的示例字符串。 | 初期只扫描指定章节和反引号 id，后续再引入 AST / Markdown parser。 |

## 10. 验收标准

本文满足以下条件才可被主进程接受：

- 明确推荐 JSON allowlist + JSON Schema 作为 registry 机器真值源。
- 明确 Markdown appendix 保留，但不能作为实现阶段唯一真值源。
- 明确暂不采用 DB registry，暂不做独立 HTTP claim gate 服务。
- 明确 claim ceiling 抽成公共 gate，并以确定性纯函数库 / CLI / 内部模块作为第一阶段形态。
- 给出 registry 文件布局和检查策略。
- 给出 claim ceiling gate 的输入、输出、调用点和降级规则。
- 迁移步骤能让后续无人流程从 Trial C 进入代码实现。
- 未引入 Trial C Context Pack allowlist 之外的 registered event、artifact family 或 interface 依赖。
- 未要求子进程修改代码、启动服务、发布 runtime、提交 git 或更新状态类文档。

## 11. 开放问题分类

### 11.1 `architecture_decision`

| 问题 | 建议处理 |
| --- | --- |
| JSON registry 是否成为正式合同源。 | 本文推荐是，主进程评审后固化到正式 architecture decision。 |
| Claim Ceiling Gate 是否作为公共 gate。 | 本文推荐是，但第一阶段不做独立 HTTP 服务。 |
| `runtime.publish.verified.v1` 是否进入 `phase5_cycle_ledger`。 | 建议进入 cycle closeout readout，但具体 ledger 持久化位置由 C1 或主进程统一收敛。 |
| Registry checker 是否进入 pre-push。 | 当前建议先进入 pre-implementation gate；是否放入 pre-push 取决于误报率和耗时。 |

### 11.2 `implementation_choice`

| 问题 | 建议处理 |
| --- | --- |
| Registry checker 用 Markdown parser 还是正则扫描。 | 第一阶段扫描 JSON registry 和合同文档反引号 id；误报高再升级 Markdown parser。 |
| JSON Schema 校验用哪个库。 | 选择项目已有 Python 工具链中维护成本最低的 schema validator。 |
| Claim gate 代码放在现有 evidence / policy 模块还是新模块。 | 以最少依赖为准，必须保持纯函数和无副作用。 |
| Context Pack 如何生成。 | 从 JSON registry 生成 allowlist 片段，主进程再追加 owned file 和任务目标。 |

### 11.3 `research_unknown`

| 问题 | 所需证据 |
| --- | --- |
| 四级 claim ceiling 是否足够表达用户理解。 | PC / 手机 served 页面可用性验证和文案走查。 |
| `paper_tracking_candidate` 是否会被误读成投资建议。 | 前端文案测试、人工审阅和真实页面上下文验证。 |
| Short Pick Lab official / diagnostic 是否需要不同 ceiling。 | 多轮 Short Pick Lab validation artifact 和用户可见投影反馈；如需跨模块复用，先注册 `proposed_artifact_family.shortpick_validation_snapshot` 的正式替代。 |

## 12. 子进程自评

改动文件：

- `docs/contracts/autonomous-flow-trial/TRIAL_C_REGISTRY_AND_CLAIM_GATE_DECISION_CN.md`

自评风险：

- 本文仍是架构决策草案，没有实现 JSON registry、schema 或 checker。
- 文件路径和 CLI 形态是推荐设计，主进程需要与其他 Trial C 决策文档统一后再固化。
- Claim Ceiling Gate 的四级 ceiling 需要后续前端文案验证，避免用户误读。

未做事项：

- 未改代码。
- 未启动服务。
- 未发布 runtime。
- 未提交 git。
- 未更新 `PROJECT_STATUS.json`、`PROCESS.md`、`DECISIONS.md`。
