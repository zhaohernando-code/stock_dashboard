# Trial BX 上下文包：CLI Attempt Output Split

目标：把 `attempt-run-readout` handler 从 `cli_autonomous_flow_attempt_outputs.py` 拆到独立模块，降低 attempt output 文件的增长风险。本轮不改变 CLI 行为。

## 1. 背景

BW 后 `cli_autonomous_flow_attempt_outputs.py` 达到 114 行，距离 warning 120 只剩 6 行。该文件已经承载 attempt context、attempt route apply、recording envelope、readout output，继续堆叠会变成新的基座热点。

本轮只做模块拆分：readout handler 迁移到 `cli_autonomous_flow_attempt_readout_outputs.py`，dispatcher import 新模块；focused tests 行为不变。

## 2. 本轮范围

必须做：

- 新增 `cli_autonomous_flow_attempt_readout_outputs.py`。
- 从 `cli_autonomous_flow_attempt_outputs.py` 移出 `handle_attempt_run_readout_output`。
- `cli_autonomous_flow_outputs.py` 改为从新模块 import readout handler。
- 保持 `attempt-run-readout` CLI 行为、输出和 exit code 不变。
- 文件预算要求 attempt outputs 恢复至少 20 行 warning margin。

不得做：

- 不改 CLI 参数或 output choices。
- 不改 readout model。
- 不改 artifact schema。
- 不修改 `process_hardening.py`。

## 3. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| BX1 | CLI attempt readout split、focused tests、本评估文件 | 保持行为不变并降低 attempt output 文件增长风险 |

## 4. 文件规模预算

- `src/ashare_evidence/cli_autonomous_flow_attempt_outputs.py`：hard 150，warning 120，warning margin minimum 20。
- `src/ashare_evidence/cli_autonomous_flow_attempt_readout_outputs.py`：hard 120，warning 90。
- `src/ashare_evidence/cli_autonomous_flow_outputs.py`：hard 160，warning 140。
- `tests/test_cli_autonomous_flow_attempt_run_readout_output.py`：hard 220，warning 180。
- `docs/contracts/autonomous-flow-trial/TRIAL_BX_EVALUATION_CN.md`：hard 150，warning 120。

## 5. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_attempt_run_readout_output.py tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/cli_autonomous_flow_attempt_outputs.py src/ashare_evidence/cli_autonomous_flow_attempt_readout_outputs.py src/ashare_evidence/cli_autonomous_flow_outputs.py tests/test_cli_autonomous_flow_attempt_run_readout_output.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_BX_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/cli_autonomous_flow_attempt_outputs.py:150:120 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_attempt_readout_outputs.py:120:90 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_outputs.py:160:140 \
  --line-budget tests/test_cli_autonomous_flow_attempt_run_readout_output.py:220:180 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_BX_EVALUATION_CN.md:150:120 \
  --line-budget-warning-margin src/ashare_evidence/cli_autonomous_flow_attempt_outputs.py:20 \
  --required-evidence tests/test_cli_autonomous_flow_attempt_run_readout_output.py:test_attempt_run_readout_output_reads_artifacts_without_running_scheduler \
  --required-evidence tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py:test_attempt_route_auto_apply_output_default_does_not_record_attempt_run
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BX_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BX_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
