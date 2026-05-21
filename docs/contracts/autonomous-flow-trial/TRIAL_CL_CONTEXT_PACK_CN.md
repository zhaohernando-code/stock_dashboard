# Trial CL 上下文包：Auto Progress Apply

目标：在 auto-progress plan 之上实现受控 apply。每次只执行 planner 推荐的一步，并返回可审计 envelope，不做循环连跑。

## 1. 初始需求对齐

- 自运行机制需要减少人工调用多个 CLI 的负担。
- 为避免黑盒化，本轮只执行“一步”，不递归推进。
- 所有写入仍落在既有 executor/recorder，auto-progress apply 只做编排。

## 2. 本轮范围

必须做：

- 新增 auto-progress apply executor。
- CLI 新增 `attempt-run-auto-progress-apply`。
- 支持 `intervention_apply`、`recovery_ticket_apply`、`recovery_followup_apply` 三个 planner phase。
- blocked/idle plan 不执行写入，直接返回结构化结果。
- intervention apply 必须记录 intervention run artifact，保证后续 recovery ticket 阶段可读取。

不得做：

- 不做 while 循环或连续多步推进。
- 不绕过已有 executor/recorder 直接写底层 artifact。
- 不修改 `process_hardening.py`。

## 3. 文件规模预算

- `src/ashare_evidence/scheduler_auto_progress_executor.py`：hard 320，warning 270。
- `src/ashare_evidence/cli_autonomous_flow_auto_progress_outputs.py`：hard 220，warning 180。
- `src/ashare_evidence/cli_autonomous_flow.py`：hard 240，warning 210。
- `src/ashare_evidence/cli_autonomous_flow_output_dispatch.py`：hard 300，warning 260。
- `tests/test_scheduler_auto_progress_executor.py`：hard 320，warning 270。
- `tests/test_cli_autonomous_flow_auto_progress_apply_output.py`：hard 280，warning 240。
- `docs/contracts/autonomous-flow-trial/TRIAL_CL_EVALUATION_CN.md`：hard 150，warning 120。

## 4. 验证命令

```bash
PYTHONPATH=src python3 -m pytest tests/test_scheduler_auto_progress_executor.py tests/test_cli_autonomous_flow_auto_progress_apply_output.py -q
ruff check src/ashare_evidence/scheduler_auto_progress_executor.py src/ashare_evidence/cli_autonomous_flow_auto_progress_outputs.py src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_output_dispatch.py tests/test_scheduler_auto_progress_executor.py tests/test_cli_autonomous_flow_auto_progress_apply_output.py
PYTHONPATH=src python3 -m pytest -q
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_CL_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/scheduler_auto_progress_executor.py:320:270 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_auto_progress_outputs.py:220:180 \
  --line-budget src/ashare_evidence/cli_autonomous_flow.py:240:210 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_output_dispatch.py:300:260 \
  --line-budget tests/test_scheduler_auto_progress_executor.py:320:270 \
  --line-budget tests/test_cli_autonomous_flow_auto_progress_apply_output.py:280:240 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_CL_EVALUATION_CN.md:150:120 \
  --required-evidence tests/test_scheduler_auto_progress_executor.py:test_auto_progress_apply_records_intervention_run_for_blocked_attempt \
  --required-evidence tests/test_cli_autonomous_flow_auto_progress_apply_output.py:test_auto_progress_apply_output_starts_followup_cycle \
  --forbidden-source-token src/ashare_evidence/scheduler_auto_progress_executor.py:while \
  --forbidden-source-token src/ashare_evidence/scheduler_auto_progress_executor.py:write_phase5
```
