# Trial AE 评估记录：Scheduler Execution Idempotency

状态：已完成  
输入：`TRIAL_AE_CONTEXT_PACK_CN.md`  
目标：评估 scheduler execution ledger 是否具备最小 idempotency key 冲突检测与幂等重放能力。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| AE1 | execution store、record 函数、execution tests、本评估文件 | 增加 idempotency lookup、repeat replay 和 conflict check |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| Idempotency 合同符合度 | 35 |
| 无副作用冲突阻断 | 25 |
| crash recovery event 补写 | 20 |
| 测试覆盖与文件规模 | 20 |

自动重跑阈值：

- 相同 idempotency key + 不同 execution id 未阻断。
- conflict 写入新 ledger 或修改 cycle。
- existing same execution id 不能幂等返回。
- focused tests 失败。
- store/test 文件超过约束。

## 3. AE1 结果

- `scheduler_execution_artifact_store.py` 新增 `find_phase5_scheduler_execution_ledger_by_idempotency_key(...)`，只扫描 `autonomous_flow/phase5_scheduler_execution_ledger` artifact family 目录，并按文件名稳定排序返回首个匹配 ledger。
- `autonomous_flow.py` 新增 `Phase5SchedulerExecutionIdempotencyConflictError`，错误对象保留 `idempotency_key`、`existing_execution_id`、`requested_execution_id` 字段；异常 message 不携带 payload 明细。
- `record_phase5_scheduler_execution_ledger(...)` 在写入前先按 idempotency key 查 existing ledger：
  - 无 existing：保持 Trial AD 写 ledger + 追加 cycle event 行为。
  - same key + same execution id：幂等返回 existing ledger，不重写 ledger；cycle 存在且缺少 execution event 时补追加 event。
  - same key + different execution id：抛 typed conflict error，不写新 ledger，不修改 cycle。
  - existing same execution id 且 cycle 缺失：返回 `(None, existing)`。
- 未修改 CLI、tick、plan、executor、artifact model、registry、schema、API、SPA；未执行 scheduler action，未写 recovery ticket，未创建 follow-up cycle。

## 4. 主进程验证

- 子进程首轮 focused tests 通过，但主进程评估认为测试文件 298 行过于贴近 300 行上限，属于“未超线但不可继续堆叠”的流程风险。
- 主进程将 execution ledger 基础测试、idempotency 测试、共享 fixture 拆为三个文件，避免后续继续在同一测试文件追加场景。
- 拆分后行数：store 92 行，基础测试 158 行，idempotency 测试 131 行，共享 helper 38 行。
- Focused tests：`PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_scheduler_execution_ledger.py tests/test_autonomous_flow_scheduler_execution_idempotency.py tests/test_autonomous_flow.py -q`，结果 `21 passed`。
- Ruff：`ruff check src/ashare_evidence/scheduler_execution_artifact_store.py src/ashare_evidence/autonomous_flow.py tests/test_autonomous_flow_scheduler_execution_ledger.py tests/test_autonomous_flow_scheduler_execution_idempotency.py tests/helpers_autonomous_flow_scheduler_execution.py`，结果通过。
- Contract registry：`status=pass, issue_count=0`。
- Policy audit：`status=pass`，无 new unclassified、direct config read、formula side effect、missing config lineage failure。
- `git diff --check`：通过。
- Full regression：`PYTHONPATH=src python3 -m pytest -q`，结果 `375 passed, 147 deselected`。

## 5. 重跑记录

- 第一次 focused tests 通过，但 Ruff 发现 import block 未整理，且测试文件达到 311 行，超过 `<300` 约束。
- 子进程整理 import 并抽出共享 fixture 后，把测试文件收敛到 298 行。
- 主进程判断 298 行仍是流程劣化信号，继续拆出独立 idempotency 测试文件后再进入最终门禁。

## 6. 自评

- Idempotency 合同符合度：通过。same key + same execution id 走 replay，不重写 ledger；same key + different execution id typed conflict。
- 无副作用冲突阻断：通过。conflict 分支在新 ledger 构造/写入和 cycle event 追加前短路。
- Crash recovery event 补写：通过。existing ledger 已存在但 cycle 缺少 execution event 时，会补追加 event。
- 残余风险：本轮仍不是多进程原子 compare-and-set；如果两个进程同时在无 existing 的状态下写入同一 idempotency key，仍需要后续引入真实锁或原子写协议。测试已拆分，下一轮继续扩 execution ledger 时应延续“按行为族建测试文件”的约束。
