# Trial CC 上下文包：Attempt Run Intervention Apply

目标：把 CB 的只读 intervention plan 接到最小写入执行层，让 blocked attempt run 能无人值守地记录 scheduler diagnostic。本轮仍不创建 recovery ticket、不执行真实重建、不写 execution ledger。

## 1. 背景

CB 已经输出 `attempt-run-intervention-plan`，能区分 `observe_only`、`route_apply_required` 和 `blocked`。当前缺口是 plan 仍停留在意图层，不能自行把 blocked latest 变成可追踪的诊断 artifact。

本轮新增 attempt-run intervention apply executor：只支持 `scheduler_diagnostic` 写入；其他 side effect 保持 blocked 或 skipped。

## 2. 本轮范围

必须做：

- 新增 `scheduler_attempt_run_intervention_executor.py`。
- blocked latest + `route_apply_required` 自动生成稳定 diagnostic id，并用 latest issued_at 作为默认 observed_at。
- CLI 新增 `attempt-run-intervention-apply`，读取 attempt/run artifacts 后执行 apply。
- `observe_only` 不写 artifact，返回 skipped。
- 缺少 cycle_id 或 observed_at 时返回 typed blocked，不抛未结构化异常。

不得做：

- 不创建 recovery ticket。
- 不写 execution ledger。
- 不伪造 `Phase5SchedulerFollowupPlan`。
- 不调用 tick、scheduler action executor 或 route apply executor。
- 不修改 `process_hardening.py`。

## 3. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| CC1 | intervention executor、CLI apply output、tests、本评估文件 | 让 intervention plan 能安全记录 diagnostic |

## 4. 文件规模预算

- `src/ashare_evidence/scheduler_attempt_run_intervention_executor.py`：hard 220，warning 180。
- `src/ashare_evidence/scheduler_attempt_run_intervention_diagnostics.py`：hard 120，warning 90。
- `src/ashare_evidence/scheduler_attempt_run_intervention_plan.py`：hard 180，warning 140。
- `src/ashare_evidence/cli_autonomous_flow_attempt_readout_outputs.py`：hard 150，warning 120。
- `src/ashare_evidence/cli_autonomous_flow.py`：hard 150，warning 125。
- `src/ashare_evidence/cli_autonomous_flow_output_dispatch.py`：hard 180，warning 140。
- `tests/test_scheduler_attempt_run_intervention_executor.py`：hard 240，warning 200。
- `tests/test_cli_autonomous_flow_attempt_intervention_apply_output.py`：hard 240，warning 200。
- `docs/contracts/autonomous-flow-trial/TRIAL_CC_EVALUATION_CN.md`：hard 150，warning 120。

## 5. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_scheduler_attempt_run_intervention_executor.py tests/test_cli_autonomous_flow_attempt_intervention_apply_output.py tests/test_scheduler_attempt_run_intervention_plan.py tests/test_cli_autonomous_flow_attempt_intervention_plan_output.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/scheduler_attempt_run_intervention_executor.py src/ashare_evidence/scheduler_attempt_run_intervention_diagnostics.py src/ashare_evidence/scheduler_attempt_run_intervention_plan.py src/ashare_evidence/cli_autonomous_flow_attempt_readout_outputs.py src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_output_dispatch.py tests/test_scheduler_attempt_run_intervention_executor.py tests/test_cli_autonomous_flow_attempt_intervention_apply_output.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_CC_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/scheduler_attempt_run_intervention_executor.py:220:180 \
  --line-budget src/ashare_evidence/scheduler_attempt_run_intervention_diagnostics.py:120:90 \
  --line-budget src/ashare_evidence/scheduler_attempt_run_intervention_plan.py:180:140 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_attempt_readout_outputs.py:150:120 \
  --line-budget src/ashare_evidence/cli_autonomous_flow.py:150:125 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_output_dispatch.py:180:140 \
  --line-budget tests/test_scheduler_attempt_run_intervention_executor.py:240:200 \
  --line-budget tests/test_cli_autonomous_flow_attempt_intervention_apply_output.py:240:200 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_CC_EVALUATION_CN.md:150:120 \
  --required-evidence tests/test_scheduler_attempt_run_intervention_executor.py:test_intervention_apply_records_diagnostic_for_route_apply_plan \
  --required-evidence tests/test_cli_autonomous_flow_attempt_intervention_apply_output.py:test_attempt_intervention_apply_output_records_diagnostic_for_blocked_latest \
  --forbidden-source-token src/ashare_evidence/scheduler_attempt_run_intervention_executor.py:datetime.now \
  --forbidden-source-token src/ashare_evidence/scheduler_attempt_run_intervention_executor.py:random
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_CC_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_CC_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
