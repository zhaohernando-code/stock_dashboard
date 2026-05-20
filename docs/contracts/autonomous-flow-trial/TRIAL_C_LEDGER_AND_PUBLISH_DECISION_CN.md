# Trial C Ledger 与发布验收架构决策

状态：Trial C draft  
所属流程：`AUTONOMOUS_DEVELOPMENT_FLOW_CN.md`  
上游输入：`TRIAL_C_CONTEXT_PACK_CN.md`  
上游协议：`TRIAL_B_GLOBAL_PROTOCOL_CN.md`、`TRIAL_B_PHASE5_VERTICAL_SLICE_DESIGN_CN.md`  
适用范围：`stock_dashboard` Phase 5 自运行周期、恢复记录、gate readout 与 runtime publish verified 事实的实现前置决策  
成熟度：`partial -> usable`，不声明 production SLA

## 1. 目标

本文件回答 Trial C 的 C1 决策问题：

- `phase5_cycle_ledger`、`phase5_recovery_ticket`、`phase5_gate_readout` 的正式持久化位置。
- `runtime.publish.verified.v1` 是否纳入 `phase5_cycle_ledger`。
- `runtime.publish.verified.v1` 如何与 release manifest 对齐，且不重复保存发布事实。
- 给后续实现任务提供最小 schema、事件归属、迁移步骤、风险、验收标准和开放问题分类。

## 2. 非目标

- 不修改业务代码、数据库迁移、发布脚本或前端页面。
- 不启动服务、不发布 runtime、不产生真实 `runtime.publish.verified.v1`。
- 不更新 `PROJECT_STATUS.json`、`PROCESS.md`、`DECISIONS.md`。
- 不把 Phase 5、Short Pick Lab、claim ceiling 或 autonomous flow 声明为 production。
- 不新增 Trial C Context Pack allowlist 之外的 event、artifact family 或 interface id。

## 3. 推荐方案

推荐采用 **artifact source of truth + lightweight query index/projection** 的分层方案。

| 对象 | 权威持久化位置 | 查询 / 展示位置 | 说明 |
| --- | --- | --- | --- |
| `phase5_cycle_ledger` | runtime artifact store 下的 append-only cycle artifact family。建议相对位置为 `data/artifacts/autonomous_flow/phase5_cycle_ledger/<cycle_id>.json`。 | 后续可投影到只读 SQLite index 或 operations projection。 | 每个 `cycle_id` 一个 ledger 文件，保存周期状态、输入合同版本、artifact refs、gate refs、recovery refs、publish verification ref 和 next action。 |
| `phase5_recovery_ticket` | runtime artifact store 下的 ticket artifact family。建议相对位置为 `data/artifacts/autonomous_flow/phase5_recovery_ticket/<cycle_id>/<ticket_id>.json`。 | cycle ledger 只保存 ticket refs 和 final rollup。 | ticket 是失败恢复事实源，不能只存在日志或会话上下文。 |
| `phase5_gate_readout` | runtime artifact store 下的 gate readout artifact family。建议相对位置为 `data/artifacts/autonomous_flow/phase5_gate_readout/<cycle_id>/<gate_id>.json`。 | projection builder 可读取最新 readout 生成 `frontend_projection_manifest`。 | readout 是 claim ceiling 的直接依据，必须可追溯。 |
| `runtime.publish.verified.v1` | release manifest 仍是发布明细权威源。 | `phase5_cycle_ledger` 保存该事件的 event envelope 摘要和 `release_manifest_ref`。 | 纳入 cycle ledger，但只作为发布验收事实的索引，不复制 release manifest 明细。 |

结论：

- **把 `runtime.publish.verified.v1` 纳入 `phase5_cycle_ledger`**，前提是该发布验收属于同一 `cycle_id` 的 live-facing 输出。
- ledger 中只保存 publish event envelope、状态摘要、manifest 指针和 digest，不保存 localhost/canonical 的完整检查明细。
- release manifest 继续作为发布过程、runtime path、commit、localhost result、canonical result 和 browser evidence 的权威明细。
- repo 本地 checkout 只允许保留测试 fixture 或历史审计副本；live-facing 自运行周期的权威事实应落在 runtime artifact store 或其同步后的 artifact 根。

## 4. 备选方案

