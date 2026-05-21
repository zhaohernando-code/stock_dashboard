# Trial CM 上下文包：Auto Progress Run Artifact

目标：为 `attempt-run-auto-progress-apply` 增加可选 run artifact 记录能力，让每次自动推进的 plan 与结果可被工作台读取和审计。

## 1. 初始需求对齐

- 中台需要展示自动推进历史，不能只依赖终端输出。
- 状态管理需要硬存储关键中间输入和最终输出。
- 本轮只记录 auto-progress run，不改变单步执行语义。

## 2. 本轮范围

必须做：

- 新增 `phase5_scheduler_auto_progress_run` artifact/model/store/recorder。
- CLI 增加 `--record-auto-progress-run` 与 `--auto-progress-run-id`。
- 记录内容包含 plan phase、plan status、apply status、applied output、recommended output、required/missing args、blocking reasons、evidence refs、result refs。
- 缺少 `issued_at` 或 `runner_id` 时，record envelope 返回 blocked，不写 artifact。

不得做：

- 不改变 auto-progress apply 的执行顺序。
- 不让 recorder 重新执行 apply。
- 不修改 `process_hardening.py`。

## 3. 文件规模预算

- `src/ashare_evidence/scheduler_auto_progress_artifacts.py`：hard 220，warning 180。
- `src/ashare_evidence/scheduler_auto_progress_artifact_store.py`：hard 180，warning 150。
- `src/ashare_evidence/scheduler_auto_progress_recorder.py`：hard 260，warning 220。
- `src/ashare_evidence/artifact_store_core.py`：hard 180，warning 150。
- `src/ashare_evidence/cli_autonomous_flow_auto_progress_outputs.py`：hard 280，warning 240。
- `src/ashare_evidence/cli_autonomous_flow.py`：hard 250，warning 220。
- `docs/contracts/registry/autonomous_flow_registry.v1.json`：hard 620，warning 580。
- `tests/test_scheduler_auto_progress_recorder.py`：hard 260，warning 220。
- `tests/test_cli_autonomous_flow_auto_progress_run_record_output.py`：hard 280，warning 240。
- `docs/contracts/autonomous-flow-trial/TRIAL_CM_EVALUATION_CN.md`：hard 150，warning 120。

## 4. 验证命令

```bash
PYTHONPATH=src python3 -m pytest tests/test_scheduler_auto_progress_recorder.py tests/test_cli_autonomous_flow_auto_progress_run_record_output.py -q
ruff check src/ashare_evidence/scheduler_auto_progress_artifacts.py src/ashare_evidence/scheduler_auto_progress_artifact_store.py src/ashare_evidence/scheduler_auto_progress_recorder.py src/ashare_evidence/artifact_store_core.py src/ashare_evidence/cli_autonomous_flow_auto_progress_outputs.py src/ashare_evidence/cli_autonomous_flow.py tests/test_scheduler_auto_progress_recorder.py tests/test_cli_autonomous_flow_auto_progress_run_record_output.py
PYTHONPATH=src python3 -m pytest -q
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_CM_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/scheduler_auto_progress_artifacts.py:220:180 \
  --line-budget src/ashare_evidence/scheduler_auto_progress_artifact_store.py:180:150 \
  --line-budget src/ashare_evidence/scheduler_auto_progress_recorder.py:260:220 \
  --line-budget src/ashare_evidence/artifact_store_core.py:180:150 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_auto_progress_outputs.py:280:240 \
  --line-budget src/ashare_evidence/cli_autonomous_flow.py:250:220 \
  --line-budget docs/contracts/registry/autonomous_flow_registry.v1.json:620:580 \
  --line-budget tests/test_scheduler_auto_progress_recorder.py:260:220 \
  --line-budget tests/test_cli_autonomous_flow_auto_progress_run_record_output.py:280:240 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_CM_EVALUATION_CN.md:150:120 \
  --required-evidence tests/test_scheduler_auto_progress_recorder.py:test_auto_progress_recorder_writes_run_artifact \
  --required-evidence tests/test_cli_autonomous_flow_auto_progress_run_record_output.py:test_auto_progress_apply_output_records_run_when_enabled \
  --forbidden-source-token src/ashare_evidence/scheduler_auto_progress_recorder.py:apply_phase5 \
  --forbidden-source-token src/ashare_evidence/scheduler_auto_progress_recorder.py:start_phase5_cycle
```
