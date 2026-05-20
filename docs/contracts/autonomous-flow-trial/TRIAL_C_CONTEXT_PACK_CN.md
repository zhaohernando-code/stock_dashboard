# Trial C Context Pack：实现前置架构决策

状态：active input  
上游流程：`AUTONOMOUS_DEVELOPMENT_FLOW_CN.md`  
上游试验：`AUTONOMOUS_FLOW_TRIAL_2026-05-20_CN.md`  
目标：在进入代码实现前，收敛 Trial B 留下的关键 architecture decisions。

## 1. 本轮目标

Trial C 不直接实现业务功能，只收敛实现前置架构决策，避免后续代码阶段把 ledger、registry、claim ceiling、publish verification 分散实现。

必须回答：

1. `phase5_cycle_ledger`、`phase5_recovery_ticket`、`phase5_gate_readout` 的正式持久化位置。
2. Registry 的正式形态：Markdown appendix、JSON Schema、DB registry 或代码生成 allowlist。
3. `claim_ceiling` 是否抽成跨 Phase 5、recommendation、Short Pick Lab 的公共 gate 服务。
4. `runtime.publish.verified.v1` 是否纳入 cycle ledger。

## 2. 非目标

- 不修改业务代码。
- 不启动服务。
- 不发布 runtime。
- 不改变真实策略、推荐结果、模拟盘或短投试验田结果。
- 不更新 `PROJECT_STATUS.json`。
- 不宣称 production SLA。

## 3. 当前成熟度

| 能力 | 当前成熟度 | Trial C 允许深度 |
| --- | --- | --- |
| autonomous flow orchestration | scaffold | 架构决策、轻量检查规则、实现拆解 |
| phase5 cycle ledger | partial | 持久化位置、schema 边界、迁移路径 |
| registry / interface allowlist | partial | 文件格式、检查策略、后续升级路径 |
| claim ceiling gate | partial | 公共服务边界、调用点、降级语义 |
| runtime publish event | usable | 是否进入 cycle ledger，如何与 release manifest 对齐 |

## 4. Registry Allowlist

Trial C 文档只能引用以下已注册 id；如需新增，必须标记为 `proposed_*`。

### Events

- `phase5.cycle.started.v1`
- `phase5.artifact.produced.v1`
- `phase5.gate.evaluated.v1`
- `phase5.projection.refreshed.v1`
- `phase5.recovery.recorded.v1`
- `runtime.publish.verified.v1`
- `frontend.projection.updated.v1`

### Artifact Families

- `phase5_cycle_ledger`
- `phase5_recovery_ticket`
- `phase5_gate_readout`
- `frontend_projection_manifest`
- `autonomous_flow_trial_report`
- `rolling_validation_manifest`
- `validation_metrics`
- `phase5_holding_policy_study`
- `portfolio_backtest`
- `replay_alignment`

### Interfaces

- `iface.scheduler.phase5-cycle-ledger.v1`
- `iface.runner.phase5-artifact-ledger.v1`
- `iface.gate.phase5-scheduler.v1`
- `iface.projection.publish-verifier.v1`
- `iface.recovery.scheduler-reviewer.v1`
- `iface.projection.api-spa.v1`
- `iface.main.subagent-contract.v1`

## 5. 项目硬约束

- live-facing 代码完成必须发布到 `~/codex/runtime/projects/ashare-dashboard` 并完成 served 验证。
- 本轮是文档架构决策，不触发 runtime publish。
- 页面 API 不能在请求路径跑研究、行情同步、LLM 或 DB 写入。
- SQLite 写锁、短投验证、历史回放和 projection rebuild 不可无脑并发。
- LLM 不进入核心评分、validation gate 或自动调仓。
- Phase 5 和 Short Pick Lab 仍是 simulation-only / research / paper tracking 边界，不进入真实交易。

## 6. 子进程规则

- 只改 assigned owned file。
- 不提交 git。
- 不启动服务。
- 不发布 runtime。
- 不更新 `PROJECT_STATUS.json`、`PROCESS.md`、`DECISIONS.md`。
- 不覆盖其他子进程文件。
- 输出必须包含：推荐方案、备选方案、取舍依据、迁移步骤、风险、验收标准、开放问题分类。

## 7. Trial C 评分

总分 100：

| 维度 | 权重 |
| --- | ---: |
| 决策明确性 | 25 |
| 与现有项目约束一致性 | 25 |
| 可实现性与迁移成本 | 20 |
| 无人介入能力提升 | 20 |
| 子进程边界遵守 | 10 |

重跑触发：

- 推荐方案仍需要人工口头判断才能继续。
- 方案要求 live-facing 代码但没有发布验收路径。
- 方案引入未注册事件、artifact 或 interface。
- 子进程越权文件。
- 总分低于 80。
