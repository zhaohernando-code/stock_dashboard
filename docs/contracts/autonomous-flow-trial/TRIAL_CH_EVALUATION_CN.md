# Trial CH 评估记录：Recovery Ticket Apply

状态：verified
输入：`TRIAL_CH_CONTEXT_PACK_CN.md`
目标：评估 ready recovery ticket intent 是否能被幂等写入为 recovery ticket artifact。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| CH1 | executor、CLI output、tests、本评估文件 | 幂等写入 recovery ticket | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 写入正确性 | 35 |
| 幂等性 | 25 |
| 异常结构化 | 20 |
| 验证完整性 | 20 |

自动重跑阈值：

- intent 模块新增写入副作用。
- 重复 apply 产生重复 ticket ref 或冲突覆盖。
- focused tests、ruff、process hardening 或 full regression 失败。

## 3. CH1 结果

- 新增 `apply_phase5_scheduler_recovery_ticket_intent` executor，作为唯一新增写入边界。
- `ready` intent 会写入 `phase5_recovery_ticket`，并通过既有 `record_phase5_recovery_ticket` 追加 cycle ledger `recovery_ticket_refs`。
- 重复 apply 同一 intent 返回 `already_recorded`，不会重复追加 ticket ref 或重复 recorded event。
- `skipped` intent 返回 `skipped`，blocked intent、缺少 ready 字段、cycle ledger 缺失、已有 ticket 内容冲突均返回结构化 `blocked`。
- CLI 新增 `attempt-run-recovery-ticket-apply`，从 intervention run readout 构造 intent 后执行 apply；blocked 返回 exit code 4。

## 4. 主进程验证

- Focused tests：`PYTHONPATH=src python3 -m pytest tests/test_scheduler_attempt_run_recovery_ticket_executor.py tests/test_cli_autonomous_flow_attempt_recovery_ticket_apply_output.py -q`，结果 `8 passed`。
- Required evidence：`tests/test_scheduler_attempt_run_recovery_ticket_executor.py:test_recovery_ticket_apply_records_ready_intent`。
- Required evidence：`tests/test_cli_autonomous_flow_attempt_recovery_ticket_apply_output.py:test_attempt_recovery_ticket_apply_output_records_ticket`。
- Ruff 初次发现测试 import 排序问题，执行 `ruff check --fix tests/test_scheduler_attempt_run_recovery_ticket_executor.py` 后复检通过。
- Ruff：`ruff check src/ashare_evidence/scheduler_attempt_run_recovery_ticket_executor.py src/ashare_evidence/cli_autonomous_flow_attempt_intervention_outputs.py src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_output_dispatch.py tests/test_scheduler_attempt_run_recovery_ticket_executor.py tests/test_cli_autonomous_flow_attempt_recovery_ticket_apply_output.py`，结果 `All checks passed!`。
- Contract registry：`contract-registry-check` 覆盖 CH context/evaluation docs，结果 `status=pass`、`issue_count=0`。
- Full regression：`PYTHONPATH=src python3 -m pytest -q`，结果 `591 passed, 147 deselected`。
- 文件规模：executor 162 行、CLI intervention outputs 165 行、dispatcher 122 行、主 CLI 124 行，均低于本轮 warning budget。

## 5. 重跑记录

- 仅因 import 排序执行一次机械修复；无语义重跑。

## 6. 自评

- 本轮把自运行链路从“开票意图”推进到“可落盘 ticket”，符合初始需求中的自运行介入与硬存储。
- 设计边界保持清晰：intent/decision 层仍无写入副作用，写入集中在 executor，CLI 只做编排。
- 下一步建议进入 Trial CI：基于 recovery ticket apply result 生成下一步 follow-up action，例如创建 follow-up cycle 或进入 retry/backoff 队列。
