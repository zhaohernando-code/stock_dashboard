# Trial AE Context Pack：Scheduler Execution Idempotency

状态：active input  
上游：Trial AD  
目标：为 scheduler execution ledger 增加 idempotency key 冲突检查与幂等重放语义，避免同一 scheduler action 被重复记录成多个不一致 execution。

## 1. 背景

Trial AD 建立了 execution ledger，但 residual risk 明确指出：

- 尚未检测重复 idempotency key。
- 尚未处理 ledger 已写但 cycle event 未追加的 crash recovery。
- 尚未定义不同 execution id 复用同一 idempotency key 时的阻断行为。

真实 scheduler action 执行前，必须先把这些边界固定下来。

## 2. 本轮目标

增强 execution ledger 记录层：

- 新增按 idempotency key 查找 existing ledger 的 store 函数。
- `record_phase5_scheduler_execution_ledger(...)` 写入前检查 idempotency key。
- 相同 idempotency key + 相同 execution id：幂等返回 existing ledger，不重写 ledger。
- 相同 idempotency key + 不同 execution id：抛出 typed conflict error。
- 如果 existing ledger 已存在但 cycle ledger 缺少 execution event，可补追加 event，用于 crash recovery。
- 保持不执行真实 scheduler action。

## 3. 非目标

- 不接 CLI。
- 不实现多进程原子 compare-and-set。
- 不执行 scheduler action。
- 不写 recovery ticket。
- 不改 registry/schema。
- 不改 API / SPA。

## 4. Owned Files

默认只允许修改：

- `src/ashare_evidence/scheduler_execution_artifact_store.py`
- `src/ashare_evidence/autonomous_flow.py`
- `tests/test_autonomous_flow_scheduler_execution_ledger.py`
- `tests/test_autonomous_flow_scheduler_execution_idempotency.py`
- `tests/helpers_autonomous_flow_scheduler_execution.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_AE_EVALUATION_CN.md`

## 5. 合同要求

新增 store 函数建议：

```python
find_phase5_scheduler_execution_ledger_by_idempotency_key(
    idempotency_key: str,
    *,
    root: Path | None = None,
) -> Phase5SchedulerExecutionLedgerArtifact | None
```

要求：

- 只扫描 execution ledger artifact family 目录。
- 如果没有匹配，返回 None。
- 如果找到多个不同 execution id 使用同一 idempotency key，返回第一个稳定排序结果即可；冲突检测由 record 层处理新请求与 existing 的关系。
- 不读取 DB、网络、当前时间或 LLM。

Typed conflict error：

- 新增 `Phase5SchedulerExecutionIdempotencyConflictError`。
- 字段至少包含 idempotency key、existing execution id、requested execution id。
- 错误 message 不包含敏感 payload。

Record 层：

- 新 idempotency key：行为同 Trial AD。
- existing same execution id：返回 existing ledger；如果 cycle 存在且缺少 execution event，补追加 event。
- existing different execution id：抛 typed conflict error；不写新 ledger，不修改 cycle。
- cycle 缺失时仍允许 existing same execution id 幂等返回。

## 6. Tests

至少覆盖：

- store 按 idempotency key 找到 existing ledger。
- record 重复相同 execution id 时不重写 ledger，返回 existing。
- record 重复相同 execution id 且 cycle event 缺失时补 event。
- record 相同 idempotency key 但 execution id 不同，抛 typed conflict error。
- conflict 不写新 ledger、不修改 cycle。
- focused tests 继续覆盖 Trial AD 原行为。

## 7. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_scheduler_execution_ledger.py tests/test_autonomous_flow_scheduler_execution_idempotency.py tests/test_autonomous_flow.py -q`
- `ruff check src/ashare_evidence/scheduler_execution_artifact_store.py src/ashare_evidence/autonomous_flow.py tests/test_autonomous_flow_scheduler_execution_ledger.py tests/test_autonomous_flow_scheduler_execution_idempotency.py tests/helpers_autonomous_flow_scheduler_execution.py`
- `wc -l src/ashare_evidence/scheduler_execution_artifact_store.py tests/test_autonomous_flow_scheduler_execution_ledger.py tests/test_autonomous_flow_scheduler_execution_idempotency.py tests/helpers_autonomous_flow_scheduler_execution.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_AE_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_AE_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage`
- `git diff --check`
- `PYTHONPATH=src python3 -m pytest -q`