| 方案 | 描述 | 优点 | 缺点 | 结论 |
| --- | --- | --- | --- | --- |
| A. 只写 Markdown / PROCESS 记录 | 把 cycle、ticket、readout、publish 结果写入文档。 | 实现成本最低。 | 不能机器恢复、不能稳定查询、容易和状态文档混杂。 | 放弃。 |
| B. 只写 SQLite 表 | 为 cycle、ticket、readout、publish 建正式表。 | 查询方便，适合 UI。 | 迁移成本高，写锁风险更高，早期 schema 变更成本大。 | 不作为第一落点，可作为后续 index。 |
| C. 只写 release manifest | 把 cycle 信息塞进发布 manifest。 | 不新增存储族。 | release manifest 只覆盖发布，不覆盖研究、gate、恢复和下一轮调度。 | 放弃。 |
| D. artifact source of truth + lightweight index | artifact 保存权威事实，SQLite/projection 只做查询加速。 | 可审计、可迁移、与现有 artifact-backed validation 一致，减少写锁压力。 | 需要后续补 schema 校验和索引生成器。 | 推荐。 |

## 5. 取舍依据

- 项目规则已经要求用户可见强结论必须 artifact-backed，Phase 5 自运行事实也应进入 artifact family，而不是只写运行日志。
- SQLite 写锁是已知风险。将权威事实先落 artifact，后续异步投影到小 index，比所有步骤同步写 DB 更稳。
- `runtime.publish.verified.v1` 是 usable 级事件，但发布明细已经由 release manifest 承担；ledger 应引用它，而不是成为第二份 release manifest。
- 自运行流程需要无人介入恢复。cycle ledger 必须能回答“上一轮卡在哪里、已自动尝试什么、下一步做什么”，这不是 release manifest 的职责。
- 当前成熟度是 `partial -> usable`，不适合直接设计分布式任务平台、复杂事件总线或 production SLA。

## 6. 最小 Schema

### 6.1 `phase5_cycle_ledger`

```json
{
  "artifact_family": "phase5_cycle_ledger",
  "schema_version": "v1",
  "cycle_id": "phase5-YYYYMMDD-slot",
  "trigger": "scheduled | manual | retry | recovery_followup",
  "scope": {
    "phase": "phase5",
    "modules": ["validation", "gate", "projection", "publish_verification"]
  },
  "status": "planned | running | degraded | blocked | completed",
  "started_at": "ISO-8601",
  "finished_at": "ISO-8601 | null",
  "input_contract_versions": {
    "global_protocol": "TRIAL_B_GLOBAL_PROTOCOL_CN.md",
    "context_pack": "TRIAL_C_CONTEXT_PACK_CN.md"
  },
  "event_refs": [
    {
      "event_id": "phase5.cycle.started.v1",
      "event_time": "ISO-8601",
      "event_digest": "sha256"
    }
  ],
  "artifact_refs": [
    {
      "artifact_family": "validation_metrics",
      "artifact_id": "string",
      "schema_version": "string",
      "lineage_ref": "string"
    }
  ],
  "gate_readout_refs": [
    {
      "artifact_family": "phase5_gate_readout",
      "gate_id": "string",
      "artifact_ref": "string"
    }
  ],
  "recovery_ticket_refs": [
    {
      "artifact_family": "phase5_recovery_ticket",
      "ticket_id": "string",
      "artifact_ref": "string",
      "final_status": "resolved | degraded | blocked"
    }
  ],
  "publish_verification_ref": {
    "event_id": "runtime.publish.verified.v1",
    "event_time": "ISO-8601",
    "commit_id": "git sha",
    "release_manifest_ref": "path or artifact id",
    "release_manifest_digest": "sha256",
    "localhost_status": "passed | failed | skipped",
    "canonical_status": "passed | failed | blocked",
    "summary_status": "verified | blocked | not_applicable"
  },
  "next_action": "continue_tracking | rebuild_projection | retry_failed_step | redesign | blocked | none"
}
```

约束：

- `publish_verification_ref` 可以为 `null`，例如纯文档试验或未触发 live-facing 发布的 cycle。
- 如果 `publish_verification_ref.summary_status != verified`，cycle 不能标记为 live-facing `completed`。
- `release_manifest_ref` 和 `release_manifest_digest` 是去重边界：ledger 不复制 release manifest 明细。

### 6.2 `phase5_recovery_ticket`

```json
{
  "artifact_family": "phase5_recovery_ticket",
  "schema_version": "v1",
  "ticket_id": "recovery-YYYYMMDD-N",
  "cycle_id": "phase5-YYYYMMDD-slot",
  "failed_step": "artifact_build | gate_eval | projection_refresh | publish_verify | replay_schedule",
  "failure_class": "external_data_timeout | sqlite_write_lock | artifact_schema_unknown | stale_projection | publish_blocked | test_failed | contract_violation",
  "failure_observed_at": "ISO-8601",
  "evidence_refs": ["path or artifact id"],
  "recovery_action": "reuse_last_valid_artifact | retry_with_backoff | rebuild_projection | mark_degraded | open_followup_cycle | block_cycle",
  "retry_count": 0,
  "final_status": "resolved | degraded | blocked",
  "claim_ceiling_effect": "unchanged | lowered",
  "notes": "short machine-readable summary"
}
```

约束：

