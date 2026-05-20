# Trial AX 上下文包：Split CLI Action Output Handlers

目标：拆分 `cli_autonomous_flow_outputs.py` 中的 `action` / `action-route` 处理逻辑，降低主 output dispatcher 的规模风险。本轮只做结构拆分，不改变任何 CLI 行为。

## 1. 背景

Trial AW 后，`src/ashare_evidence/cli_autonomous_flow_outputs.py` 达到 218 行，距离 warning 220 只有 2 行。该文件已经承载 status、plan、dry-run、diagnostic、execution、action、action-route 和 full 分支。继续在这里追加无人化执行功能会退化成打补丁。

本轮先把 action 相关输出拆到独立模块，给后续真实调度链路留出设计空间。

## 2. 本轮范围

必须做：

- 新增独立模块，例如 `cli_autonomous_flow_action_outputs.py`。
- 迁移 `action` / `action-route` 输出逻辑和 `_ACTION_BLOCKED_EXIT_CODE` / action exit code helper。
- `cli_autonomous_flow_outputs.py` 只保留轻量分发调用。
- 不改变以下行为：
  - `--output action` completed 返回 0。
  - `--output action` blocked 返回 4，并打印 action result JSON。
  - `--output action-route` 返回 0，并打印 route result JSON。
  - `--output execution` conflict 返回 3。
  - `--output status` 透传 tick exit code。
- 不修改 `tests/test_cli_autonomous_flow_action_output.py`，该文件处于 189/190 临界点。
- 新增或调整测试时使用独立文件。

不得做：

- 不改变 parser choices 或 help 文案。
- 不改变 action executor、router、ledger/reservation、artifact store、diagnostic/recovery/projection/closeout。
- 不新增真实写入能力。

## 3. 建议实现

建议新增：

```python
def handle_action_output(args, handlers, *, run_tick_from_args, print_json) -> int: ...
def handle_action_route_output(args, handlers, *, run_tick_from_args, print_json) -> int: ...
```

主 dispatcher 中：

```python
if args.output == "action":
    return handle_action_output(args, handlers, run_tick_from_args=_run_tick_from_args, print_json=_print_json)
if args.output == "action-route":
    return handle_action_route_output(args, handlers, run_tick_from_args=_run_tick_from_args, print_json=_print_json)
```

## 4. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| AX1 | CLI action output handler split、测试、本评估文件 | 拆分 action/action-route 输出逻辑 |

子进程注意：这是结构性拆分，不是功能扩展。行为变更视为跑偏。

## 5. 文件规模预算

- `src/ashare_evidence/cli_autonomous_flow_outputs.py`：hard 240，warning 200。
- `src/ashare_evidence/cli_autonomous_flow_action_outputs.py`：hard 160，warning 130。
- `src/ashare_evidence/cli_autonomous_flow_diagnostic_outputs.py`：hard 160，warning 130；如 action split 后 dispatcher 仍超 warning，可拆出 diagnostic handler。
- `tests/test_cli_autonomous_flow_action_route_output.py`：hard 220，warning 190。
- `tests/test_cli_autonomous_flow_action_output.py`：hard 220，warning 190，不得修改。

## 6. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_action_route_output.py tests/test_cli_autonomous_flow_action_output.py tests/test_cli_autonomous_flow_execution.py tests/test_cli_autonomous_flow.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/cli_autonomous_flow_outputs.py src/ashare_evidence/cli_autonomous_flow_action_outputs.py tests/test_cli_autonomous_flow_action_route_output.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_AX_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/cli_autonomous_flow_outputs.py:240:200 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_action_outputs.py:160:130 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_diagnostic_outputs.py:160:130 \
  --line-budget tests/test_cli_autonomous_flow_action_route_output.py:220:190 \
  --line-budget tests/test_cli_autonomous_flow_action_output.py:220:190 \
  --required-evidence src/ashare_evidence/cli_autonomous_flow_action_outputs.py:handle_action_route_output
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_AX_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_AX_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
