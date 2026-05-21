# Trial CI 评估记录：Recovery Follow-up Intent

状态：verified
输入：`TRIAL_CI_CONTEXT_PACK_CN.md`
目标：评估 recovery ticket 是否能稳定推导下一步 follow-up intent。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| CI1 | intent、CLI output、tests、本评估文件 | 生成 recovery follow-up intent | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 状态读取正确性 | 30 |
| follow-up intent 完整性 | 30 |
| 副作用隔离 | 20 |
| 验证完整性 | 20 |

自动重跑阈值：

- intent 模块调用 `start_phase5_cycle` 或写 artifact。
- ticket 缺失时抛未结构化异常。
- focused tests、ruff、process hardening 或 full regression 失败。

## 3. CI1 结果

- 新增 `Phase5SchedulerRecoveryFollowupIntent`，从 cycle ledger 的最新 `recovery_ticket_refs` 与 recovery ticket artifact 推导下一步动作。
- `recovery_action=open_followup_cycle` 会生成 `ready` intent，包含稳定 `followup_cycle_id`、`followup_trigger=recovery_followup`、`source_ticket_ref` 与去重后的 evidence refs。
- cycle 缺失返回 blocked；cycle 没有 ticket ref 返回 skipped；ticket ref 无法解析返回 blocked；非 follow-up action 返回 skipped。
- CLI 新增 `attempt-run-recovery-followup-intent`，只读状态并打印 intent；blocked 返回 exit code 4。
- 副作用隔离通过：intent 模块不调用 `start_phase5_cycle`，也不包含 `write_` 写入路径。

## 4. 主进程验证

- Focused tests：`PYTHONPATH=src python3 -m pytest tests/test_scheduler_recovery_followup_intent.py tests/test_cli_autonomous_flow_attempt_recovery_followup_intent_output.py -q`，结果 `8 passed`。
- Required evidence：`tests/test_scheduler_recovery_followup_intent.py:test_recovery_followup_intent_ready_for_open_followup_cycle`。
- Required evidence：`tests/test_cli_autonomous_flow_attempt_recovery_followup_intent_output.py:test_attempt_recovery_followup_intent_output_reads_latest_ticket`。
- Ruff：`ruff check src/ashare_evidence/scheduler_recovery_followup_intent.py src/ashare_evidence/cli_autonomous_flow_recovery_outputs.py src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_output_dispatch.py tests/test_scheduler_recovery_followup_intent.py tests/test_cli_autonomous_flow_attempt_recovery_followup_intent_output.py`，结果 `All checks passed!`。
- Contract registry：`contract-registry-check` 覆盖 CI context/evaluation docs，结果 `status=pass`、`issue_count=0`。
- Full regression：`PYTHONPATH=src python3 -m pytest -q`，结果 `599 passed, 147 deselected`。
- 文件规模：intent 131 行、CLI recovery outputs 21 行、dispatcher 128 行、主 CLI 126 行，均低于本轮 warning budget。

## 5. 重跑记录

- 无需重跑。focused tests、ruff、registry check 与 full regression 均一次通过。

## 6. 自评

- 本轮把 recovery ticket 的落盘结果推进成下一步 follow-up intent，继续符合“先决策后执行”的基座设计。
- 当前闭环仍差最后一步：`ready` follow-up intent 还没有被 apply 成新的 `phase5_cycle_ledger`。
- 下一步建议进入 Trial CJ：新增 recovery follow-up apply executor，输入 ready intent 后幂等创建 follow-up cycle。
