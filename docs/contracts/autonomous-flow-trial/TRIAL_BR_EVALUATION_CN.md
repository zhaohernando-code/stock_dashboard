# Trial BR 评估记录：Scheduler Attempt Run Recorder

状态：verified
输入：`TRIAL_BR_CONTEXT_PACK_CN.md`
目标：评估 typed attempt route apply result 到 attempt/run artifact 的映射与写入是否稳定。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| BR1 | recorder module、focused tests、本评估文件 | 建立 typed result 到 attempt/run artifact 的稳定映射层 | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 结构化字段映射完整性 | 35 |
| 确定性 run id 与显式上下文 | 20 |
| store 写入隔离 | 20 |
| 禁止 reason parsing | 15 |
| 验证完整性 | 10 |

自动重跑阈值：

- CLI 写盘被混入本轮。
- 从自然语言 reason 解析结构化状态。
- 新增本地时间、随机数或 UUID。
- typed result 的关键字段未映射到 artifact。
- focused tests、ruff、process hardening、registry 或 full regression 失败。

## 3. BR1 结果

- 新增 `scheduler_attempt_run_recorder.py`，提供 typed result 到 `Phase5SchedulerAttemptRunArtifact` 的纯 builder。
- 新增 deterministic run id builder；run id 只来自结构化 result、显式 `runner_id`、显式 `issued_at`，不使用本地时间、UUID 或随机数。
- 新增 recorder，调用 builder 后通过既有 `phase5_scheduler_attempt_run` store 写入，并返回 artifact 与 path。
- 字段映射覆盖 attempt/preflight/apply 状态、route type、applied output、required/missing arguments、diagnostic/execution/idempotency、cycle event、reason、error type。
- blocking reasons 不解析自然语言 reason；仅使用显式输入，或从 `missing_arguments` 结构化降级生成。
- 新增 `tests/test_scheduler_attempt_run_recorder.py` 覆盖 applied、blocked missing context、deterministic id、写读。

## 4. 主进程验证

- `PYTHONPATH=src python3 -m pytest tests/test_scheduler_attempt_run_recorder.py tests/test_scheduler_attempt_run_artifact_store.py -q`：通过，7 passed。
- `ruff check src/ashare_evidence/scheduler_attempt_run_recorder.py tests/test_scheduler_attempt_run_recorder.py`：通过。
- `PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check ...`：通过，0 issues。
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check ...`：通过，0 issues。
- `PYTHONPATH=src python3 -m pytest -q`：通过，529 tests，147 deselected。

主进程语义复核：

- recorder 是独立层，未接 CLI 写盘，后续接入点可以保持很薄。
- artifact 字段直接从 `Phase5SchedulerAttemptRouteApplyResult` 映射；`reason` 只复制并由 BQ artifact 模型清洗，不参与结构化判断。
- 默认 `blocking_reasons` 只从 `missing_arguments` 这类结构化字段生成；显式传入时交给 artifact 模型去重与清洗。
- run id builder 使用 cycle、attempt、runner、issued_at、route/status/output/ref 字段计算稳定 digest，不使用本地时间、UUID 或随机数。

## 5. 重跑记录

- 无重跑；主进程补充全量回归后通过。

## 6. 自评

- BR1 范围内完成；未接 CLI 写盘，未修改 `process_hardening.py`，未解析自然语言 reason。focused tests、ruff、process hardening、registry、full regression 均通过。
