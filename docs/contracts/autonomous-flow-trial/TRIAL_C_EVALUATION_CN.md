# Trial C 评估记录：实现前置架构决策

状态：进行中  
输入：`TRIAL_C_CONTEXT_PACK_CN.md`  
目标：评估子进程产出的架构决策方案，必要时重跑，最终固化可进入实现的架构选择。

## 1. 子任务拆解

| 子进程 | owned file | 目标 |
| --- | --- | --- |
| C1 | `TRIAL_C_LEDGER_AND_PUBLISH_DECISION_CN.md` | 收敛 cycle ledger / recovery ticket / gate readout / publish event 的持久化与事件归属 |
| C2 | `TRIAL_C_REGISTRY_AND_CLAIM_GATE_DECISION_CN.md` | 收敛 registry 形态与 claim ceiling 公共 gate 边界 |

## 2. 评分标准

| 维度 | 权重 | 判定 |
| --- | ---: | --- |
| 决策明确性 | 25 | 是否给出推荐方案，而不是只列选项 |
| 与现有项目约束一致性 | 25 | 是否遵守 runtime、projection、SQLite、simulation-only、LLM 边界 |
| 可实现性与迁移成本 | 20 | 是否能按小步落地，不破坏现有 Phase 5 |
| 无人介入能力提升 | 20 | 是否减少人工判断和会话上下文依赖 |
| 子进程边界遵守 | 10 | 是否只改 owned file |

自动重跑阈值：

- 总分低于 80。
- 任一关键维度低于 60%。
- 引用未注册 id。
- 开放问题未分类。
- 子进程越权文件。

## 3. Trial C 初轮结果

Trial C 初轮已完成两份子进程产物：

- `TRIAL_C_LEDGER_AND_PUBLISH_DECISION_CN.md`
- `TRIAL_C_REGISTRY_AND_CLAIM_GATE_DECISION_CN.md`

### 3.1 C1 评分：Ledger / Publish

| 维度 | 权重 | 得分 | 说明 |
| --- | ---: | ---: | --- |
| 决策明确性 | 25 | 24 | 明确推荐 `artifact source of truth + lightweight query index/projection`。 |
| 与现有项目约束一致性 | 25 | 24 | 避开 SQLite 写锁，把 release manifest 继续作为发布明细真值源。 |
| 可实现性与迁移成本 | 20 | 18 | 先用 artifact JSON，后续再建 index，迁移路径轻。 |
| 无人介入能力提升 | 20 | 19 | cycle、ticket、gate readout 都进入 durable artifact，可支撑恢复。 |
| 子进程边界遵守 | 10 | 10 | 只写 owned file，未提交、未发布、未改状态文档。 |
| **总分** | **100** | **95** | 接受。 |

接受的 C1 决策：

- `phase5_cycle_ledger`、`phase5_recovery_ticket`、`phase5_gate_readout` 的权威事实先落 runtime artifact store。
- SQLite / frontend projection 只做可重建查询层，不作为第一事实源。
- `runtime.publish.verified.v1` 纳入 `phase5_cycle_ledger`，但 ledger 只保存 event envelope、`release_manifest_ref` 和 digest。
- release manifest 继续作为发布验收明细的权威源。

### 3.2 C2 评分：Registry / Claim Gate

| 维度 | 权重 | 得分 | 说明 |
| --- | ---: | ---: | --- |
| 决策明确性 | 25 | 24 | 明确推荐 JSON allowlist + JSON Schema，claim gate 做纯函数库。 |
| 与现有项目约束一致性 | 25 | 24 | 不引入 DB registry 或 HTTP gate，符合写锁和发布复杂度约束。 |
| 可实现性与迁移成本 | 20 | 18 | 文件布局和 CLI 形态清晰，第一阶段 schema 范围克制。 |
| 无人介入能力提升 | 20 | 20 | registry checker 与公共 gate 都直接减少人工判断。 |
| 子进程边界遵守 | 10 | 10 | 只写 owned file，未提交、未发布、未改状态文档。 |
| **总分** | **100** | **96** | 接受。 |

接受的 C2 决策：

- JSON allowlist + JSON Schema 成为实现阶段机器真值源。
- Markdown appendix 保留为人工镜像，但不再作为唯一真值源。
- 暂不引入 DB registry。
- `claim_ceiling` 抽成公共 gate，但第一阶段做确定性纯函数库 / CLI / 内部模块，不做 HTTP 服务。
- Context Pack 后续应由 JSON registry 派生 allowlist。

## 4. 重跑记录

本轮不触发重跑。

原因：

- 两份子进程产物均给出明确推荐方案，不需要人工口头判断才能继续。
- 没有要求 live-facing 代码或 runtime publish。
- 没有发现 Trial A 无版本事件继续作为 registered dependency 使用。
- 开放问题均已分类。
- 子进程未越权文件。

## 5. 最终固化结论

Trial C 进入实现拆解前置完成，下一轮应按以下顺序推进：

1. 建立 `docs/contracts/registry/autonomous_flow_registry.v1.json` 与对应 JSON Schema。
2. 实现 registry checker，先检查合同文档和 Context Pack 中的 registered id、deprecated id、maturity overreach。
3. 实现 claim ceiling gate 的纯函数库与 fixture 测试。
4. 再实现 `phase5_cycle_ledger`、`phase5_recovery_ticket`、`phase5_gate_readout` 的 artifact schema 与写入路径。
5. 最后接入 scheduler / projection / publish verifier。

这个顺序的原因是：registry/checker 是后续所有子进程和实现任务的共同门禁，先做它可以让后续代码实现也被同一流程约束，而不是继续依赖主进程人工审阅。
