# Trial CO 上下文包：Workbench Projection Manifest

目标：把 cycle ledger、latest recovery ticket 与 auto-progress run readout 组合为只读 workbench projection manifest，作为 PC/mobile 工作台一屏状态输入。

## 1. 初始需求对齐

- 工作台需要一目了然看到 cycle 状态、恢复票、自动推进历史和下一步风险。
- 本轮先稳定前端输入 JSON，不写新 artifact，避免把 projection 生成和持久化耦合。
- projection 必须来自硬存储读取，不直接执行任务或推进状态。

## 2. 本轮范围

必须做：

- 新增 workbench projection manifest 纯模块。
- CLI 新增 `attempt-run-workbench-projection` 只读输出。
- 投影字段覆盖 cycle summary、recovery summary、auto-progress summary、source refs、missing refs、blocking reasons。
- cycle 缺失返回 degraded/blocked projection，不抛未结构化异常。
- 空 auto-progress history 仍返回可用 manifest，状态为 degraded。

不得做：

- 不写 artifact。
- 不调用 auto-progress apply。
- 不修改 `process_hardening.py`。

## 3. 文件规模预算

- `src/ashare_evidence/scheduler_workbench_projection.py`：hard 300，warning 250。
- `src/ashare_evidence/cli_autonomous_flow_workbench_outputs.py`：hard 160，warning 130。
- `src/ashare_evidence/cli_autonomous_flow.py`：hard 270，warning 240。
- `src/ashare_evidence/cli_autonomous_flow_output_dispatch.py`：hard 340，warning 300。
- `tests/test_scheduler_workbench_projection.py`：hard 300，warning 250。
- `tests/test_cli_autonomous_flow_workbench_projection_output.py`：hard 260，warning 220。
- `docs/contracts/autonomous-flow-trial/TRIAL_CO_EVALUATION_CN.md`：hard 150，warning 120。

## 4. 验证命令

```bash
PYTHONPATH=src python3 -m pytest tests/test_scheduler_workbench_projection.py tests/test_cli_autonomous_flow_workbench_projection_output.py -q
ruff check src/ashare_evidence/scheduler_workbench_projection.py src/ashare_evidence/cli_autonomous_flow_workbench_outputs.py src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_output_dispatch.py tests/test_scheduler_workbench_projection.py tests/test_cli_autonomous_flow_workbench_projection_output.py
PYTHONPATH=src python3 -m pytest -q
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_CO_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/scheduler_workbench_projection.py:300:250 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_workbench_outputs.py:160:130 \
  --line-budget src/ashare_evidence/cli_autonomous_flow.py:270:240 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_output_dispatch.py:340:300 \
  --line-budget tests/test_scheduler_workbench_projection.py:300:250 \
  --line-budget tests/test_cli_autonomous_flow_workbench_projection_output.py:260:220 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_CO_EVALUATION_CN.md:150:120 \
  --required-evidence tests/test_scheduler_workbench_projection.py:test_workbench_projection_combines_cycle_recovery_and_auto_progress \
  --required-evidence tests/test_cli_autonomous_flow_workbench_projection_output.py:test_workbench_projection_output_reads_projection_manifest \
  --forbidden-source-token src/ashare_evidence/scheduler_workbench_projection.py:apply_phase5 \
  --forbidden-source-token src/ashare_evidence/scheduler_workbench_projection.py:write_
```
