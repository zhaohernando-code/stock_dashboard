# Trial E 评估记录：Phase 5 自运行 Ledger Artifact

状态：进行中  
输入：`TRIAL_E_CONTEXT_PACK_CN.md`  
目标：评估 `phase5_cycle_ledger`、`phase5_recovery_ticket`、`phase5_gate_readout` 最小 artifact 读写层。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| E1 | `autonomous_flow_artifacts.py`、`research_artifact_store.py`、`test_autonomous_flow_artifacts.py` | 实现三类 artifact model 与 read/write 路径 |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| Schema 合同符合度 | 30 |
| Artifact store 集成一致性 | 25 |
| 测试覆盖 | 25 |
| 约束遵守 | 20 |

自动重跑阈值：

- 总分低于 85。
- 任一 required schema 字段缺失。
- 绕过 `_ensure_artifact_write_allowed`。
- 写入路径不在 `autonomous_flow/` 隔离目录。
- focused tests 失败。

## 3. E1 结果

接受。

改动范围：

- `src/ashare_evidence/autonomous_flow_artifacts.py`
- `src/ashare_evidence/research_artifact_store.py`
- `tests/test_autonomous_flow_artifacts.py`

评分：

| 维度 | 权重 | 得分 | 说明 |
| --- | ---: | ---: | --- |
| Schema 合同符合度 | 30 | 29 | 三类 artifact required fields 与 registry schema 对齐。 |
| Artifact store 集成一致性 | 25 | 24 | 复用现有 `_write_model` / `_read_model` / 写入保护。 |
| 测试覆盖 | 25 | 23 | 覆盖三类 artifact round trip、missing read、repo write guard、publish ref 禁止明细。 |
| 约束遵守 | 20 | 20 | 未接 scheduler/projection/API/frontend，未新增 DB。 |
| **总分** | **100** | **96** | 接受。 |

接受内容：

- 新增 `Phase5CycleLedgerArtifact`、`Phase5RecoveryTicketArtifact`、`Phase5GateReadoutArtifact`。
- 新增 `PublishVerificationRef`，只保存 `release_manifest_ref`、`digest` 和可选 `event_ref`。
- artifact 路径隔离在：
  - `autonomous_flow/phase5_cycle_ledger`
  - `autonomous_flow/phase5_recovery_ticket`
  - `autonomous_flow/phase5_gate_readout`
- store 新增三类 artifact 的 `write/read/read_if_exists`。

## 4. 主进程验证

已完成：

```bash
PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_artifacts.py
PYTHONPATH=src python3 -m pytest tests/test_research_artifact_store.py tests/test_autonomous_flow_artifacts.py
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_E_CONTEXT_PACK_CN.md \
  --fail-on-unregistered \
  --fail-on-deprecated
```

结果：

- `tests/test_autonomous_flow_artifacts.py` 通过，`4 passed`。
- `tests/test_research_artifact_store.py tests/test_autonomous_flow_artifacts.py` 通过，`10 passed`。
- `tests/test_autonomous_flow_artifacts.py tests/test_research_artifact_store.py tests/test_contract_registry.py tests/test_claim_ceiling.py` 通过，`21 passed`。
- 完整 `PYTHONPATH=src python3 -m pytest -q` 通过，`233 passed, 147 deselected`。
- `policy-audit` 通过。
- registry check 通过，`issue_count=0`。

## 5. 重跑记录

本轮不触发重跑。

残余风险进入下一轮：

- 目前只是 artifact store 层，尚未接入 scheduler、projection builder 或 publish verifier。
- `publish_verification_ref` 当前保存最小指针和 digest；如后续需要完整 event envelope，需要扩展 schema。
- `input_contract_versions` 仍是简单 key/value；如果后续 Context Pack 版本信息变复杂，需要新增结构而不是塞入自由文本。
