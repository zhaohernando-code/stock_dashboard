# Trial AW 上下文包：CLI Action Route Output

目标：把 Trial AV 的 pure action router 暴露为 `phase5-local-cycle-step --output action-route`，让上层调度器可以一次获得下一步 route 和 required arguments。本轮仍不写任何 artifact，不生成 ID。

## 1. 背景

当前 CLI 已支持 `--output action`，会执行 no-op action executor，并在 blocked action 时返回 exit code 4。Trial AV 新增了纯函数 `route_phase5_scheduler_action_result(...)`，可以把 action result 的 `recommended_next_action` 转成 route。

当前缺口：调度器需要额外调用内部 Python 才能拿到 route。AW 要把它暴露为只读 CLI 输出。

## 2. 本轮范围

必须做：

- 新增 `--output action-route`。
- handler 顺序必须是 `tick -> plan -> execute_scheduler_noop_action -> route_scheduler_action_result`。
- 输出 route result JSON，而不是 action result JSON。
- `action-route` 不要求 `diagnostic_id`、`observed_at`、`execution_id`、`idempotency_key`、`created_at`。
- `action-route` 成功生成 route 时返回 exit code 0，即使 route_type 是 `diagnostic_output` 或 `execution_output`。
- 不调用 dry-run、diagnostic、execution ledger 或 full service。
- 不写 diagnostic、execution ledger、recovery ticket、projection、closeout，不生成 ID 或 timestamp。
- 新增独立测试文件，不修改 `tests/test_cli_autonomous_flow_action_output.py`。

不得做：

- 不改变 `--output action` 的 exit code 语义。
- 不改变 `--output execution` 的 required args / conflict exit code。
- 不改变 action executor 或 router 语义。
- 不自动执行 route 指向的下一步。

## 3. 建议实现

建议修改：

- `src/ashare_evidence/cli_autonomous_flow.py`
- `src/ashare_evidence/cli_autonomous_flow_outputs.py`

建议新增：

- `tests/test_cli_autonomous_flow_action_route_output.py`

建议 handler 增加：

```python
route_scheduler_action_result: Callable[..., Any]
```

建议分支：

```python
if args.output == "action-route":
    tick_result = _run_tick_from_args(args, handlers)
    plan = handlers.plan_followup(tick_result)
    action_result = handlers.execute_scheduler_noop_action(plan)
    route_result = handlers.route_scheduler_action_result(action_result)
    _print_json(route_result.model_dump(mode="json"))
    return 0
```

## 4. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| AW1 | CLI action-route output、测试、本评估文件 | 暴露 pure router CLI 输出 |

子进程注意：这是 route 读取入口，不是执行 route。任何 writer 调用或 ID 生成都视为跑偏。

## 5. 文件规模预算

- `src/ashare_evidence/cli_autonomous_flow.py`：hard 100，warning 90。
- `src/ashare_evidence/cli_autonomous_flow_outputs.py`：hard 240，warning 220。
- `tests/test_cli_autonomous_flow_action_route_output.py`：hard 220，warning 190。
- `tests/test_cli_autonomous_flow_action_output.py`：hard 220，warning 190，不得修改。

## 6. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_action_route_output.py tests/test_cli_autonomous_flow_action_output.py tests/test_cli_autonomous_flow_execution.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_outputs.py tests/test_cli_autonomous_flow_action_route_output.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_AW_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/cli_autonomous_flow.py:100:90 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_outputs.py:240:220 \
  --line-budget tests/test_cli_autonomous_flow_action_route_output.py:220:190 \
  --line-budget tests/test_cli_autonomous_flow_action_output.py:220:190 \
  --required-evidence tests/test_cli_autonomous_flow_action_route_output.py:test_phase5_local_cycle_step_action_route_output_calls_router_only
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_AW_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_AW_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
