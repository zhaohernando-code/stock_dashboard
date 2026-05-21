# Trial BY 评估记录：Attempt Run Follow-up Policy

状态：verified
输入：`TRIAL_BY_CONTEXT_PACK_CN.md`
目标：评估 attempt/run readout 到自运行 follow-up decision 的策略是否清晰、可复用、无副作用。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| BY1 | follow-up policy module、focused tests、本评估文件 | 生成自运行介入的 typed decision | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 策略语义清晰 | 35 |
| typed decision 完整性 | 25 |
| 无副作用边界 | 20 |
| 验证完整性 | 20 |

自动重跑阈值：

- 策略读取 artifact 或调用 CLI。
- 从 reason 解析状态。
- 修改 scheduler plan 或 CLI。
- focused tests、ruff、process hardening、registry 或 full regression 失败。

## 3. BY1 结果

- 新增 `scheduler_attempt_run_followup_policy.py`，提供 typed decision model 和纯策略函数。
- 策略只接受 `Phase5SchedulerAttemptRunReadout`，不读取 artifact、不调用 CLI、不写文件。
- 覆盖 empty、blocked、applied、skipped 四种 readout 状态。

## 4. 主进程验证

- `PYTHONPATH=src python3 -m pytest tests/test_scheduler_attempt_run_followup_policy.py -q`：通过，4 passed。
- `ruff check src/ashare_evidence/scheduler_attempt_run_followup_policy.py tests/test_scheduler_attempt_run_followup_policy.py`：通过。
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check ...`：通过，0 issues。
- `process-hardening-check` 首次发现本文档残留占位符；补齐验证记录后重跑。
- `PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check ...`：通过，0 issues。
- `PYTHONPATH=src python3 -m pytest -q`：通过，543 passed，147 deselected。

## 5. 重跑记录

- process hardening 因评估占位符失败一次，无功能修改。

## 6. 自评

- 策略语义清晰且无副作用；当前只把 readout 转换为 typed decision，尚未接入实际调度执行。
