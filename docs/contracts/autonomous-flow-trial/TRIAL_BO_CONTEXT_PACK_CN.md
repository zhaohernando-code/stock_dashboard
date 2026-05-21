# Trial BO 上下文包：CLI Output Context Split

目标：对 `cli_autonomous_flow_outputs.py` 做结构性减压，把共享 handler dataclass、tick 参数绑定和 JSON 输出工具拆到独立 helper，避免后续继续在接近 warning 的 dispatcher 文件里堆功能。

## 1. 背景

BM 后 `cli_autonomous_flow_outputs.py` 为 150 行，warning 160。虽然还未触发 warning，但已经不适合继续承载 handler 类型、公共 IO helper 和所有 output 分发。BN 已新增 `--line-budget-warning-margin`，本轮要用它把“拆分而不是继续堆叠”转成可验证门禁。

本轮不新增 CLI output，不改变现有输出语义，只移动共享结构。

## 2. 本轮范围

必须做：

- 新增独立模块，例如 `src/ashare_evidence/cli_autonomous_flow_output_context.py`。
- 移入 `Phase5LocalCycleStepHandlers` dataclass。
- 移入 tick 参数绑定 helper，例如 `run_tick_from_args(args, handlers)`。
- 移入 JSON 输出 helper，例如 `print_json(payload)`。
- `cli_autonomous_flow_outputs.py` 使用新 helper，行数必须明显下降，并通过 warning margin gate。
- 保持 `src/ashare_evidence/cli_autonomous_flow.py` 对 `Phase5LocalCycleStepHandlers` 的导入兼容，或做最小清晰导入调整。
- 不新增 output、不改变 exit code、不改变输出 JSON shape。
- 不扩写 `tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py`，该文件已经接近 warning。

不得做：

- 不重写整个 dispatcher。
- 不引入 registry/artifact/DB 行为。
- 不改变 `action-route-auto-apply` 或 `attempt-route-auto-apply` 语义。
- 不把新 helper 做成抽象框架；只拆当前共享结构。

## 3. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| BO1 | CLI output context helper、导入调整、本评估文件 | 降低 dispatcher 文件规模并保持行为不变 |

## 4. 文件规模预算

- `src/ashare_evidence/cli_autonomous_flow_outputs.py`：hard 190，warning 160，margin minimum 15。
- `src/ashare_evidence/cli_autonomous_flow_output_context.py`：hard 140，warning 110。
- `src/ashare_evidence/cli_autonomous_flow.py`：hard 190，warning 170。
- `tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py`：hard 220，warning 180，不允许修改。
- `docs/contracts/autonomous-flow-trial/TRIAL_BO_EVALUATION_CN.md`：hard 150，warning 120。

如果 dispatcher 仍无法满足 margin，必须继续拆分，而不是降低门禁。

## 5. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_outputs.py tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py tests/test_cli_autonomous_flow_action_route_auto_apply_output.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_outputs.py src/ashare_evidence/cli_autonomous_flow_output_context.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_BO_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/cli_autonomous_flow_outputs.py:190:160 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_output_context.py:140:110 \
  --line-budget src/ashare_evidence/cli_autonomous_flow.py:190:170 \
  --line-budget tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py:220:180 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_BO_EVALUATION_CN.md:150:120 \
  --required-evidence tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py:test_attempt_route_auto_apply_output_builds_context_then_applies \
  --line-budget-warning-margin src/ashare_evidence/cli_autonomous_flow_outputs.py:15
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BO_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BO_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
