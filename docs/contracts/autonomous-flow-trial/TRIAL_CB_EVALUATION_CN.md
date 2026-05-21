# Trial CB 评估记录：Attempt Run Intervention Plan

状态：verified
输入：`TRIAL_CB_CONTEXT_PACK_CN.md`
目标：评估 attempt-run follow-up decision 是否能稳定转换为可执行介入计划，同时保持只读、无 side effect 边界。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| CB1 | intervention plan module、CLI output、tests、本评估文件 | 将 attempt-run decision 固化为可执行计划 | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 策略转换清晰 | 35 |
| side effect 边界 | 25 |
| CLI 兼容性 | 20 |
| 验证完整性 | 20 |

自动重跑阈值：

- `attempt-run-followup-decision` 原输出 shape 改变。
- intervention plan 模块出现 IO、时钟、随机或 artifact 写入。
- CLI intervention 输出触发 scheduler handler 或写入 artifact。
- focused tests、ruff、process hardening、registry 或 full regression 失败。

## 3. CB1 结果

- 新增 `scheduler_attempt_run_intervention_plan.py`，将 attempt-run readout + decision 转成 typed intervention plan。
- 新增 CLI 输出 `attempt-run-intervention-plan`，保持只读：只读取 attempt/run artifacts，不跑 tick、不跑 scheduler handler、不写新 artifact。
- intervention plan 使用 `plan_status/action/execution_boundary/required_arguments/missing_arguments` 明确后续执行边界。
- blocked latest 映射为 `open_recovery_ticket` + `route_apply_required` + `scheduler_diagnostic`；empty/applied 映射为 `continue_tracking` + `observe_only`。
- 未复用 tick 派生的 `Phase5SchedulerFollowupPlan`，避免伪造 `source_tick_status`。

## 4. 主进程验证

- `PYTHONPATH=src python3 -m pytest tests/test_scheduler_attempt_run_intervention_plan.py tests/test_cli_autonomous_flow_attempt_intervention_plan_output.py tests/test_cli_autonomous_flow_attempt_followup_decision_output.py -q` 通过，9 passed。
- `ruff check src/ashare_evidence/scheduler_attempt_run_intervention_plan.py src/ashare_evidence/cli_autonomous_flow_attempt_readout_outputs.py src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_output_dispatch.py tests/test_scheduler_attempt_run_intervention_plan.py tests/test_cli_autonomous_flow_attempt_intervention_plan_output.py` 通过。
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check ...` 通过，issue_count 0。
- `PYTHONPATH=src python3 -m pytest -q` 通过，552 passed，147 deselected。

## 5. 重跑记录

- 首轮 focused tests 失败：实现把后续 route apply 所需的 `diagnostic_id/observed_at` 当成当前 plan 缺失参数，导致 blocked latest 被错误标成 `blocked`。
- 修正后只把当前 plan 阶段必须具备的 `cycle_id` 作为阻断参数；`diagnostic_id/observed_at` 保留在 `required_arguments` 中，作为下一阶段 route apply 的边界要求。

## 6. 自评

- 本轮验证了“计划阶段”和“执行阶段参数”必须分层，否则无人值守流程会过早阻断可恢复任务。
- intervention plan 仍是只读意图层，下一轮应新增执行器把 `route_apply_required` 映射到已有 diagnostic route apply，并继续保持幂等与 side effect 边界。
