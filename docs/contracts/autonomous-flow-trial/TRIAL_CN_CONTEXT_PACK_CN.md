# Trial CN 上下文包：Auto Progress Run Readout

目标：为 `phase5_scheduler_auto_progress_run` 增加 readout，按 cycle/runner 汇总最近自动推进历史，作为后续 PC/mobile 工作台 projection 输入。

## 1. 初始需求对齐

- 工作台需要一目了然看到自动推进状态，而不是只看单个 artifact。
- 状态读取必须来自硬存储的 auto-progress run artifact。
- 本轮只读汇总，不执行 apply，不写 artifact。

## 2. 本轮范围

必须做：

- 新增 auto-progress run query/list。
- 新增 auto-progress run readout 聚合模型。
- CLI 新增 `attempt-run-auto-progress-readout` 只读输出。
- 聚合字段包含 total_runs、latest run、phase/apply/applied output、applied/blocked/idle counts、latest refs、result refs。
- 空 store 返回 degraded readout，不创建目录。

不得做：

- 不调用 auto-progress apply。
- 不写 artifact。
- 不修改 `process_hardening.py`。

## 3. 文件规模预算

- `src/ashare_evidence/scheduler_auto_progress_artifact_queries.py`：hard 180，warning 150。
- `src/ashare_evidence/scheduler_auto_progress_readout.py`：hard 240，warning 200。
- `src/ashare_evidence/scheduler_auto_progress_artifact_store.py`：hard 220，warning 180。
- `src/ashare_evidence/cli_autonomous_flow_auto_progress_outputs.py`：hard 320，warning 270。
- `src/ashare_evidence/cli_autonomous_flow.py`：hard 260，warning 230。
- `src/ashare_evidence/cli_autonomous_flow_output_dispatch.py`：hard 320，warning 280。
- `tests/test_scheduler_auto_progress_readout.py`：hard 260，warning 220。
- `tests/test_cli_autonomous_flow_auto_progress_readout_output.py`：hard 240，warning 200。
- `docs/contracts/autonomous-flow-trial/TRIAL_CN_EVALUATION_CN.md`：hard 150，warning 120。

## 4. 验证命令

```bash
PYTHONPATH=src python3 -m pytest tests/test_scheduler_auto_progress_readout.py tests/test_cli_autonomous_flow_auto_progress_readout_output.py -q
ruff check src/ashare_evidence/scheduler_auto_progress_artifact_queries.py src/ashare_evidence/scheduler_auto_progress_readout.py src/ashare_evidence/scheduler_auto_progress_artifact_store.py src/ashare_evidence/cli_autonomous_flow_auto_progress_outputs.py src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_output_dispatch.py tests/test_scheduler_auto_progress_readout.py tests/test_cli_autonomous_flow_auto_progress_readout_output.py
PYTHONPATH=src python3 -m pytest -q
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_CN_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/scheduler_auto_progress_artifact_queries.py:180:150 \
  --line-budget src/ashare_evidence/scheduler_auto_progress_readout.py:240:200 \
  --line-budget src/ashare_evidence/scheduler_auto_progress_artifact_store.py:220:180 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_auto_progress_outputs.py:320:270 \
  --line-budget src/ashare_evidence/cli_autonomous_flow.py:260:230 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_output_dispatch.py:320:280 \
  --line-budget tests/test_scheduler_auto_progress_readout.py:260:220 \
  --line-budget tests/test_cli_autonomous_flow_auto_progress_readout_output.py:240:200 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_CN_EVALUATION_CN.md:150:120 \
  --required-evidence tests/test_scheduler_auto_progress_readout.py:test_auto_progress_readout_summarizes_latest_run \
  --required-evidence tests/test_cli_autonomous_flow_auto_progress_readout_output.py:test_auto_progress_readout_output_reads_recorded_runs \
  --forbidden-source-token src/ashare_evidence/scheduler_auto_progress_readout.py:apply_phase5 \
  --forbidden-source-token src/ashare_evidence/scheduler_auto_progress_readout.py:write_
```
