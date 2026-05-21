# Trial CM 评估记录：Auto Progress Run Artifact

状态：verified
输入：`TRIAL_CM_CONTEXT_PACK_CN.md`
目标：评估 auto-progress apply 是否能可选记录 run artifact。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| CM1 | artifact、store、recorder、CLI、tests、本评估文件 | 记录 auto-progress run | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 记录字段完整性 | 35 |
| recorder 无副作用重放 | 25 |
| CLI record envelope | 20 |
| 验证完整性 | 20 |

自动重跑阈值：

- recorder 调用 apply executor。
- 缺少 issued_at/runner_id 时仍写 artifact。
- focused tests、ruff、process hardening 或 full regression 失败。

## 3. CM1 结果

- 新增 `Phase5SchedulerAutoProgressRunArtifact`，artifact family 为 `phase5_scheduler_auto_progress_run`。
- 新增 auto-progress run store 与 recorder；recorder 只接收已完成的 apply result，不重新执行 apply。
- CLI `attempt-run-auto-progress-apply` 增加 `--record-auto-progress-run` 与 `--auto-progress-run-id`。
- record envelope 包含 `auto_progress_apply_result`、`auto_progress_run_artifact`、artifact path 与 record status。
- 缺少 `issued_at` 或 `runner_id` 时 record status 返回 blocked，不写 artifact。
- Registry 新增 `phase5.scheduler.auto_progress_run.recorded.v1` 与 `phase5_scheduler_auto_progress_run`。

## 4. 主进程验证

- Focused tests 初次失败：新 artifact family 未注册到 `ARTIFACT_FOLDERS`；补 `artifact_store_core.py` 映射后通过。
- Registry 初次失败：`phase5_scheduler_auto_progress_run` 未注册；补 registry event 与 artifact family 后通过。
- Focused tests：`PYTHONPATH=src python3 -m pytest tests/test_scheduler_auto_progress_recorder.py tests/test_cli_autonomous_flow_auto_progress_run_record_output.py -q`，结果 `3 passed`。
- Required evidence：`tests/test_scheduler_auto_progress_recorder.py:test_auto_progress_recorder_writes_run_artifact`。
- Required evidence：`tests/test_cli_autonomous_flow_auto_progress_run_record_output.py:test_auto_progress_apply_output_records_run_when_enabled`。
- Ruff：`ruff check src/ashare_evidence/scheduler_auto_progress_artifacts.py src/ashare_evidence/scheduler_auto_progress_artifact_store.py src/ashare_evidence/scheduler_auto_progress_recorder.py src/ashare_evidence/artifact_store_core.py src/ashare_evidence/cli_autonomous_flow_auto_progress_outputs.py src/ashare_evidence/cli_autonomous_flow.py tests/test_scheduler_auto_progress_recorder.py tests/test_cli_autonomous_flow_auto_progress_run_record_output.py`，结果 `All checks passed!`。
- Contract registry：`contract-registry-check` 覆盖 CM context/evaluation docs，结果 `status=pass`、`issue_count=0`。
- Full regression：`PYTHONPATH=src python3 -m pytest -q`，结果 `621 passed, 147 deselected`。
- 文件规模：artifact 33 行、store 43 行、recorder 117 行、CLI auto-progress outputs 86 行、registry 575 行，均低于本轮 warning budget。
- 已知 warning：`artifact_store_core.py` 152 行，超过本轮 warning 线 150 行但低于 hard 180；本轮只新增 1 个 artifact folder 映射，暂不为中心常量表拆文件。

## 5. 重跑记录

- 2 次结构性修正：补 artifact store folder 映射；补 registry event/family。均属于新增契约的必要注册，不是绕过测试。
- 1 个规模 warning 已记录：`artifact_store_core.py` 中心映射接近拆分阈值，后续若继续增加 artifact family，应单独设计 registry-driven folder mapping。

## 6. 自评

- 本轮补齐了工作台和审计需要的 auto-progress run 硬存储。
- auto-progress apply 仍保持一次一跳；recording 是可选包装，不改变执行语义。
- 下一步建议进入 Trial CN：新增 auto-progress run readout，按 cycle/runner 汇总最近自动推进历史，给 PC/mobile 工作台提供直接 projection 输入。
