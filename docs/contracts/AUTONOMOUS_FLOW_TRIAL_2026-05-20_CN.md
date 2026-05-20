# 自运行流程试验记录 2026-05-20

状态：进行中  
关联流程：`docs/contracts/AUTONOMOUS_DEVELOPMENT_FLOW_CN.md`  
试验对象：`stock_dashboard` Phase 5 研究、投影、发布与回放链路的无人介入开发流程。

## 1. 试验目标

本轮不是直接实现业务功能，而是验证一个流程命题：

> AI 项目组能否在没有人工连续补充提示的情况下，先设计流程，再按流程生成设计产物，再自动评估质量，最后根据评估结果重跑并固化流程约束。

## 2. 上一轮暴露的问题

上一轮多 agent 模块设计试验的问题包括：

- 各模块产出速度快，但缺少统一术语、事件、artifact 与接口矩阵。
- 有些文档把 scaffold / partial 阶段写成 production 级复杂设计。
- 开放问题未区分架构决策、实现选择和研究未知。
- 子进程容易把全局决策、模块接口命名和最终质量判断混入自己的职责。
- 评估结论如果不转成硬约束，下一轮仍会重复同类问题。

## 3. 本轮流程改动

本轮先新增 `AUTONOMOUS_DEVELOPMENT_FLOW_CN.md`，引入以下硬约束：

- 并行模块设计前必须有全局协议基线。
- 每个模块必须声明成熟度，并按成熟度限制设计深度。
- 子进程只改 owned files，不提交、不发布、不更新项目状态。
- 评审分为结构、一致性、成熟度和工程四类。
- 不合格项必须触发重跑，而不是在最终汇总里口头说明。

## 4. Trial A 任务拆解

| 子进程 | owned file | 目标 |
| --- | --- | --- |
| A | `docs/contracts/autonomous-flow-trial/TRIAL_A_GLOBAL_PROTOCOL_CN.md` | 生成 stock_dashboard 项目级术语、事件、artifact、接口与成熟度基线 |
| B | `docs/contracts/autonomous-flow-trial/TRIAL_A_PHASE5_VERTICAL_SLICE_DESIGN_CN.md` | 生成 Phase 5 无人介入纵向切片设计 |

子进程共同约束：
- 读取 canonical docs 和流程合同。
- 只写 owned files。
- 不启动服务。
- 不发布 runtime。
- 不提交 git。
- 不改 `PROJECT_STATUS.json`、`PROCESS.md`、`DECISIONS.md`。

## 5. 评估量表

总分 100 分：

| 维度 | 权重 | 判定问题 |
| --- | ---: | --- |
| 结构完整性 | 20 | 是否覆盖流程合同要求的章节与开放问题分类 |
| 跨模块一致性 | 30 | 是否先注册术语、事件、artifact、接口，再在模块设计中引用 |
| 成熟度约束 | 20 | 是否避免把未成熟能力写成 production 承诺 |
| 工程可执行性 | 20 | 是否有明确验收、测试、失败恢复和无人推进路径 |
| 子进程边界 | 10 | 是否只改 owned files，是否避免提交、发布、状态更新 |

自动重跑阈值：
- 总分低于 75。
- 任一关键维度低于该维度 60%。
- 存在未分类开放问题。
- 存在未注册跨模块接口。
- 子进程越权改文件。

## 6. Trial A 结果

Trial A 已完成两份产物：

- `docs/contracts/autonomous-flow-trial/TRIAL_A_GLOBAL_PROTOCOL_CN.md`
- `docs/contracts/autonomous-flow-trial/TRIAL_A_PHASE5_VERTICAL_SLICE_DESIGN_CN.md`

### 6.1 评分

| 维度 | 权重 | 得分 | 说明 |
| --- | ---: | ---: | --- |
| 结构完整性 | 20 | 19 | 两份文档都覆盖了主要章节，开放问题也做了分类。 |
| 跨模块一致性 | 30 | 17 | 全局协议有事件和 artifact registry，但纵向切片在全局协议之外自行声明了 `phase5.*` 事件。 |
| 成熟度约束 | 20 | 18 | 明确控制在 `partial -> usable`，没有宣称 production。 |
| 工程可执行性 | 20 | 16 | 有失败恢复和门禁，但 registry 仍是 Markdown，缺少机器可校验清单。 |
| 子进程边界 | 10 | 10 | 子进程只写 owned files，未提交、未发布、未改状态文档。 |
| **总分** | **100** | **80** | 草案质量可用，但触发自动重跑条件。 |

### 6.2 自动重跑触发项

