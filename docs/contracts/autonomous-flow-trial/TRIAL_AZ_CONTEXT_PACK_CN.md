# Trial AZ 上下文包：CLI Action Route Preflight Output

目标：把 AY 的 action route apply preflight 暴露为只读 CLI 输出 `phase5-local-cycle-step --output action-route-preflight`。它检查下一步 route 的参数是否齐备，但不执行 route，不生成参数。

## 1. 背景

`action-route` 可以返回下一步 route 和 required arguments。`preflight_phase5_scheduler_action_route(...)` 可以判断调用方提供了哪些参数。当前缺口是上层调度器无法通过 CLI 一次拿到 route preflight 结果。

## 2. 本轮范围

必须做：

- 新增 `--output action-route-preflight`。
- handler 顺序：`tick -> plan -> action -> route -> route preflight`。
- `provided_argument_names` 由已传入的 CLI 参数推导：
  - `--diagnostic-id` -> `diagnostic_id`
  - `--observed-at` -> `observed_at`
  - `--execution-id` -> `execution_id`
  - `--idempotency-key` -> `idempotency_key`
  - `--created-at` -> `created_at`
- 输出 route preflight JSON。
- ready 返回 exit code 0；blocked 返回固定 exit code 4，和 action blocked 保持一致。
- 不调用 diagnostic recorder、execution ledger recorder、full service 或 writer。
- 不生成 ID/timestamp。
- 不改变 `action`、`action-route`、`diagnostic`、`execution`、`status` 既有语义。
- 新增独立测试文件，不修改临界 `tests/test_cli_autonomous_flow_action_output.py`。

不得做：

- 不执行 route 指向的下一步。
- 不修改 action executor、router mapping 或 route preflight 语义。
- 不新增真实写入能力。

## 3. 建议实现

建议修改：

- `src/ashare_evidence/cli_autonomous_flow.py`
- `src/ashare_evidence/cli_autonomous_flow_outputs.py`
- `src/ashare_evidence/cli_autonomous_flow_action_outputs.py`

建议新增 handler 注入：

```python
preflight_scheduler_action_route: Callable[..., Any]
```

建议新增函数：

```python
def handle_action_route_preflight_output(...): ...
```

## 4. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| AZ1 | CLI action-route-preflight output、测试、本评估文件 | 暴露 route preflight CLI 输出 |

子进程注意：这是只读 preflight，不是 route apply。

## 5. 文件规模预算

- `src/ashare_evidence/cli_autonomous_flow.py`：hard 100，warning 90。
- `src/ashare_evidence/cli_autonomous_flow_outputs.py`：hard 240，warning 200。
- `src/ashare_evidence/cli_autonomous_flow_action_outputs.py`：hard 180，warning 150。
- `tests/test_cli_autonomous_flow_action_route_preflight_output.py`：hard 220，warning 190。
- `tests/test_cli_autonomous_flow_action_output.py`：hard 220，warning 190，不得修改。

## 6. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_action_route_preflight_output.py tests/test_cli_autonomous_flow_action_route_output.py tests/test_cli_autonomous_flow_action_output.py tests/test_cli_autonomous_flow_execution.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_outputs.py src/ashare_evidence/cli_autonomous_flow_action_outputs.py tests/test_cli_autonomous_flow_action_route_preflight_output.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_AZ_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/cli_autonomous_flow.py:100:90 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_outputs.py:240:200 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_action_outputs.py:180:150 \
  --line-budget tests/test_cli_autonomous_flow_action_route_preflight_output.py:220:190 \
  --line-budget tests/test_cli_autonomous_flow_action_output.py:220:190 \
  --required-evidence tests/test_cli_autonomous_flow_action_route_preflight_output.py:test_action_route_preflight_output_blocks_missing_diagnostic_arguments
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_AZ_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_AZ_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
