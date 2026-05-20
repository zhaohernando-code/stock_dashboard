# Trial E Context Pack：Phase 5 自运行 Ledger Artifact 最小实现

状态：active input  
上游：Trial C / Trial D  
目标：实现 `phase5_cycle_ledger`、`phase5_recovery_ticket`、`phase5_gate_readout` 的最小 artifact 读写层，为后续 scheduler / projection / publish verifier 接入做准备。

## 1. 本轮目标

只实现 artifact store 能力：

- 新增 typed models 或 dataclasses，表达三类 artifact 的最小 schema。
- 在 `research_artifact_store.py` 中提供 read/write/read_if_exists 路径。
- artifact 路径必须落到 `autonomous_flow/phase5_cycle_ledger`、`autonomous_flow/phase5_recovery_ticket`、`autonomous_flow/phase5_gate_readout` 这类隔离目录。
- 复用现有 `_ensure_artifact_write_allowed`，禁止默认写入 repo 源码 artifact 目录。
- 增加 focused tests。

## 2. 非目标

- 不接 scheduler。
- 不接 projection builder。
- 不接 publish verifier。
- 不改 API / frontend。
- 不发布 runtime。
- 不改变任何当前 Phase 5 研究结果。
- 不新增数据库表。

## 3. Owned Files

建议子进程 owned files：

- `src/ashare_evidence/autonomous_flow_artifacts.py`
- `src/ashare_evidence/research_artifact_store.py`
- `tests/test_autonomous_flow_artifacts.py`

如确需修改其他文件，必须在最终报告中说明原因。

## 4. Registry IDs

只允许引用：

- `phase5_cycle_ledger`
- `phase5_recovery_ticket`
- `phase5_gate_readout`
- `runtime.publish.verified.v1`
- `phase5.cycle.started.v1`
- `phase5.artifact.produced.v1`
- `phase5.gate.evaluated.v1`
- `phase5.projection.refreshed.v1`
- `phase5.recovery.recorded.v1`

实现前后必须运行：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_E_CONTEXT_PACK_CN.md \
  --fail-on-unregistered \
  --fail-on-deprecated
```

## 5. Schema 要求

### `Phase5CycleLedgerArtifact`

必须包含：

- `artifact_family = "phase5_cycle_ledger"`
- `schema_version`
- `cycle_id`
- `trigger`
- `scope`
- `status`
- `started_at`
- `finished_at`
- `input_contract_versions`
- `event_refs`
- `artifact_refs`
- `gate_readout_refs`
- `recovery_ticket_refs`
- `publish_verification_ref`
- `next_action`

### `Phase5RecoveryTicketArtifact`

必须包含：

- `artifact_family = "phase5_recovery_ticket"`
- `schema_version`
- `ticket_id`
- `cycle_id`
- `failed_step`
- `failure_class`
- `failure_observed_at`
- `evidence_refs`
- `recovery_action`
- `retry_count`
- `final_status`
- `claim_ceiling_effect`
- `notes`

### `Phase5GateReadoutArtifact`

必须包含：

- `artifact_family = "phase5_gate_readout"`
- `schema_version`
- `gate_id`
- `cycle_id`
- `gate_status`
- `failing_gate_ids`
- `incomplete_gate_ids`
- `claim_ceiling`
- `source_artifact_ids`
- `blocking_reasons`
- `next_action`
- `evaluated_at`

## 6. Tests

Focused tests 至少覆盖：

- 三类 artifact 都能写入临时 runtime root 并读回。
- 默认 repo artifact root 写入仍被拒绝。
- artifact 路径隔离在 `autonomous_flow/...` 下。
- `publish_verification_ref` 只保存 manifest ref / digest，不要求 manifest 明细。

## 7. 验收

- `git diff --check` 通过。
- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_artifacts.py` 通过。
- `PYTHONPATH=src python3 -m pytest tests/test_research_artifact_store.py tests/test_autonomous_flow_artifacts.py` 通过。
- registry check 对本 Context Pack 通过。
