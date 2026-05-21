# Trial BQ 评估记录：Scheduler Attempt Run Artifact Store

状态：verified
输入：`TRIAL_BQ_CONTEXT_PACK_CN.md`
目标：评估 scheduler attempt/run 总结 artifact 与存储层是否满足硬存储底座要求。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| BQ1 | attempt run artifact model、store、schema、registry、focused tests、本评估文件 | 建立可持久化的 attempt/run 总结底座 | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 状态表达完整性 | 30 |
| artifact/store 设计隔离 | 25 |
| registry/schema 一致性 | 20 |
| 安全与确定性 | 15 |
| 验证完整性 | 10 |

自动重跑阈值：

- CLI 写盘被混入本轮。
- 从自然语言 reason 解析结构化状态。
- 新增本地时间、随机数或 UUID。
- artifact family 未注册或 schema 缺失。
- focused tests、ruff、process hardening、registry 或 full regression 失败。

## 3. BQ1 结果

- 新增 `phase5_scheduler_attempt_run` artifact family 与 `phase5.scheduler.attempt_run.recorded.v1` event。
- 新增独立模型 `scheduler_attempt_run_artifacts.py`，覆盖 run/attempt/cycle/runner/issued_at、attempt/route/preflight/apply 状态、applied output、required/missing arguments、diagnostic/execution/idempotency、cycle event、error type、reason、blocking/event refs。
- 新增独立 store `scheduler_attempt_run_artifact_store.py`，提供 write、read、read-if-exists，并映射到 `autonomous_flow/phase5_scheduler_attempt_run`。
- focused tests 覆盖写读、missing 返回 None、结构化 apply 摘要字段、敏感 identity 拒绝、reason 清洗、refs 去重。
- 未接 CLI 写盘，未解析自然语言 reason，未修改 process hardening，未扩大 near-warning 文件。

## 4. 主进程验证

- `PYTHONPATH=src python3 -m pytest tests/test_scheduler_attempt_run_artifact_store.py -q`：passed，3 tests。
- `ruff check src/ashare_evidence/scheduler_attempt_run_artifacts.py src/ashare_evidence/scheduler_attempt_run_artifact_store.py tests/test_scheduler_attempt_run_artifact_store.py`：passed。
- `PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check ...`：passed，0 issues；所有文件低于 warning budget；forbidden token 未命中。
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check ...`：passed，0 issues；registered ids 59。
- `PYTHONPATH=src python3 -m pytest -q`：passed，525 tests，147 deselected。

主进程语义复核：

- BQ1 初版 artifact 已能持久化关键状态，但缺少 `applied_output`、required/missing arguments、`cycle_event_recorded`、`error_type`。这些字段对后续恢复运行、看板展示和 reviewer 定位问题有价值，已在主进程补齐并同步 schema、registry 与 tests。
- 未接 CLI 写盘；本轮仍保持模型/store 先行，避免把持久化副作用直接揉进 BM 的一条命令。
- 未从自然语言 reason 解析结构化状态；reason 只作为被清洗后的说明字段保存。

## 5. 重跑记录

- 主进程补齐结构化恢复字段后重跑 focused tests、ruff、process hardening、registry 和 full regression，均通过。

## 6. 自评

- 状态表达完整性：30 / 30。字段覆盖 context pack 要求的 run、attempt、cycle、runner、issued_at、attempt/route/preflight/apply 状态，并补齐 applied output、required/missing arguments、cycle event、error type。
- artifact/store 设计隔离：25 / 25。模型与 store 独立于 `autonomous_flow_artifacts.py` 和 CLI 写盘路径。
- registry/schema 一致性：20 / 20。family、event、schema 与 folder 映射一致，registry gate 通过。
- 安全与确定性：15 / 15。显式输入，无本地时间、随机数或 UUID；敏感 identity 拒绝，reason 与 refs 清洗。
- 验证完整性：10 / 10。focused tests、ruff、process hardening、registry、full regression 均通过。
