# Trial BW 上下文包：CLI Attempt Run Readout Output

目标：把 BV 的 attempt/run operations readout 暴露为 `phase5-local-cycle-step` 的只读 CLI 输出，供人工、调度器和后续中台快速查看当前运行状态。本轮不写 artifact，不改现有 apply 输出。

## 1. 背景

BV 已提供纯 readout builder 和 query convenience，但目前只能被 Python 代码调用。为了让自动化流程和中台调试能快速读取状态，需要一个 CLI 输出入口。

本轮只新增 `--output attempt-run-readout`。它读取 `phase5_scheduler_attempt_run` artifacts，按当前 `--cycle-id` 和可选 `--runner-id` 生成 readout JSON。该输出不执行 tick/plan/action，不写 artifact。

## 2. 本轮范围

必须做：

- `phase5-local-cycle-step --output` 新增 `attempt-run-readout`。
- 该输出调用 `read_phase5_scheduler_attempt_run_readout(cycle_id=args.cycle_id, runner_id=args.runner_id, root=args.artifact_root)`。
- 输出 readout JSON，exit code 为 0。
- 不调用 tick、plan、action、route、apply handlers。
- 新增独立 focused CLI 测试，覆盖有记录和空记录。

不得做：

- 不改变 `attempt-route-auto-apply` 默认输出或 opt-in recording。
- 不写任何 artifact。
- 不新增 registry artifact/event。
- 不修改 artifact schema。
- 不修改 `process_hardening.py`。

## 3. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| BW1 | CLI readout output、focused tests、本评估文件 | 暴露无副作用的 attempt/run readout CLI |

## 4. 文件规模预算

- `src/ashare_evidence/cli_autonomous_flow.py`：hard 140，warning 125。
- `src/ashare_evidence/cli_autonomous_flow_outputs.py`：hard 160，warning 140。
- `src/ashare_evidence/cli_autonomous_flow_attempt_outputs.py`：hard 150，warning 120。
- `tests/test_cli_autonomous_flow_attempt_run_readout_output.py`：hard 220，warning 180。
- `docs/contracts/autonomous-flow-trial/TRIAL_BW_EVALUATION_CN.md`：hard 150，warning 120。

## 5. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_attempt_run_readout_output.py tests/test_scheduler_attempt_run_readout.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_outputs.py src/ashare_evidence/cli_autonomous_flow_attempt_outputs.py tests/test_cli_autonomous_flow_attempt_run_readout_output.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_BW_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/cli_autonomous_flow.py:140:125 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_outputs.py:160:140 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_attempt_outputs.py:150:120 \
  --line-budget tests/test_cli_autonomous_flow_attempt_run_readout_output.py:220:180 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_BW_EVALUATION_CN.md:150:120 \
  --required-evidence tests/test_cli_autonomous_flow_attempt_run_readout_output.py:test_attempt_run_readout_output_reads_artifacts_without_running_scheduler \
  --required-evidence tests/test_cli_autonomous_flow_attempt_run_readout_output.py:test_attempt_run_readout_output_handles_empty_store \
  --forbidden-source-token src/ashare_evidence/cli_autonomous_flow_attempt_outputs.py:datetime.now \
  --forbidden-source-token src/ashare_evidence/cli_autonomous_flow_attempt_outputs.py:uuid \
  --forbidden-source-token src/ashare_evidence/cli_autonomous_flow_attempt_outputs.py:random
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BW_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BW_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
