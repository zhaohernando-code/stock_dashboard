# Trial AF Context Pack：Scheduler Execution Idempotency Reservation

状态：active input  
上游：Trial AE  
目标：为 scheduler execution ledger 增加原子 reservation 层，避免同一 idempotency key 在并发或 crash replay 场景下被重复认定为新 execution。

## 1. 背景

Trial AE 已经固定了最小幂等语义：

- same idempotency key + same execution id：返回 existing ledger。
- same idempotency key + different execution id：typed conflict。
- existing ledger 存在但 cycle event 缺失时可补 event。

但 AE 仍依赖“扫描 ledger 目录再写 ledger”的非原子流程。两个进程同时扫描到空结果时，仍可能分别写入不同 execution ledger。本轮要补的是 execution 入口的 reservation 层，而不是继续扩大扫描逻辑。

## 2. 本轮目标

- 新增 scheduler execution idempotency reservation artifact 或 sidecar model。
- reservation 文件名必须由 idempotency key 的稳定 digest 生成，不能把原始 key 直接放进路径。
- reservation 写入必须使用原子 create-if-absent 语义；已有 reservation 时不能覆盖。
- record 层先 reserve，再检查 ledger，再写 ledger。
- same key + same execution id + ledger missing：允许继续写 ledger，用于 crash after reservation before ledger write 的恢复。
- same key + different execution id：抛 Trial AE 的 typed conflict error，不写新 ledger，不修改 cycle。
- 保留 Trial AE 的 existing ledger replay 和 event 补写语义。

## 3. 非目标

- 不执行真实 scheduler action。
- 不接 CLI output。
- 不引入跨机器分布式锁。
- 不新增 recovery ticket。
- 不修改 tick / planner / executor。
- 不修改 API / SPA。

## 4. Owned Files

默认允许修改：

- `src/ashare_evidence/autonomous_flow_artifacts.py`
- `src/ashare_evidence/scheduler_execution_artifact_store.py`
- `src/ashare_evidence/autonomous_flow.py`
- `tests/test_autonomous_flow_scheduler_execution_reservation.py`
- `tests/test_autonomous_flow_scheduler_execution_idempotency.py`
- `tests/helpers_autonomous_flow_scheduler_execution.py`
- `docs/contracts/registry/autonomous_flow_registry.v1.json`
- `docs/contracts/registry/schemas/phase5_scheduler_execution_reservation.schema.json`
- `docs/contracts/autonomous-flow-trial/TRIAL_AF_EVALUATION_CN.md`

如果实现不需要新增 registered artifact family，可以不修改 registry/schema，但必须在评估中说明为什么 reservation 只是内部 sidecar。

## 5. 合同要求

Reservation model 至少包含：

- artifact family / schema version
- reservation id
- idempotency key
- execution id
- cycle id
- created at
- source

Store 层要求：

- 提供稳定 reservation id 生成函数。
- 提供 create-if-absent reservation 函数。
- 原子创建失败时读取 existing reservation 并返回，不覆盖 existing payload。
- 如果 digest 文件存在但 payload 中的 idempotency key 与请求不一致，必须 fail closed。
- 继续拒绝默认写入 repo source artifact 目录。

Record 层要求：

- 先 reserve idempotency key，再处理 ledger。
- reservation execution id 与请求 execution id 不一致时，复用 Trial AE typed conflict error。
- reservation same execution id 且 ledger missing 时，继续写 ledger。
- reservation same execution id 且 ledger existing 时，不重写 ledger。
- conflict 分支不得写新 ledger，不得追加 cycle event。

## 6. Tests

至少覆盖：

- reservation id 对相同 key 稳定，对包含 slash/colon/space 的 key 仍生成安全文件名。
- 首次 reserve 创建文件，重复 reserve 返回 existing 且不覆盖。
- digest 文件 payload key mismatch 时 fail closed。
- record 首次执行会创建 reservation 和 ledger。
- reservation 已存在但 ledger 缺失时，same execution id 可恢复写 ledger。
- reservation 已存在且 execution id 不同时，typed conflict 且无 ledger/cycle 副作用。
- Trial AE 的 replay/conflict tests 继续通过。

## 7. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_scheduler_execution_reservation.py tests/test_autonomous_flow_scheduler_execution_idempotency.py tests/test_autonomous_flow_scheduler_execution_ledger.py tests/test_autonomous_flow.py -q`
- `ruff check src/ashare_evidence/autonomous_flow_artifacts.py src/ashare_evidence/scheduler_execution_artifact_store.py src/ashare_evidence/autonomous_flow.py tests/test_autonomous_flow_scheduler_execution_reservation.py tests/test_autonomous_flow_scheduler_execution_idempotency.py tests/helpers_autonomous_flow_scheduler_execution.py`
- `wc -l src/ashare_evidence/scheduler_execution_artifact_store.py tests/test_autonomous_flow_scheduler_execution_reservation.py tests/test_autonomous_flow_scheduler_execution_idempotency.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_AF_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_AF_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage`
- `git diff --check`
- `PYTHONPATH=src python3 -m pytest -q`