- recovery ticket 不允许提升 `claim_ceiling`。
- 连续恢复失败必须变成 `blocked` 或 `open_followup_cycle`，不能等待人工口头介入。

### 6.3 `phase5_gate_readout`

```json
{
  "artifact_family": "phase5_gate_readout",
  "schema_version": "v1",
  "gate_id": "phase5-gate-YYYYMMDD",
  "cycle_id": "phase5-YYYYMMDD-slot",
  "gate_status": "passed | insufficient_evidence | blocked | degraded",
  "failing_gate_ids": ["string"],
  "incomplete_gate_ids": ["string"],
  "claim_ceiling": "research_observation | paper_tracking | simulation_candidate | insufficient_evidence | non_promotion",
  "source_artifact_ids": ["artifact id"],
  "blocking_reasons": ["string"],
  "next_action": "continue_tracking | rebuild_projection | redesign | retry_failed_step | blocked",
  "evaluated_at": "ISO-8601"
}
```

约束：

- `claim_ceiling` 是用户可见表达强度的上限，不允许前端文案绕过。
- manual LLM review 只能作为人工研究层，不参与本 readout 的 core gate。

### 6.4 `runtime.publish.verified.v1` Event Envelope

```json
{
  "event_id": "runtime.publish.verified.v1",
  "schema_version": "v1",
  "cycle_id": "phase5-YYYYMMDD-slot | null",
  "commit_id": "git sha",
  "release_manifest": "path or artifact id",
  "release_manifest_digest": "sha256",
  "localhost_result": "passed | failed | skipped",
  "canonical_result": "passed | failed | blocked",
  "verified_at": "ISO-8601",
  "verified_by": "main_process"
}
```

约束：

- `verified_by` 只能是主进程或发布验收器；子进程不得产生该事件。
- 若 `cycle_id` 为空，该事件只进入项目发布日志，不进入某个 Phase 5 cycle 的闭环评价。

## 7. 事件归属

| Event ID | Provider | Ledger 处理 | 说明 |
| --- | --- | --- | --- |
| `phase5.cycle.started.v1` | scheduler / main autonomous process | 必须写入 `phase5_cycle_ledger.event_refs`。 | cycle 创建失败时不得启动研究链路。 |
| `phase5.artifact.produced.v1` | Phase 5 runners | 写入 `phase5_cycle_ledger.artifact_refs` 的可追溯摘要。 | artifact 本体仍在各自 artifact family。 |
| `phase5.gate.evaluated.v1` | gate evaluator | 写入 `phase5_cycle_ledger.gate_readout_refs`，并指向 `phase5_gate_readout`。 | ledger 不复制 readout 全量。 |
| `phase5.projection.refreshed.v1` | projection builder | 写入 `phase5_cycle_ledger.artifact_refs`，指向 `frontend_projection_manifest`。 | 页面 API 只读 projection。 |
| `phase5.recovery.recorded.v1` | recovery runner / main autonomous process | 写入 `phase5_cycle_ledger.recovery_ticket_refs`。 | ticket 本体独立持久化。 |
| `runtime.publish.verified.v1` | main process closeout / publish verifier | 条件性写入 `phase5_cycle_ledger.publish_verification_ref`。 | 只有与本 cycle 的 live-facing 输出直接相关时纳入。 |

## 8. 迁移步骤

1. 保留 Trial B Markdown registry 作为当前 allowlist，后续实现前先生成轻量机器检查脚本，检查本文引用的 event、artifact family 和 interface 均已注册。
2. 在 runtime artifact root 下建立三个 artifact family 的目录约定：`phase5_cycle_ledger`、`phase5_recovery_ticket`、`phase5_gate_readout`。
3. 为三类 artifact 增加最小 JSON schema 校验，先覆盖 required fields、registered id、状态枚举和 digest 字段。
4. 调度器先写 `phase5_cycle_ledger`，再启动 Phase 5 runners；如果 ledger 无法写入，本轮停止。
5. runners 继续写各自研究 artifact，同时向 cycle ledger 追加 artifact refs；追加失败时记录 `phase5_recovery_ticket`。
6. gate evaluator 写 `phase5_gate_readout`，再把 readout ref 追加到 cycle ledger。
7. projection builder 生成 `frontend_projection_manifest`，cycle ledger 只引用 projection manifest id。
8. 主进程完成 live-facing 发布验收后，生成 `runtime.publish.verified.v1` event envelope；若该发布属于本 cycle，将 event 摘要和 release manifest ref 追加到 cycle ledger。
9. 后续需要 UI 查询时，再从 artifact source of truth 生成只读 SQLite index 或 frontend projection，不把 DB 表作为第一权威源。

## 9. 风险

