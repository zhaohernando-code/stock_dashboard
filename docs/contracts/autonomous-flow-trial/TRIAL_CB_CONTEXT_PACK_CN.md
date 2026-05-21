# Trial CB 上下文包：Attempt Run Intervention Plan

目标：把 `attempt-run-followup-decision` 推进为可执行的自运行介入计划，但本轮不直接写恢复票、不写 execution ledger、不触发 scheduler side effect。

## 1. 背景

BY/BZ 已经让系统能从 attempt/run artifact 中读出最新状态，并输出 typed follow-up decision。当前缺口是：decision 仍只是策略判断，后续 agent 需要自行解释“下一步怎么做”，容易在无人值守流程里跑偏。

本轮新增 attempt-run 专属 intervention plan，明确下一步是继续观察、记录恢复诊断、还是阻断 cycle。该 plan 必须保持纯函数、无 IO、无时钟、无随机，并与 tick 派生的 `Phase5SchedulerFollowupPlan` 保持边界。

## 2. 本轮范围

必须做：

- 新增 attempt-run intervention plan 纯模块。
- 明确 decision/readout 到 intervention plan 的转换规则。
- 新增 CLI 只读输出 `attempt-run-intervention-plan`，读取 artifact 后输出 intervention plan。
- intervention plan 必须区分计划阶段缺失参数和下一阶段 route apply 参数：`diagnostic_id/observed_at` 可出现在 `required_arguments`，但不得在计划阶段导致 blocked。
- 保持 `attempt-run-followup-decision` 原有输出不变。
- focused tests 覆盖 blocked、empty/applied、unknown 三类路径。

不得做：

- 不写恢复票、不写 execution ledger、不记录新的 attempt/run artifact。
- 不复用或伪造 tick 派生的 `Phase5SchedulerFollowupPlan`。
- 不改 artifact schema。
- 不修改 `process_hardening.py`。

## 3. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| CB1 | intervention plan module、CLI output、tests、本评估文件 | 将 attempt-run decision 固化为可执行计划 |

## 4. 文件规模预算

- `src/ashare_evidence/scheduler_attempt_run_intervention_plan.py`：hard 180，warning 140。
- `src/ashare_evidence/cli_autonomous_flow_attempt_readout_outputs.py`：hard 120，warning 90。
- `src/ashare_evidence/cli_autonomous_flow.py`：hard 150，warning 125。
- `src/ashare_evidence/cli_autonomous_flow_output_dispatch.py`：hard 180，warning 140。
- `tests/test_scheduler_attempt_run_intervention_plan.py`：hard 220，warning 180。
- `tests/test_cli_autonomous_flow_attempt_intervention_plan_output.py`：hard 220，warning 180。
- `docs/contracts/autonomous-flow-trial/TRIAL_CB_EVALUATION_CN.md`：hard 150，warning 120。

## 5. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_scheduler_attempt_run_intervention_plan.py tests/test_cli_autonomous_flow_attempt_intervention_plan_output.py tests/test_cli_autonomous_flow_attempt_followup_decision_output.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/scheduler_attempt_run_intervention_plan.py src/ashare_evidence/cli_autonomous_flow_attempt_readout_outputs.py src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_output_dispatch.py tests/test_scheduler_attempt_run_intervention_plan.py tests/test_cli_autonomous_flow_attempt_intervention_plan_output.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_CB_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/scheduler_attempt_run_intervention_plan.py:180:140 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_attempt_readout_outputs.py:120:90 \
  --line-budget src/ashare_evidence/cli_autonomous_flow.py:150:125 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_output_dispatch.py:180:140 \
  --line-budget tests/test_scheduler_attempt_run_intervention_plan.py:220:180 \
  --line-budget tests/test_cli_autonomous_flow_attempt_intervention_plan_output.py:220:180 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_CB_EVALUATION_CN.md:150:120 \
  --required-evidence tests/test_scheduler_attempt_run_intervention_plan.py:test_intervention_plan_records_recovery_diagnostic_for_blocked_latest \
  --required-evidence tests/test_cli_autonomous_flow_attempt_intervention_plan_output.py:test_attempt_intervention_plan_output_recommends_recovery_diagnostic_for_blocked_latest \
  --forbidden-source-token src/ashare_evidence/scheduler_attempt_run_intervention_plan.py:datetime \
  --forbidden-source-token src/ashare_evidence/scheduler_attempt_run_intervention_plan.py:random \
  --forbidden-source-token src/ashare_evidence/scheduler_attempt_run_intervention_plan.py:write_
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_CB_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_CB_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
