# Trial CK 上下文包：Auto Progress Plan

目标：把已经拆开的 attempt/intervention/recovery CLI 串成一个只读 auto-progress plan，让系统能判断下一步该执行什么，而不是依赖人工在多个输出之间切换。

## 1. 初始需求对齐

- 自运行机制需要“下一步推荐”，不能每轮都靠人工决定调用哪个 CLI。
- 当前仍保持保守：本轮只读、只出 plan，不自动执行写入。
- plan 必须显式说明 recommended output、required arguments、missing arguments、blocking reasons 与 evidence refs。

## 2. 本轮范围

必须做：

- 新增 auto-progress plan 纯模块。
- CLI 新增 `attempt-run-auto-progress-plan` 只读输出。
- 优先级：follow-up apply > recovery ticket apply > intervention apply > wait。
- 对 follow-up apply 要求 `created_at`，对 intervention apply record 要求 `issued_at` 与 `runner_id`。
- 缺参数时返回 blocked plan，不执行任何写入。

不得做：

- 不调用任何 apply executor。
- 不写 artifact。
- 不启动 scheduler runner。
- 不修改 `process_hardening.py`。

## 3. 文件规模预算

- `src/ashare_evidence/scheduler_auto_progress_plan.py`：hard 300，warning 250。
- `src/ashare_evidence/cli_autonomous_flow_auto_progress_outputs.py`：hard 160，warning 130。
- `src/ashare_evidence/cli_autonomous_flow.py`：hard 230，warning 200。
- `src/ashare_evidence/cli_autonomous_flow_output_dispatch.py`：hard 280，warning 240。
- `tests/test_scheduler_auto_progress_plan.py`：hard 300，warning 250。
- `tests/test_cli_autonomous_flow_auto_progress_plan_output.py`：hard 260，warning 220。
- `docs/contracts/autonomous-flow-trial/TRIAL_CK_EVALUATION_CN.md`：hard 150，warning 120。

## 4. 验证命令

```bash
PYTHONPATH=src python3 -m pytest tests/test_scheduler_auto_progress_plan.py tests/test_cli_autonomous_flow_auto_progress_plan_output.py -q
ruff check src/ashare_evidence/scheduler_auto_progress_plan.py src/ashare_evidence/cli_autonomous_flow_auto_progress_outputs.py src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_output_dispatch.py tests/test_scheduler_auto_progress_plan.py tests/test_cli_autonomous_flow_auto_progress_plan_output.py
PYTHONPATH=src python3 -m pytest -q
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_CK_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/scheduler_auto_progress_plan.py:300:250 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_auto_progress_outputs.py:160:130 \
  --line-budget src/ashare_evidence/cli_autonomous_flow.py:230:200 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_output_dispatch.py:280:240 \
  --line-budget tests/test_scheduler_auto_progress_plan.py:300:250 \
  --line-budget tests/test_cli_autonomous_flow_auto_progress_plan_output.py:260:220 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_CK_EVALUATION_CN.md:150:120 \
  --required-evidence tests/test_scheduler_auto_progress_plan.py:test_auto_progress_plan_recommends_intervention_apply_for_blocked_attempt \
  --required-evidence tests/test_cli_autonomous_flow_auto_progress_plan_output.py:test_auto_progress_plan_output_recommends_recovery_followup_apply \
  --forbidden-source-token src/ashare_evidence/scheduler_auto_progress_plan.py:apply_phase5 \
  --forbidden-source-token src/ashare_evidence/scheduler_auto_progress_plan.py:write_
```
