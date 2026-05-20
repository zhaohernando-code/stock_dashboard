# Trial AD 评估记录：Scheduler Execution Ledger

状态：已完成  
输入：`TRIAL_AD_CONTEXT_PACK_CN.md`  
目标：评估 scheduler execution ledger 是否能为后续真实 scheduler action 提供幂等、可恢复、可审计的执行意图记录。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| AD1 | registry/schema、artifact model、execution store、record 函数、测试、本评估文件 | 实现 execution ledger 最小持久化合同 |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| Execution ledger 合同符合度 | 30 |
| 幂等与无副作用边界 | 25 |
| cycle 缺失容错 | 15 |
| registry/schema 一致性 | 15 |
| 文件规模与测试覆盖 | 15 |

自动重跑阈值：

- 总分低于 85。
- record 函数执行真实 scheduler action。
- cycle 缺失时不写 ledger 或抛错。
- record 函数改变 cycle status、next action 或 finished at。
- 新增 id 未注册或 registry check 失败。
- focused tests 失败。

## 3. AD1 结果

实现结果：

- 新增 `Phase5SchedulerExecutionLedgerArtifact`，artifact family 为 `phase5_scheduler_execution_ledger`，schema version 为 `v1`。
- 新增注册事件 `phase5.scheduler.execution.recorded.v1`，并在 registry 中注册 execution ledger artifact family 与 schema。
- 新增独立 store 模块 `scheduler_execution_artifact_store.py`，负责 execution ledger 的 write/read/read-if-exists，没有继续扩张既有 autonomous flow artifact store。
- 新增 `record_phase5_scheduler_execution_ledger(...)`：
  - 所有输入由调用方显式传入，不读 DB、网络、当前时间或 LLM。
  - 始终先写 execution ledger。
  - cycle 存在时只追加 `phase5.scheduler.execution.recorded.v1` event ref。
  - cycle 缺失时返回 `cycle=None`，不抛错，ledger 仍落盘。
  - 不改变 cycle `status`、`next_action`、`finished_at`，不写 recovery ticket，不执行真实 scheduler action。
- 新增 `tests/test_autonomous_flow_scheduler_execution_ledger.py`，覆盖 model 默认 event、去重、store 读写、cycle 存在/缺失、cycle 不变性和敏感内容保护。

文件规模：

- `src/ashare_evidence/scheduler_execution_artifact_store.py`：74 行，低于 180 行约束。
- `tests/test_autonomous_flow_scheduler_execution_ledger.py`：186 行，低于 260 行约束。

## 4. 主进程验证

门禁结果：

| 命令 | 结果 |
| --- | --- |
| `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_scheduler_execution_ledger.py tests/test_autonomous_flow.py -q` | `17 passed` |
| `ruff check src/ashare_evidence/autonomous_flow_artifacts.py src/ashare_evidence/scheduler_execution_artifact_store.py src/ashare_evidence/autonomous_flow.py tests/test_autonomous_flow_scheduler_execution_ledger.py` | passed |
| `wc -l src/ashare_evidence/scheduler_execution_artifact_store.py tests/test_autonomous_flow_scheduler_execution_ledger.py` | `74 / 186` |
| `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_AD_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_AD_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated` | `status=pass, issue_count=0` |
| `git diff --check` | passed |
| `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage` | `status=pass` |
| `PYTHONPATH=src python3 -m pytest -q` | `371 passed, 147 deselected` |

## 5. 重跑记录

无需重跑。首轮实现的 focused tests、ruff、registry、policy audit、full pytest 和 diff whitespace gate 均通过。

## 6. 自评

综合评分：96 / 100。

- Execution ledger 合同符合度：30 / 30。字段、event refs、schema、registry 均与 Context Pack 对齐。
- 幂等与无副作用边界：25 / 25。idempotency key 由调用方传入；record 函数没有真实执行 scheduler action。
- cycle 缺失容错：15 / 15。cycle 缺失时 ledger 仍写入并返回 `None`。
- registry/schema 一致性：15 / 15。registry check 通过。
- 文件规模与测试覆盖：11 / 15。当前规模满足约束，但后续如果 execution ledger 继续扩展，需要避免把 test 文件扩到 260 行以上。

残余风险：

- 本轮仅记录 execution ledger，不实现真实执行锁、重复 idempotency key 冲突检测或多进程原子 compare-and-set。后续接入真实 scheduler action 前，需要新增 execution claim / conflict check 层。
- 新 store 模块为专用路径实现，避免改非 owned 的 `artifact_store_core.py`；后续如果 artifact store family 继续增多，应抽象一个轻量 family registry，而不是在各模块复制路径逻辑。
