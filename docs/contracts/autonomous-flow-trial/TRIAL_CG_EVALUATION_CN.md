# Trial CG 评估记录：Recovery Ticket Intent

状态：verified
输入：`TRIAL_CG_CONTEXT_PACK_CN.md`
目标：评估 intervention follow-up decision 是否能稳定转换为 recovery ticket intent。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| CG1 | intent、CLI output、tests、本评估文件 | 输出 recovery ticket intent | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| intent 字段完整性 | 35 |
| 副作用隔离 | 25 |
| CLI 只读边界 | 20 |
| 验证完整性 | 20 |

自动重跑阈值：

- intent 模块写 recovery ticket 或调用 recorder。
- CLI intent 输出写 artifact 或调用 scheduler handler。
- focused tests、ruff、process hardening 或 full regression 失败。

## 3. CG1 结果

- 新增 `Phase5SchedulerRecoveryTicketIntent`，从 intervention run readout 与 follow-up decision 生成 `ready`、`blocked` 或 `skipped` 三类 intent。
- `ready` intent 固化 `ticket_id`、`cycle_id`、`failed_step`、`failure_class`、`failure_observed_at`、`evidence_refs`、`recovery_action`、`final_status`、`claim_ceiling_effect` 与来源字段。
- CLI 新增 `attempt-run-recovery-ticket-intent`，只读取 intervention run artifact 并打印 intent；`blocked` 返回 exit code 4。
- 副作用隔离通过：intent 模块未调用 `record_phase5_recovery_ticket`，也不包含 `write_` 写入路径。
- 兼容取舍：当前复用既有 recovery ticket schema 枚举，scheduler intervention 失败临时映射为 `failed_step=replay_schedule`、`failure_class=contract_violation`，下一轮写入 executor 前再评估是否需要扩展 schema。

## 4. 主进程验证

- Focused tests：`PYTHONPATH=src python3 -m pytest tests/test_scheduler_attempt_run_recovery_ticket_intent.py tests/test_cli_autonomous_flow_attempt_recovery_ticket_intent_output.py -q`，结果 `7 passed`。
- Required evidence：`tests/test_scheduler_attempt_run_recovery_ticket_intent.py:test_recovery_ticket_intent_ready_after_applied_diagnostic`。
- Required evidence：`tests/test_cli_autonomous_flow_attempt_recovery_ticket_intent_output.py:test_attempt_recovery_ticket_intent_output_builds_ready_intent_after_diagnostic`。
- Ruff：`ruff check src/ashare_evidence/scheduler_attempt_run_recovery_ticket_intent.py src/ashare_evidence/cli_autonomous_flow_attempt_intervention_outputs.py src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_output_dispatch.py tests/test_scheduler_attempt_run_recovery_ticket_intent.py tests/test_cli_autonomous_flow_attempt_recovery_ticket_intent_output.py`，结果 `All checks passed!`。
- Contract registry：`contract-registry-check` 覆盖 CG context/evaluation docs，结果 `status=pass`、`issue_count=0`。
- Full regression：`PYTHONPATH=src python3 -m pytest -q`，结果 `583 passed, 147 deselected`。
- 文件规模：新增 intent 146 行、CLI intervention outputs 147 行、dispatcher 118 行、主 CLI 122 行，均低于本轮 warning budget。

## 5. 重跑记录

- 无需重跑。首轮 focused tests、ruff、registry check 与 full regression 均通过。

## 6. 自评

- 本轮符合“基座式演进”：新增独立 intent 模块，没有把 recovery ticket 写入逻辑补丁式塞进 follow-up policy 或 CLI dispatch。
- 当前还不是完整闭环：系统已经能稳定判断“应该开 ticket 并给出 typed intent”，但还未把 intent 以幂等方式写成 `phase5_recovery_ticket` artifact。
- 下一步建议进入 Trial CH：新增 recovery ticket apply executor，输入只接受 `ready` intent，负责幂等写入和 CLI `attempt-run-recovery-ticket-apply`。
