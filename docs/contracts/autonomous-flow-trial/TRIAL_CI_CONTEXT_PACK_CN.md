# Trial CI 上下文包：Recovery Follow-up Intent

目标：从已写入的 recovery ticket 推导下一步 follow-up intent，为后续自动创建 follow-up cycle 做准备。本轮只读 cycle 与 ticket，不创建新 cycle。

## 1. 初始需求对齐

- 自运行机制需要把“错误已开票”继续推进到“下一步任务意图”。
- 状态读取必须来自硬存储：以 cycle ledger 的 `recovery_ticket_refs` 和 recovery ticket artifact 为准。
- 继续保持两段式：本轮只产 intent，下一轮再 apply。

## 2. 本轮范围

必须做：

- 新增 recovery follow-up intent 纯模块。
- CLI 新增 `attempt-run-recovery-followup-intent` 只读输出。
- 对 `open_followup_cycle` 生成稳定 `followup_cycle_id`。
- cycle 缺失、ticket ref 缺失、ticket artifact 缺失时返回结构化 blocked/skipped。

不得做：

- 不调用 `start_phase5_cycle`。
- 不写任何 artifact。
- 不修改 `process_hardening.py`。

## 3. 文件规模预算

- `src/ashare_evidence/scheduler_recovery_followup_intent.py`：hard 240，warning 200。
- `src/ashare_evidence/cli_autonomous_flow_recovery_outputs.py`：hard 180，warning 150。
- `src/ashare_evidence/cli_autonomous_flow.py`：hard 210，warning 180。
- `src/ashare_evidence/cli_autonomous_flow_output_dispatch.py`：hard 240，warning 200。
- `tests/test_scheduler_recovery_followup_intent.py`：hard 240，warning 200。
- `tests/test_cli_autonomous_flow_attempt_recovery_followup_intent_output.py`：hard 220，warning 190。
- `docs/contracts/autonomous-flow-trial/TRIAL_CI_EVALUATION_CN.md`：hard 150，warning 120。

## 4. 验证命令

```bash
PYTHONPATH=src python3 -m pytest tests/test_scheduler_recovery_followup_intent.py tests/test_cli_autonomous_flow_attempt_recovery_followup_intent_output.py -q
ruff check src/ashare_evidence/scheduler_recovery_followup_intent.py src/ashare_evidence/cli_autonomous_flow_recovery_outputs.py src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_output_dispatch.py tests/test_scheduler_recovery_followup_intent.py tests/test_cli_autonomous_flow_attempt_recovery_followup_intent_output.py
PYTHONPATH=src python3 -m pytest -q
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_CI_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/scheduler_recovery_followup_intent.py:240:200 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_recovery_outputs.py:180:150 \
  --line-budget src/ashare_evidence/cli_autonomous_flow.py:210:180 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_output_dispatch.py:240:200 \
  --line-budget tests/test_scheduler_recovery_followup_intent.py:240:200 \
  --line-budget tests/test_cli_autonomous_flow_attempt_recovery_followup_intent_output.py:220:190 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_CI_EVALUATION_CN.md:150:120 \
  --required-evidence tests/test_scheduler_recovery_followup_intent.py:test_recovery_followup_intent_ready_for_open_followup_cycle \
  --required-evidence tests/test_cli_autonomous_flow_attempt_recovery_followup_intent_output.py:test_attempt_recovery_followup_intent_output_reads_latest_ticket \
  --forbidden-source-token src/ashare_evidence/scheduler_recovery_followup_intent.py:start_phase5_cycle \
  --forbidden-source-token src/ashare_evidence/scheduler_recovery_followup_intent.py:write_
```
