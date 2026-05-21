# Trial CF 上下文包：Intervention Follow-up Policy

目标：基于 intervention run readout 生成 typed follow-up decision，判断介入执行后下一步是继续观察、重试介入、还是进入恢复票创建阶段。本轮只做纯策略和只读 CLI 输出，不执行副作用。

## 1. 初始需求对齐

本轮服务“自运行介入机制”和“任务调度下一步自动开启”：

- intervention diagnostic 已成功记录时，系统应能进入下一阶段恢复票创建决策，而不是停住等人读 JSON。
- intervention apply blocked 时，系统应能明确建议重试，而不是无结构地卡住。
- 所有判断只读 typed readout 字段，不解析 reason。

## 2. 本轮范围

必须做：

- 新增 intervention follow-up policy 纯模块。
- CLI 新增 `attempt-run-intervention-followup-decision` 只读输出。
- 覆盖 empty、latest applied diagnostic、latest blocked、latest skipped。

不得做：

- 不创建 recovery ticket。
- 不写 artifact。
- 不调用 scheduler handler。
- 不修改 `process_hardening.py`。

## 3. 文件规模预算

- `src/ashare_evidence/scheduler_attempt_run_intervention_followup_policy.py`：hard 180，warning 140。
- `src/ashare_evidence/cli_autonomous_flow_attempt_intervention_outputs.py`：hard 220，warning 180。
- `src/ashare_evidence/cli_autonomous_flow.py`：hard 180，warning 150。
- `src/ashare_evidence/cli_autonomous_flow_output_dispatch.py`：hard 200，warning 160。
- `tests/test_scheduler_attempt_run_intervention_followup_policy.py`：hard 220，warning 180。
- `tests/test_cli_autonomous_flow_attempt_intervention_followup_decision_output.py`：hard 220，warning 180。
- `docs/contracts/autonomous-flow-trial/TRIAL_CF_EVALUATION_CN.md`：hard 150，warning 120。

## 4. 验证命令

```bash
PYTHONPATH=src python3 -m pytest tests/test_scheduler_attempt_run_intervention_followup_policy.py tests/test_cli_autonomous_flow_attempt_intervention_followup_decision_output.py -q
ruff check src/ashare_evidence/scheduler_attempt_run_intervention_followup_policy.py src/ashare_evidence/cli_autonomous_flow_attempt_intervention_outputs.py src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_output_dispatch.py tests/test_scheduler_attempt_run_intervention_followup_policy.py tests/test_cli_autonomous_flow_attempt_intervention_followup_decision_output.py
PYTHONPATH=src python3 -m pytest -q
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_CF_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/scheduler_attempt_run_intervention_followup_policy.py:180:140 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_attempt_intervention_outputs.py:220:180 \
  --line-budget src/ashare_evidence/cli_autonomous_flow.py:180:150 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_output_dispatch.py:200:160 \
  --line-budget tests/test_scheduler_attempt_run_intervention_followup_policy.py:220:180 \
  --line-budget tests/test_cli_autonomous_flow_attempt_intervention_followup_decision_output.py:220:180 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_CF_EVALUATION_CN.md:150:120 \
  --required-evidence tests/test_scheduler_attempt_run_intervention_followup_policy.py:test_intervention_followup_recommends_recovery_ticket_after_applied_diagnostic \
  --required-evidence tests/test_cli_autonomous_flow_attempt_intervention_followup_decision_output.py:test_attempt_intervention_followup_decision_output_recommends_recovery_ticket_after_diagnostic
```
