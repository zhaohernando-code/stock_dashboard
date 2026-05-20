# Trial BD 上下文包：Scheduler Action Route Argument Binding

目标：新增纯 route argument binding 层，为 `diagnostic_output` / `execution_output` route 生成稳定参数包，让无人调度器不再依赖人工提供 `diagnostic_id`、`execution_id`、`idempotency_key` 等参数。本轮不接 CLI，不执行 apply，不写 artifact。

## 1. 背景

Trial BC 已把 `action-route-apply` 暴露到 CLI，但调用方仍需要显式提供 route 所需参数。无人调度器需要一个可重放、可审计的参数绑定层：给定 route、外部注入的时间与 attempt id，生成下一步 apply 所需参数。

该层必须保持纯函数，不能读取当前时间。时间必须由调用方显式传入，避免测试和 crash replay 跑偏。

## 2. 本轮范围

必须做：

- 新增独立模块，例如 `src/ashare_evidence/autonomous_flow_scheduler_action_route_arguments.py`。
- 提供 typed result，例如 `Phase5SchedulerActionRouteArgumentBindingResult`。
- 提供纯函数，例如 `bind_phase5_scheduler_action_route_arguments(...)`。
- 输入至少包含 `Phase5SchedulerActionRouteResult`、`attempt_id`、可选 `issued_at`。
- `wait_for_next_tick` / `terminal` 返回 ready 且空参数。
- `diagnostic_output`：
  - 需要 `issued_at`。
  - 生成 `diagnostic_id` 与 `observed_at`。
  - `observed_at == issued_at`。
- `execution_output`：
  - 需要 `issued_at`。
  - 生成 `execution_id`、`idempotency_key`、`created_at`。
  - `created_at == issued_at`。
  - `idempotency_key` 必须由 execution id 稳定派生。
- 如果 route 需要时间但 `issued_at` 为空，返回 typed blocked result，不生成部分参数。
- 生成的 id 必须稳定、文件名安全，并包含 cycle/action/attempt 的可读信息或稳定摘要。
- 不读取当前时间，不生成随机数，不写 artifact，不调用 apply/core writer/CLI。
- 不修改 route mapping、route preflight、route apply core 语义。

不得做：

- 不接 `action-route-apply` CLI。
- 不执行 route apply。
- 不读取 artifact store 或 DB。
- 不把自然语言 reason 作为分支依据。

## 3. 建议模型

```python
Phase5SchedulerActionRouteArgumentBindingStatus = Literal["ready", "blocked"]

class Phase5SchedulerActionRouteArgumentBindingResult(BaseModel):
    cycle_id: str
    route_type: Phase5SchedulerActionRouteType
    status: Phase5SchedulerActionRouteArgumentBindingStatus
    required_arguments: tuple[str, ...]
    provided_arguments: dict[str, str]
    missing_arguments: tuple[str, ...]
    reason: str
```

建议函数：

```python
def bind_phase5_scheduler_action_route_arguments(
    route: Phase5SchedulerActionRouteResult,
    *,
    attempt_id: str,
    issued_at: str | None = None,
) -> Phase5SchedulerActionRouteArgumentBindingResult: ...
```

## 4. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| BD1 | route argument binding、测试、本评估文件 | 新增纯参数绑定层 |

子进程注意：这是纯 binding，不是 apply，不得写 artifact。

## 5. 文件规模预算

- `src/ashare_evidence/autonomous_flow_scheduler_action_route_arguments.py`：hard 180，warning 150。
- `tests/test_autonomous_flow_scheduler_action_route_arguments.py`：hard 220，warning 190。
- `src/ashare_evidence/autonomous_flow_scheduler_action_router.py`：hard 180，warning 150，不建议修改。
- `src/ashare_evidence/autonomous_flow_scheduler_action_route_executor.py`：hard 180，warning 150，不建议修改。

如果达到 warning，必须在本轮压缩或拆分。

## 6. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_scheduler_action_route_arguments.py tests/test_autonomous_flow_scheduler_action_route_preflight.py tests/test_autonomous_flow_scheduler_action_route_executor.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/autonomous_flow_scheduler_action_route_arguments.py tests/test_autonomous_flow_scheduler_action_route_arguments.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_BD_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/autonomous_flow_scheduler_action_route_arguments.py:180:150 \
  --line-budget tests/test_autonomous_flow_scheduler_action_route_arguments.py:220:190 \
  --line-budget src/ashare_evidence/autonomous_flow_scheduler_action_router.py:180:150 \
  --line-budget src/ashare_evidence/autonomous_flow_scheduler_action_route_executor.py:180:150 \
  --required-evidence tests/test_autonomous_flow_scheduler_action_route_arguments.py:test_route_argument_binding_generates_execution_arguments
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BD_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BD_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
