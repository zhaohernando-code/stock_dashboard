# Trial CE 上下文包：Intervention Run Readout

目标：为 `phase5_scheduler_attempt_intervention_run` 增加查询与 readout，让调度器、reviewer 和未来中台不需要扫描原始 JSON。

## 1. 对齐初始需求

本轮不扩大执行能力，只补读取层：

- 面向中台：提供聚合状态、latest run、applied/blocked/skipped 计数。
- 面向自运行：让下一步调度能基于 typed readout 判断是否继续、重试或升级。
- 面向硬状态：所有判断来自 artifact typed fields，不解析 reason 文本。

## 2. 本轮范围

必须做：

- 新增 intervention run query helper。
- 新增 intervention run readout model 与 builder。
- CLI 新增 `attempt-run-intervention-readout` 只读输出。
- 支持按 `cycle_id`、`runner_id`、`execution_status` 查询。

不得做：

- 不写 artifact。
- 不改 intervention apply 默认行为。
- 不创建 recovery ticket。
- 不修改 `process_hardening.py`。

## 3. 文件规模预算

- `src/ashare_evidence/scheduler_attempt_run_intervention_artifact_queries.py`：hard 160，warning 120。
- `src/ashare_evidence/scheduler_attempt_run_intervention_artifact_store.py`：hard 160，warning 120。
- `src/ashare_evidence/scheduler_attempt_run_intervention_readout.py`：hard 180，warning 140。
- `src/ashare_evidence/cli_autonomous_flow_attempt_intervention_outputs.py`：hard 180，warning 140。
- `src/ashare_evidence/cli_autonomous_flow_attempt_readout_outputs.py`：hard 180，warning 140。
- `src/ashare_evidence/cli_autonomous_flow.py`：hard 170，warning 145。
- `src/ashare_evidence/cli_autonomous_flow_output_dispatch.py`：hard 190，warning 150。
- `tests/test_scheduler_attempt_run_intervention_artifact_store.py`：hard 220，warning 180。
- `tests/test_scheduler_attempt_run_intervention_readout.py`：hard 220，warning 180。
- `tests/test_cli_autonomous_flow_attempt_intervention_readout_output.py`：hard 220，warning 180。
- `docs/contracts/autonomous-flow-trial/TRIAL_CE_EVALUATION_CN.md`：hard 150，warning 120。

## 4. 验证命令

```bash
PYTHONPATH=src python3 -m pytest tests/test_scheduler_attempt_run_intervention_artifact_store.py tests/test_scheduler_attempt_run_intervention_readout.py tests/test_cli_autonomous_flow_attempt_intervention_readout_output.py -q
ruff check src/ashare_evidence/scheduler_attempt_run_intervention_artifact_queries.py src/ashare_evidence/scheduler_attempt_run_intervention_artifact_store.py src/ashare_evidence/scheduler_attempt_run_intervention_readout.py src/ashare_evidence/cli_autonomous_flow_attempt_intervention_outputs.py src/ashare_evidence/cli_autonomous_flow_attempt_readout_outputs.py src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_output_dispatch.py tests/test_scheduler_attempt_run_intervention_artifact_store.py tests/test_scheduler_attempt_run_intervention_readout.py tests/test_cli_autonomous_flow_attempt_intervention_readout_output.py
PYTHONPATH=src python3 -m pytest -q
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_CE_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/scheduler_attempt_run_intervention_artifact_queries.py:160:120 \
  --line-budget src/ashare_evidence/scheduler_attempt_run_intervention_artifact_store.py:160:120 \
  --line-budget src/ashare_evidence/scheduler_attempt_run_intervention_readout.py:180:140 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_attempt_intervention_outputs.py:180:140 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_attempt_readout_outputs.py:180:140 \
  --line-budget src/ashare_evidence/cli_autonomous_flow.py:170:145 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_output_dispatch.py:190:150 \
  --line-budget tests/test_scheduler_attempt_run_intervention_artifact_store.py:220:180 \
  --line-budget tests/test_scheduler_attempt_run_intervention_readout.py:220:180 \
  --line-budget tests/test_cli_autonomous_flow_attempt_intervention_readout_output.py:220:180 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_CE_EVALUATION_CN.md:150:120 \
  --required-evidence tests/test_scheduler_attempt_run_intervention_readout.py:test_build_intervention_run_readout_summarizes_mixed_runs \
  --required-evidence tests/test_cli_autonomous_flow_attempt_intervention_readout_output.py:test_attempt_intervention_readout_output_reads_recorded_runs_without_scheduler_handlers
```
