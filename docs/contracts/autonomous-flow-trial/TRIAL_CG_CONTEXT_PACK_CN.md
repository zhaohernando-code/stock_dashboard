# Trial CG 上下文包：Recovery Ticket Intent

目标：把 intervention follow-up decision 转换为 typed recovery ticket intent，为下一轮可控写入 `phase5_recovery_ticket` 做准备。本轮只做纯 intent 与只读 CLI 输出，不写 ticket。

## 1. 初始需求对齐

本轮继续推进“自运行介入机制”：

- 当 intervention diagnostic 已记录，系统不应停在建议文本，而应生成可执行票据意图。
- intent 必须显式列出 ticket_id、failed_step、failure_class、recovery_action、evidence_refs 等字段。
- 仍保持副作用隔离：intent 层不写 recovery ticket。

## 2. 本轮范围

必须做：

- 新增 recovery ticket intent 纯模块。
- CLI 新增 `attempt-run-recovery-ticket-intent` 只读输出。
- 缺少 cycle_id、diagnostic_id 或 observed_at 时返回 blocked intent。

不得做：

- 不调用 `record_phase5_recovery_ticket`。
- 不写 artifact。
- 不调用 scheduler handler。
- 不修改 `process_hardening.py`。

## 3. 文件规模预算

- `src/ashare_evidence/scheduler_attempt_run_recovery_ticket_intent.py`：hard 220，warning 180。
- `src/ashare_evidence/cli_autonomous_flow_attempt_intervention_outputs.py`：hard 260，warning 220。
- `src/ashare_evidence/cli_autonomous_flow.py`：hard 190，warning 160。
- `src/ashare_evidence/cli_autonomous_flow_output_dispatch.py`：hard 220，warning 180。
- `tests/test_scheduler_attempt_run_recovery_ticket_intent.py`：hard 240，warning 200。
- `tests/test_cli_autonomous_flow_attempt_recovery_ticket_intent_output.py`：hard 240，warning 200。
- `docs/contracts/autonomous-flow-trial/TRIAL_CG_EVALUATION_CN.md`：hard 150，warning 120。

## 4. 验证命令

```bash
PYTHONPATH=src python3 -m pytest tests/test_scheduler_attempt_run_recovery_ticket_intent.py tests/test_cli_autonomous_flow_attempt_recovery_ticket_intent_output.py -q
ruff check src/ashare_evidence/scheduler_attempt_run_recovery_ticket_intent.py src/ashare_evidence/cli_autonomous_flow_attempt_intervention_outputs.py src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_output_dispatch.py tests/test_scheduler_attempt_run_recovery_ticket_intent.py tests/test_cli_autonomous_flow_attempt_recovery_ticket_intent_output.py
PYTHONPATH=src python3 -m pytest -q
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_CG_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/scheduler_attempt_run_recovery_ticket_intent.py:220:180 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_attempt_intervention_outputs.py:260:220 \
  --line-budget src/ashare_evidence/cli_autonomous_flow.py:190:160 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_output_dispatch.py:220:180 \
  --line-budget tests/test_scheduler_attempt_run_recovery_ticket_intent.py:240:200 \
  --line-budget tests/test_cli_autonomous_flow_attempt_recovery_ticket_intent_output.py:240:200 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_CG_EVALUATION_CN.md:150:120 \
  --required-evidence tests/test_scheduler_attempt_run_recovery_ticket_intent.py:test_recovery_ticket_intent_ready_after_applied_diagnostic \
  --required-evidence tests/test_cli_autonomous_flow_attempt_recovery_ticket_intent_output.py:test_attempt_recovery_ticket_intent_output_builds_ready_intent_after_diagnostic \
  --forbidden-source-token src/ashare_evidence/scheduler_attempt_run_recovery_ticket_intent.py:record_phase5_recovery_ticket \
  --forbidden-source-token src/ashare_evidence/scheduler_attempt_run_recovery_ticket_intent.py:write_
```
