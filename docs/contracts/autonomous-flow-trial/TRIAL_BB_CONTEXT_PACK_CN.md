# Trial BB 上下文包：Split CLI Execution Output Handlers

目标：拆分 `cli_autonomous_flow_outputs.py` 中的 `execution` / `full` 输出处理逻辑，降低 dispatcher 规模风险，为后续 `action-route-apply` CLI 接线预留结构空间。本轮只做行为保持的模块拆分。

## 1. 背景

Trial BA 已新增核心 `apply_phase5_scheduler_action_route(...)`。下一步如果直接在 CLI dispatcher 里追加 output 分支，`src/ashare_evidence/cli_autonomous_flow_outputs.py` 会从 198/200 继续膨胀，违反“基座能力不能打补丁式堆叠”的流程约束。

当前 dispatcher 已经承载 status、plan、dry-run、diagnostic、execution、action、action-route、action-route-preflight 和 full。action 与 diagnostic 已拆出独立模块；本轮继续拆出 execution/full。

## 2. 本轮范围

必须做：

- 新增独立模块，例如 `src/ashare_evidence/cli_autonomous_flow_execution_outputs.py`。
- 迁移 `_handle_execution_output(...)`、`_handle_full_output(...)`、execution conflict payload、missing argument helper、jsonable result helper。
- `cli_autonomous_flow_outputs.py` 只保留轻量分发调用。
- 不改变以下行为：
  - `--output execution` 缺 `--execution-id` / `--idempotency-key` / `--created-at` 时返回 exit code 2，且不调用 tick。
  - `--output execution` idempotency conflict 返回 exit code 3 与 typed JSON。
  - `--output execution` 正常路径仍是 `tick -> plan -> record_scheduler_plan_execution`。
  - `--output full` 成功返回 0，异常返回 1 与 error JSON。
  - `--output status` 仍透传 tick exit code。
- 不修改 parser choices/help。
- 不修改 action route/preflight/apply core、scheduler executor、artifact store 或 writer 语义。
- 不修改临界测试文件：`tests/test_cli_autonomous_flow_execution.py`、`tests/test_cli_autonomous_flow_action_route_preflight_output.py`、`tests/test_cli_autonomous_flow_action_output.py`。

不得做：

- 不新增 `action-route-apply` CLI output。
- 不接 BA 的 route apply core。
- 不改变任何 JSON schema 或 exit code。

## 3. 建议实现

建议新模块导出：

```python
def handle_execution_output(args, handlers, *, run_tick_from_args, print_json) -> int: ...
def handle_full_output(args, handlers, *, print_json) -> int: ...
```

主 dispatcher 中仅保留：

```python
if args.output == "execution":
    return handle_execution_output(args, handlers, run_tick_from_args=_run_tick_from_args, print_json=_print_json)

return handle_full_output(args, handlers, print_json=_print_json)
```

## 4. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| BB1 | CLI execution/full output handler split、本评估文件 | 行为保持拆分 |

子进程注意：这是结构拆分，不是功能扩展。任何 exit code、JSON 字段、writer 调用顺序变化都视为跑偏。

## 5. 文件规模预算

- `src/ashare_evidence/cli_autonomous_flow_outputs.py`：hard 220，warning 170。
- `src/ashare_evidence/cli_autonomous_flow_execution_outputs.py`：hard 180，warning 150。
- `src/ashare_evidence/cli_autonomous_flow_action_outputs.py`：hard 180，warning 150。
- `src/ashare_evidence/cli_autonomous_flow_diagnostic_outputs.py`：hard 160，warning 130。
- `tests/test_cli_autonomous_flow_execution.py`：hard 220，warning 190，不得修改。
- `tests/test_cli_autonomous_flow_action_route_preflight_output.py`：hard 220，warning 190，不得修改。
- `tests/test_cli_autonomous_flow_action_output.py`：hard 220，warning 190，不得修改。

如果新模块或 dispatcher 达到 warning，应继续拆分或压缩，不把规模问题留给下一轮。

## 6. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_execution.py tests/test_cli_autonomous_flow_full_output.py tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_action_route_preflight_output.py tests/test_cli_autonomous_flow_action_output.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/cli_autonomous_flow_outputs.py src/ashare_evidence/cli_autonomous_flow_execution_outputs.py tests/test_cli_autonomous_flow_execution.py tests/test_cli_autonomous_flow_full_output.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_BB_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/cli_autonomous_flow_outputs.py:220:170 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_execution_outputs.py:180:150 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_action_outputs.py:180:150 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_diagnostic_outputs.py:160:130 \
  --line-budget tests/test_cli_autonomous_flow_execution.py:220:190 \
  --line-budget tests/test_cli_autonomous_flow_action_route_preflight_output.py:220:190 \
  --line-budget tests/test_cli_autonomous_flow_action_output.py:220:190 \
  --required-evidence src/ashare_evidence/cli_autonomous_flow_execution_outputs.py:handle_execution_output
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BB_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BB_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
