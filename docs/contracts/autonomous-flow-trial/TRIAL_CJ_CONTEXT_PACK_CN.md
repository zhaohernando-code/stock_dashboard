# Trial CJ 上下文包：Recovery Follow-up Apply

目标：把 ready recovery follow-up intent 幂等创建为新的 `phase5_cycle_ledger`，完成本轮自运行介入闭环。

## 1. 初始需求对齐

- 当 recovery ticket 要求打开 follow-up cycle 时，系统应能自动创建下一轮 cycle，而不是停在人工操作。
- 创建动作必须可重复运行且不制造重复状态。
- 时间输入必须显式：本轮使用 CLI `--created-at` 作为新 cycle 的 `started_at`，缺失时 blocked。

## 2. 本轮范围

必须做：

- 新增 recovery follow-up apply executor。
- CLI 新增 `attempt-run-recovery-followup-apply` 写入出口。
- ready intent 创建 follow-up cycle，scope 记录 source cycle/ticket/evidence。
- 重复运行同一 intent 返回 `already_started`。
- intent blocked/skipped、字段缺失、created_at 缺失、已有 cycle 冲突时返回结构化结果。

不得做：

- 不修改 recovery follow-up intent 的只读边界。
- 不启动任务执行器或 scheduler runner。
- 不修改 `process_hardening.py`。

## 3. 文件规模预算

- `src/ashare_evidence/scheduler_recovery_followup_executor.py`：hard 260，warning 220。
- `src/ashare_evidence/cli_autonomous_flow_recovery_outputs.py`：hard 240，warning 200。
- `src/ashare_evidence/cli_autonomous_flow.py`：hard 220，warning 190。
- `src/ashare_evidence/cli_autonomous_flow_output_dispatch.py`：hard 260，warning 220。
- `tests/test_scheduler_recovery_followup_executor.py`：hard 260，warning 220。
- `tests/test_cli_autonomous_flow_attempt_recovery_followup_apply_output.py`：hard 260，warning 220。
- `docs/contracts/autonomous-flow-trial/TRIAL_CJ_EVALUATION_CN.md`：hard 150，warning 120。

## 4. 验证命令

```bash
PYTHONPATH=src python3 -m pytest tests/test_scheduler_recovery_followup_executor.py tests/test_cli_autonomous_flow_attempt_recovery_followup_apply_output.py -q
ruff check src/ashare_evidence/scheduler_recovery_followup_executor.py src/ashare_evidence/cli_autonomous_flow_recovery_outputs.py src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_output_dispatch.py tests/test_scheduler_recovery_followup_executor.py tests/test_cli_autonomous_flow_attempt_recovery_followup_apply_output.py
PYTHONPATH=src python3 -m pytest -q
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_CJ_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/scheduler_recovery_followup_executor.py:260:220 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_recovery_outputs.py:240:200 \
  --line-budget src/ashare_evidence/cli_autonomous_flow.py:220:190 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_output_dispatch.py:260:220 \
  --line-budget tests/test_scheduler_recovery_followup_executor.py:260:220 \
  --line-budget tests/test_cli_autonomous_flow_attempt_recovery_followup_apply_output.py:260:220 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_CJ_EVALUATION_CN.md:150:120 \
  --required-evidence tests/test_scheduler_recovery_followup_executor.py:test_recovery_followup_apply_starts_ready_followup_cycle \
  --required-evidence tests/test_cli_autonomous_flow_attempt_recovery_followup_apply_output.py:test_attempt_recovery_followup_apply_output_starts_cycle \
  --forbidden-source-token src/ashare_evidence/scheduler_recovery_followup_intent.py:start_phase5_cycle \
  --forbidden-source-token src/ashare_evidence/scheduler_recovery_followup_intent.py:write_
```
