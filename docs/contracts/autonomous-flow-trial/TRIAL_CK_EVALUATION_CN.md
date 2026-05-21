# Trial CK 评估记录：Auto Progress Plan

状态：verified
输入：`TRIAL_CK_CONTEXT_PACK_CN.md`
目标：评估系统是否能只读判断下一步 auto-progress CLI。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| CK1 | plan、CLI output、tests、本评估文件 | 生成下一步 auto-progress plan | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 下一步优先级正确性 | 35 |
| 参数阻塞可解释性 | 25 |
| 副作用隔离 | 20 |
| 验证完整性 | 20 |

自动重跑阈值：

- plan 模块调用 apply executor 或写 artifact。
- 缺参数时仍返回 ready。
- focused tests、ruff、process hardening 或 full regression 失败。

## 3. CK1 结果

- 新增 `Phase5SchedulerAutoProgressPlan`，只读组合 attempt run readout、intervention run readout、recovery ticket intent 与 recovery follow-up intent。
- 新增 CLI 输出 `attempt-run-auto-progress-plan`，返回下一步 recommended output、recommended flags、required arguments、missing arguments、blocking reasons 与 evidence refs。
- 优先级已固化：`recovery_followup_apply` > `recovery_ticket_apply` > `intervention_apply` > `wait_for_next_tick`。
- 参数阻塞已结构化：follow-up apply 缺 `created_at` 返回 blocked；intervention apply record 缺 `issued_at` 或 `runner_id` 返回 blocked。
- 副作用隔离通过：planner 不调用 apply executor，不写 artifact。

## 4. 主进程验证

- Focused tests 初次失败：CLI test guard 使用了不存在的函数名；修正为 `build_attempt_context_and_apply_phase5_scheduler_action_route`。
- Ruff 初次失败：dispatcher import 排序；执行 `ruff check --fix` 后复检通过。
- Focused tests：`PYTHONPATH=src python3 -m pytest tests/test_scheduler_auto_progress_plan.py tests/test_cli_autonomous_flow_auto_progress_plan_output.py -q`，结果 `7 passed`。
- Required evidence：`tests/test_scheduler_auto_progress_plan.py:test_auto_progress_plan_recommends_intervention_apply_for_blocked_attempt`。
- Required evidence：`tests/test_cli_autonomous_flow_auto_progress_plan_output.py:test_auto_progress_plan_output_recommends_recovery_followup_apply`。
- Ruff：`ruff check src/ashare_evidence/scheduler_auto_progress_plan.py src/ashare_evidence/cli_autonomous_flow_auto_progress_outputs.py src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_output_dispatch.py tests/test_scheduler_auto_progress_plan.py tests/test_cli_autonomous_flow_auto_progress_plan_output.py`，结果 `All checks passed!`。
- Contract registry：`contract-registry-check` 覆盖 CK context/evaluation docs，结果 `status=pass`、`issue_count=0`。
- Full regression：`PYTHONPATH=src python3 -m pytest -q`，结果 `613 passed, 147 deselected`。
- 文件规模：planner 223 行、CLI auto-progress outputs 22 行、dispatcher 136 行、主 CLI 130 行，均低于本轮 warning budget。

## 5. 重跑记录

- 1 次机械重跑：修正测试 guard 函数名与 import 排序；无语义回滚或补丁式绕过。

## 6. 自评

- 本轮把分散 CLI 推进为可判断下一步的只读 planner，降低人工介入。
- 设计仍保持两段式：plan 不执行写入，apply 仍由既有 executor 负责。
- 下一步建议进入 Trial CL：在 auto-progress plan 之上实现受控 auto-progress apply，一次只执行一个 recommended step，并返回可审计 envelope。