- 纵向切片存在未注册事件：`phase5.cycle.started`、`phase5.artifact.produced`、`phase5.gate.evaluated`、`phase5.projection.refreshed`、`phase5.recovery.recorded`。
- 全局协议缺少机器可校验的 registry appendix，后续无法用脚本稳定检查“未注册事件 / artifact / interface”。
- Trial A 证明“让两个子进程并行分别产出全局协议和依赖全局协议的模块设计”仍然存在时序问题：模块设计可能先于全局协议完成，导致引用漂移。

### 6.3 结论

Trial A 不是失败，但不能直接接受为最终输出。按 `AUTONOMOUS_DEVELOPMENT_FLOW_CN.md`，必须进入 Trial B。

## 7. Trial B 重跑输入

Trial B 只重跑受影响部分，不废弃 Trial A 的有效内容。

硬约束：

- 先生成 `TRIAL_B_GLOBAL_PROTOCOL_CN.md`，其中必须包含机器可校验 registry appendix。
- 如果 Phase 5 cycle 事件是合理事件，必须先在全局协议注册，再允许纵向切片引用。
- 再生成 `TRIAL_B_PHASE5_VERTICAL_SLICE_DESIGN_CN.md`，只能引用 Trial B 全局协议中已注册的事件、artifact 和接口。
- Trial B 产物必须保留 `partial -> usable` 成熟度上限，不写 production SLA。
- 子进程仍只改 owned files，不提交、不发布、不改状态文档。

## 8. 最终结论

Trial B 已完成两份产物：

- `docs/contracts/autonomous-flow-trial/TRIAL_B_GLOBAL_PROTOCOL_CN.md`
- `docs/contracts/autonomous-flow-trial/TRIAL_B_PHASE5_VERTICAL_SLICE_DESIGN_CN.md`

### 8.1 Trial B 评分

| 维度 | 权重 | 得分 | 说明 |
| --- | ---: | ---: | --- |
| 结构完整性 | 20 | 20 | 全局协议和纵向切片都覆盖必需章节，纵向切片新增“引用协议清单”。 |
| 跨模块一致性 | 30 | 27 | Phase 5 事件、artifact family 和 interface 先在全局协议注册，再由纵向切片引用。 |
| 成熟度约束 | 20 | 19 | 明确保持 `partial -> usable`，未写 production SLA 或实盘承诺。 |
| 工程可执行性 | 20 | 18 | 已有可脚本扫描的 Markdown appendix，但还不是正式 JSON Schema 或 DB registry。 |
| 子进程边界 | 10 | 10 | 子进程只写 owned files，未提交、未发布、未改状态文档。 |
| **总分** | **100** | **94** | 可作为下一步实现拆解的流程草案。 |

### 8.2 自动检查结果

- `git diff --check` 通过。
- Trial B 纵向切片中反引号引用的 event / artifact / interface id 均能在 Trial B 全局协议中找到。
- Trial B 纵向切片中未发现 Trial A 无版本事件引用：`phase5.cycle.started`、`phase5.artifact.produced`、`phase5.gate.evaluated`、`phase5.projection.refreshed`、`phase5.recovery.recorded`。
- 必需章节覆盖完整。

### 8.3 本轮学到的流程约束

- 全局协议和依赖它的模块设计不能同轮并行；必须先完成全局协议，再启动模块设计。
- 子进程输入不能无限读取长文档；主进程需要先生成短 `Context Pack`，只把必要事实、文件、owned scope、registry allowlist 和成熟度限制传给子进程。
- Markdown registry 可以作为早期轻量门禁，但进入实现前应升级为机器 schema 或至少有正式检查脚本。
- 重跑应只重跑失败面：Trial B 没有废弃 Trial A 的有效内容，只修复了 registry 与引用一致性。

### 8.4 下一步实现前置条件

进入代码实现前，必须先收敛以下 `architecture_decision`：

- `phase5_cycle_ledger`、`phase5_recovery_ticket`、`phase5_gate_readout` 的正式持久化位置。
- Registry 的正式形态：Markdown appendix、JSON Schema、DB registry 或代码生成 allowlist。
- `claim_ceiling` 是否抽成跨 Phase 5、recommendation、Short Pick Lab 的公共 gate 服务。
- `runtime.publish.verified.v1` 是否纳入 cycle ledger。

本轮完成了“流程设计 -> 试运行 -> 评估 -> 重跑 -> 固化”的最小闭环。它证明当前流程可以在没有用户继续干预的情况下发现 Trial A 的协议漂移，并通过 Trial B 自行收敛。
