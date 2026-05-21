# Trial CD 上下文包：Intervention Run Artifact

目标：为 `attempt-run-intervention-apply` 增加可选硬存储能力，记录本次介入执行 envelope，形成“读取 -> 计划 -> 执行 -> 结果记录”的闭环。

## 1. 范围

必须做：

- 新增 intervention run artifact model、store、recorder。
- 注册 `phase5_scheduler_attempt_intervention_run` artifact family 与 schema。
- CLI 增加 `--record-intervention-run` 和 `--intervention-run-id`。
- 默认 `attempt-run-intervention-apply` 行为不变，不记录 artifact。
- opt-in 记录时返回 envelope：`apply_result`、`intervention_run_artifact`、`intervention_run_record_status`、path。

不得做：

- 不改变 diagnostic 写入语义。
- 不创建 recovery ticket。
- 不写 execution ledger。
- 不修改 `process_hardening.py`。

## 2. 文件规模预算

- `src/ashare_evidence/scheduler_attempt_run_intervention_artifacts.py`：hard 180，warning 140。
- `src/ashare_evidence/scheduler_attempt_run_intervention_artifact_store.py`：hard 140，warning 110。
- `src/ashare_evidence/scheduler_attempt_run_intervention_recorder.py`：hard 180，warning 140。
- `src/ashare_evidence/cli_autonomous_flow_attempt_readout_outputs.py`：hard 180，warning 140。
- `src/ashare_evidence/cli_autonomous_flow.py`：hard 160，warning 135。
- `tests/test_scheduler_attempt_run_intervention_recorder.py`：hard 220，warning 180。
- `tests/test_cli_autonomous_flow_attempt_intervention_apply_output.py`：hard 260，warning 220。
- `docs/contracts/registry/schemas/phase5_scheduler_attempt_intervention_run.schema.json`：hard 180，warning 150。
- `docs/contracts/autonomous-flow-trial/TRIAL_CD_EVALUATION_CN.md`：hard 150，warning 120。

## 3. 验证命令

```bash
PYTHONPATH=src python3 -m pytest tests/test_scheduler_attempt_run_intervention_recorder.py tests/test_cli_autonomous_flow_attempt_intervention_apply_output.py -q
ruff check src/ashare_evidence/scheduler_attempt_run_intervention_artifacts.py src/ashare_evidence/scheduler_attempt_run_intervention_artifact_store.py src/ashare_evidence/scheduler_attempt_run_intervention_recorder.py src/ashare_evidence/cli_autonomous_flow_attempt_readout_outputs.py src/ashare_evidence/cli_autonomous_flow.py tests/test_scheduler_attempt_run_intervention_recorder.py tests/test_cli_autonomous_flow_attempt_intervention_apply_output.py
PYTHONPATH=src python3 -m pytest -q
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_CD_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/scheduler_attempt_run_intervention_artifacts.py:180:140 \
  --line-budget src/ashare_evidence/scheduler_attempt_run_intervention_artifact_store.py:140:110 \
  --line-budget src/ashare_evidence/scheduler_attempt_run_intervention_recorder.py:180:140 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_attempt_readout_outputs.py:180:140 \
  --line-budget src/ashare_evidence/cli_autonomous_flow.py:160:135 \
  --line-budget tests/test_scheduler_attempt_run_intervention_recorder.py:220:180 \
  --line-budget tests/test_cli_autonomous_flow_attempt_intervention_apply_output.py:260:220 \
  --line-budget docs/contracts/registry/schemas/phase5_scheduler_attempt_intervention_run.schema.json:180:150 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_CD_EVALUATION_CN.md:150:120 \
  --required-evidence tests/test_scheduler_attempt_run_intervention_recorder.py:test_record_intervention_run_artifact_writes_apply_result \
  --required-evidence tests/test_cli_autonomous_flow_attempt_intervention_apply_output.py:test_attempt_intervention_apply_output_records_intervention_run_when_enabled
```
