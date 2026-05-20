# Trial BC 上下文包：CLI Action Route Apply Output

目标：把 Trial BA 的核心 route apply 层暴露为 `phase5-local-cycle-step --output action-route-apply`，让无人调度器可以通过 CLI 完成 `tick -> plan -> action -> route -> apply`，并保持所有写入都由核心 apply 层和现有 writer 控制。

## 1. 背景

Trial BA 已实现 `apply_phase5_scheduler_action_route(...)`，负责先 route preflight，再调用 diagnostic / execution writer 或返回 wait/terminal skipped。Trial BB 已拆出 execution/full 输出 handler，把 CLI dispatcher 降到 114 行。

当前缺口：CLI 仍只能输出 route 或 route preflight，不能把 ready route 交给核心 apply 层执行。上层 shell/cron 若自行拼接 diagnostic/execution output，仍可能绕过 BA 的 typed blocked/conflict/no-op 结果。

## 2. 本轮范围

必须做：

- 新增 CLI output choice：`action-route-apply`。
- handler 顺序必须是 `tick -> plan -> action -> route -> apply`。
- CLI handler 必须调用 `apply_phase5_scheduler_action_route(...)` 或注入的等价 handler，不在 CLI 中重写 diagnostic/execution writer 分支。
- 输出 `Phase5SchedulerActionRouteApplyResult` JSON。
- `execution_status="applied"` 或 `"skipped"` 返回 exit code 0。
- `execution_status="blocked"` 返回 exit code 4，沿用 action blocked contract。
- 参数传递：
  - `--diagnostic-id` -> `diagnostic_id`
  - `--observed-at` -> `observed_at`
  - `--execution-id` -> `execution_id`
  - `--idempotency-key` -> `idempotency_key`
  - `--created-at` -> `created_at`
  - `--diagnostic-id` 作为 execution route 的 `diagnostic_refs`，如果非空。
- 不生成 ID/timestamp，不读取当前时间。
- 不调用 dry-run、diagnostic output handler、execution output handler、full service。
- 不修改 BA core、route mapping、route preflight 或 action executor 语义。
- 新增独立测试文件，不修改临界测试文件。

不得做：

- 不在 CLI 中直接调用 `record_phase5_scheduler_plan_diagnostic(...)` 或 `record_phase5_scheduler_plan_execution(...)`。
- 不把 blocked route apply 当作 exit 0。
- 不把 missing args 变成 parser 层强制参数；必须由 BA preflight typed result 表达。

## 3. 建议实现

建议修改：

- `src/ashare_evidence/cli_autonomous_flow.py`
- `src/ashare_evidence/cli_autonomous_flow_outputs.py`
- `src/ashare_evidence/cli_autonomous_flow_action_outputs.py`

建议新增 handler 注入：

```python
apply_scheduler_action_route: Callable[..., Any]
```

建议新增：

```python
def handle_action_route_apply_output(...): ...
```

## 4. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| BC1 | CLI action-route-apply output、测试、本评估文件 | 暴露核心 route apply CLI 输出 |

子进程注意：CLI 只是薄封装，不能绕过 BA core 自己写 writer 分支。

## 5. 文件规模预算

- `src/ashare_evidence/cli_autonomous_flow.py`：hard 110，warning 95。
- `src/ashare_evidence/cli_autonomous_flow_outputs.py`：hard 220，warning 170。
- `src/ashare_evidence/cli_autonomous_flow_action_outputs.py`：hard 180，warning 150。
- `src/ashare_evidence/autonomous_flow_scheduler_action_route_executor.py`：hard 180，warning 150，不建议修改。
- `tests/test_cli_autonomous_flow_action_route_apply_output.py`：hard 220，warning 190。
- `tests/test_cli_autonomous_flow_action_route_preflight_output.py`：hard 220，warning 190，不得修改。
- `tests/test_cli_autonomous_flow_action_output.py`：hard 220，warning 190，不得修改。

如果达到 warning，必须在本轮压缩或拆分。

## 6. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_action_route_apply_output.py tests/test_cli_autonomous_flow_action_route_preflight_output.py tests/test_cli_autonomous_flow_action_route_output.py tests/test_autonomous_flow_scheduler_action_route_executor.py tests/test_cli_autonomous_flow_execution.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_outputs.py src/ashare_evidence/cli_autonomous_flow_action_outputs.py tests/test_cli_autonomous_flow_action_route_apply_output.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_BC_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/cli_autonomous_flow.py:110:95 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_outputs.py:220:170 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_action_outputs.py:180:150 \
  --line-budget src/ashare_evidence/autonomous_flow_scheduler_action_route_executor.py:180:150 \
  --line-budget tests/test_cli_autonomous_flow_action_route_apply_output.py:220:190 \
  --line-budget tests/test_cli_autonomous_flow_action_route_preflight_output.py:220:190 \
  --line-budget tests/test_cli_autonomous_flow_action_output.py:220:190 \
  --required-evidence tests/test_cli_autonomous_flow_action_route_apply_output.py:test_action_route_apply_output_calls_core_apply_only
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BC_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BC_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