| 风险 | 影响 | 缓解 |
| --- | --- | --- |
| artifact JSON schema 漂移 | 下一轮 cycle 无法可靠恢复。 | 最小 schema 校验先行，未知字段允许保留，required 字段 fail closed。 |
| ledger 与 release manifest 不一致 | 发布验收事实出现双源冲突。 | ledger 只保存 `release_manifest_ref` 和 digest；发布明细以 release manifest 为准。 |
| runtime artifact store 路径与 repo fixture 混淆 | 可能误把 repo 输出当 live 真值。 | 文档和实现必须区分 runtime artifact root 与 repo fixture；live-facing 判断以 runtime 为准。 |
| SQLite index 后续变成事实源 | 可能引入写锁和回放分歧。 | DB/projection 只读再生，source-of-truth 字段必须能从 artifact 重建。 |
| publish verification 与非 live cycle 绑定错误 | 文档或研究 cycle 被误标为 live completed。 | `cycle_id` 可为空；只有 live-facing 输出直接来自该 cycle 时才能写入 ledger。 |
| recovery 自动推进过度 | 可能掩盖真实 gate blocked。 | recovery 只能降低或保持 claim ceiling，不能把 blocked 改成 passed。 |

## 10. 验收标准

- 本文明确推荐 `artifact source of truth + lightweight query index/projection`。
- 本文明确 `phase5_cycle_ledger`、`phase5_recovery_ticket`、`phase5_gate_readout` 的权威持久化位置和后续查询位置。
- 本文明确 `runtime.publish.verified.v1` 纳入 `phase5_cycle_ledger`，但只保存 event envelope 摘要、manifest ref 和 digest，不复制 release manifest 明细。
- 本文只引用 Trial C Context Pack allowlist 中已注册的 event、artifact family 和 interface id。
- 本文包含推荐方案、备选方案、取舍依据、最小 schema、事件归属、迁移步骤、风险、验收标准、开放问题分类。
- 本文不要求子进程改代码、启动服务、发布 runtime、提交 git 或更新状态文档。

## 11. 开放问题分类

### 11.1 `architecture_decision`

| 问题 | 推荐处理 |
| --- | --- |
| runtime artifact root 的正式路径是否复用现有 `data/artifacts` 约定，还是建立 `autonomous_flow` 子根。 | 推荐建立 `data/artifacts/autonomous_flow/` 子根，避免与已有研究 artifact 混排。 |
| SQLite index 是否需要进入第一期实现。 | 推荐第一期不建正式业务表，只做可重建的轻量 index 或脚本查询；如果 operations UI 需要再补。 |
| `cycle_id` 是否必须绑定交易日 slot。 | 推荐采用 `phase5-YYYYMMDD-<slot>`，必要时附加 input digest 防冲突。 |

### 11.2 `implementation_choice`

| 问题 | 推荐处理 |
| --- | --- |
| JSON schema 用手写 schema 还是从 Markdown registry 生成。 | 第一版手写最小 schema，后续把 registry 升级为机器源。 |
| ledger 追加是重写 JSON 文件还是 JSONL events。 | 第一版每个 cycle 一个 compact JSON 文件，内部 refs append 后原子替换；事件量上来后再拆 JSONL。 |
| release manifest digest 如何计算。 | 使用发布 manifest 文件内容 hash；ledger 保存 digest 但不解释明细。 |
| projection freshness 阈值放在哪里。 | 放在 projection builder 配置或 policy config，不写死在 ledger schema。 |

### 11.3 `research_unknown`

| 问题 | 所需证据 |
| --- | --- |
| recovery 自动降级是否会让用户误解策略状态。 | PC 和手机 served 页面上的状态文案验证。 |
| Phase 5 周期粒度是否足以覆盖 Short Pick Lab 联动。 | 多轮 cycle 后检查 recovery ticket、gate readout 与 shortpick projection 的关联需求。 |
| artifact-first 是否会给日刷增加明显耗时。 | 后续实现阶段记录 artifact write、schema check、projection rebuild 的耗时。 |

## 12. 子进程自评

改动文件：

- `docs/contracts/autonomous-flow-trial/TRIAL_C_LEDGER_AND_PUBLISH_DECISION_CN.md`

自评风险：

- 本文件仍是 Trial C 架构决策，不是已实现 schema 系统。
- runtime artifact root 的绝对路径需要主进程结合现有发布脚本和 runtime 目录再最终落定。
- SQLite index/projection 只定义为后续可选层，若 operations UI 第一阶段必须高频查询，可能需要提前补索引设计。
- `runtime.publish.verified.v1` 的 event envelope 需要发布验收器实现时确保与 release manifest hash 一致。

未做事项：

- 未改代码。
- 未启动服务。
- 未发布 runtime。
- 未提交 git。
- 未更新 `PROJECT_STATUS.json`、`PROCESS.md`、`DECISIONS.md`。
