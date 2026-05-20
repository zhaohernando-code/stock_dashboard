# Trial BA 上下文包：Scheduler Action Route Apply Core

目标：新增一个核心 route apply 层，消费 action route result 与调度器已提供参数，先执行 route preflight，再按 route 类型调用现有 diagnostic / execution writer 或返回无写入结果。本轮不接 CLI，不生成任何 ID 或时间。

## 1. 背景

Trial AV-AZ 已形成链路：`action result -> route -> route preflight -> CLI preflight output`。当前仍缺少一个可复用的核心执行层，把 ready route 安全地落到已有 writer。没有这层时，上层 scheduler 或 shell 需要自己根据 route JSON 分支调用 `diagnostic` / `execution` 输出，容易绕过 preflight、幂等边界和统一返回模型。

本轮应建立核心库函数，后续 CLI 或自动调度器只能薄封装该函数，而不是各自拼接 writer。

## 2. 本轮范围

必须做：

- 新增独立模块，例如 `src/ashare_evidence/autonomous_flow_scheduler_action_route_executor.py`。
- 提供 typed result，例如 `Phase5SchedulerActionRouteApplyResult`。
- 提供核心函数，例如 `apply_phase5_scheduler_action_route(...)`。
- 输入至少包含 scheduler follow-up plan、route result、route 所需参数与 `root`。
- 函数内部必须先调用 `preflight_phase5_scheduler_action_route(...)`，不得绕过。
- `diagnostic_output` ready 时调用现有 `record_phase5_scheduler_plan_diagnostic(...)`。
- `execution_output` ready 时调用现有 `record_phase5_scheduler_plan_execution(...)`。
- `wait_for_next_tick` 与 `terminal` 无 writer，返回 typed skipped/no-op 结果。
- route preflight blocked 时返回 typed blocked 结果，不调用 writer。
- `Phase5SchedulerExecutionIdempotencyConflictError` 必须转成 typed blocked 结果，不能让无人调度器因为未结构化异常卡住。
- 覆盖 plan/route cycle 或 action 不匹配时的 fail-closed 行为，不能写 artifact。
- 不生成 `diagnostic_id`、`observed_at`、`execution_id`、`idempotency_key` 或 `created_at`。
- 不读取当前时间，不调用 CLI，不调用 full service，不修改 route/preflight/action executor 语义。

不得做：

- 不新增 CLI output。
- 不执行真正业务 action；本轮只把 route 指向的 diagnostic / execution ledger 记录落到现有 writer。
- 不修改 `record_phase5_scheduler_plan_diagnostic(...)` 或 `record_phase5_scheduler_plan_execution(...)` 语义。
- 不修改临界 CLI 测试文件。

## 3. 建议结果模型

建议字段保持扁平，避免嵌套 plan/tick payload 泄漏：

```python
Phase5SchedulerActionRouteApplyStatus = Literal["applied", "blocked", "skipped"]
Phase5SchedulerActionRouteAppliedOutput = Literal["none", "diagnostic", "execution"]

class Phase5SchedulerActionRouteApplyResult(BaseModel):
    cycle_id: str
    route_type: Phase5SchedulerActionRouteType
    execution_mode: Literal["route_apply"] = "route_apply"
    execution_status: Phase5SchedulerActionRouteApplyStatus
    preflight_status: Phase5SchedulerActionRoutePreflightStatus
    applied_output: Phase5SchedulerActionRouteAppliedOutput
    required_arguments: tuple[str, ...]
    missing_arguments: tuple[str, ...]
    diagnostic_id: str | None = None
    execution_id: str | None = None
    idempotency_key: str | None = None
    cycle_event_recorded: bool = False
    reason: str
    error_type: str | None = None
```

## 4. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| BA1 | route apply core、测试、本评估文件 | 实现核心 route apply 函数与门禁 |

子进程注意：这是核心执行层，不是 CLI。所有写入都必须来自现有 writer，且必须先经过 route preflight。

## 5. 文件规模预算

- `src/ashare_evidence/autonomous_flow_scheduler_action_route_executor.py`：hard 180，warning 150。
- `tests/test_autonomous_flow_scheduler_action_route_executor.py`：hard 220，warning 190。
- `src/ashare_evidence/autonomous_flow_scheduler_action_router.py`：hard 180，warning 150，不建议修改。
- `src/ashare_evidence/autonomous_flow_scheduler_executor.py`：hard 220，warning 190，不建议修改。
- `tests/test_cli_autonomous_flow_action_route_preflight_output.py`：hard 220，warning 190，不得修改。
- `tests/test_cli_autonomous_flow_action_output.py`：hard 220，warning 190，不得修改。

如果新增测试接近 warning，应在本轮拆分，不把规模风险留给后续。

## 6. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_scheduler_action_route_executor.py tests/test_autonomous_flow_scheduler_action_route_preflight.py tests/test_autonomous_flow_scheduler_execution_executor.py tests/test_autonomous_flow_scheduler_executor.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/autonomous_flow_scheduler_action_route_executor.py tests/test_autonomous_flow_scheduler_action_route_executor.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_BA_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/autonomous_flow_scheduler_action_route_executor.py:180:150 \
  --line-budget tests/test_autonomous_flow_scheduler_action_route_executor.py:220:190 \
  --line-budget src/ashare_evidence/autonomous_flow_scheduler_action_router.py:180:150 \
  --line-budget src/ashare_evidence/autonomous_flow_scheduler_executor.py:220:190 \
  --line-budget tests/test_cli_autonomous_flow_action_route_preflight_output.py:220:190 \
  --line-budget tests/test_cli_autonomous_flow_action_output.py:220:190 \
  --required-evidence tests/test_autonomous_flow_scheduler_action_route_executor.py:test_route_apply_blocks_missing_diagnostic_arguments_without_writing
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BA_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BA_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
