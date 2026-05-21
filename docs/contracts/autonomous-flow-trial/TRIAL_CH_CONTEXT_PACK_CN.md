# Trial CH 上下文包：Recovery Ticket Apply

目标：把 Trial CG 的 ready recovery ticket intent 幂等写入 `phase5_recovery_ticket`，补齐 intervention diagnostic 之后的自运行闭环。本轮允许写 ticket，但写入必须集中在 apply executor。

## 1. 初始需求对齐

- 自运行介入机制不能停在“建议开票”，必须能在无需人工确认时生成可追踪 recovery ticket。
- 状态管理必须硬存储：ticket artifact 与 cycle ledger ref 都要写入。
- 设计上保持基座边界：intent 仍纯净；apply executor 承担副作用。

## 2. 本轮范围

必须做：

- 新增 recovery ticket apply executor。
- CLI 新增 `attempt-run-recovery-ticket-apply` 写入出口。
- ready intent 写入 ticket，并追加 cycle ledger `recovery_ticket_refs`。
- 重复运行同一 intent 必须返回 `already_recorded`，不重复制造状态。
- cycle 缺失、intent blocked/skipped、已有 ticket 冲突时必须返回 blocked 或 skipped，不抛未结构化异常。

不得做：

- 不修改 intent builder 的纯函数边界。
- 不扩展 recovery ticket schema enum。
- 不修改 `process_hardening.py`。

## 3. 文件规模预算

- `src/ashare_evidence/scheduler_attempt_run_recovery_ticket_executor.py`：hard 260，warning 220。
- `src/ashare_evidence/cli_autonomous_flow_attempt_intervention_outputs.py`：hard 290，warning 250。
- `src/ashare_evidence/cli_autonomous_flow.py`：hard 200，warning 170。
- `src/ashare_evidence/cli_autonomous_flow_output_dispatch.py`：hard 230，warning 190。
- `tests/test_scheduler_attempt_run_recovery_ticket_executor.py`：hard 260，warning 220。
- `tests/test_cli_autonomous_flow_attempt_recovery_ticket_apply_output.py`：hard 260，warning 220。
- `docs/contracts/autonomous-flow-trial/TRIAL_CH_EVALUATION_CN.md`：hard 150，warning 120。

## 4. 验证命令

```bash
PYTHONPATH=src python3 -m pytest tests/test_scheduler_attempt_run_recovery_ticket_executor.py tests/test_cli_autonomous_flow_attempt_recovery_ticket_apply_output.py -q
ruff check src/ashare_evidence/scheduler_attempt_run_recovery_ticket_executor.py src/ashare_evidence/cli_autonomous_flow_attempt_intervention_outputs.py src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_output_dispatch.py tests/test_scheduler_attempt_run_recovery_ticket_executor.py tests/test_cli_autonomous_flow_attempt_recovery_ticket_apply_output.py
PYTHONPATH=src python3 -m pytest -q
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_CH_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/scheduler_attempt_run_recovery_ticket_executor.py:260:220 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_attempt_intervention_outputs.py:290:250 \
  --line-budget src/ashare_evidence/cli_autonomous_flow.py:200:170 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_output_dispatch.py:230:190 \
  --line-budget tests/test_scheduler_attempt_run_recovery_ticket_executor.py:260:220 \
  --line-budget tests/test_cli_autonomous_flow_attempt_recovery_ticket_apply_output.py:260:220 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_CH_EVALUATION_CN.md:150:120 \
  --required-evidence tests/test_scheduler_attempt_run_recovery_ticket_executor.py:test_recovery_ticket_apply_records_ready_intent \
  --required-evidence tests/test_cli_autonomous_flow_attempt_recovery_ticket_apply_output.py:test_attempt_recovery_ticket_apply_output_records_ticket \
  --forbidden-source-token src/ashare_evidence/scheduler_attempt_run_recovery_ticket_intent.py:record_phase5_recovery_ticket \
  --forbidden-source-token src/ashare_evidence/scheduler_attempt_run_recovery_ticket_intent.py:write_
```
