# Trial AV 上下文包：Action Follow-up Router

目标：新增一个纯 route planner，把 `Phase5SchedulerActionExecutionResult.recommended_next_action` 转换为机器可消费的下一步路由要求。该 router 只分类下一步，不生成 ID、不写 artifact、不调用 CLI。

## 1. 背景

Trial AU 已在 action result 中加入 `recommended_next_action`：

- `continue_scheduler_tracking`
- `finish_without_followup`
- `record_scheduler_diagnostic`
- `record_scheduler_execution_intent`

当前缺口：上层调度器仍需要自己知道这些建议对应哪个 output 模式、需要哪些参数、是否是 terminal 状态。为避免每个调度进程重复写字符串分支，本轮建立纯 route planner。

## 2. 本轮范围

必须做：

- 新增独立模块，例如 `autonomous_flow_scheduler_action_router.py`。
- 输入 `Phase5SchedulerActionExecutionResult`，输出 typed route result。
- 不修改 action executor 语义，不修改 CLI exit code。
- 不生成 `diagnostic_id`、`execution_id`、`idempotency_key`、timestamp。
- 不写 diagnostic、execution ledger、recovery ticket、projection、closeout。
- 覆盖四类 route：
  - `continue_scheduler_tracking` -> `route_type="wait_for_next_tick"`，无 required arguments。
  - `finish_without_followup` -> `route_type="terminal"`，无 required arguments。
  - `record_scheduler_diagnostic` -> `route_type="diagnostic_output"`，required arguments 为 `diagnostic_id`、`observed_at`。
  - `record_scheduler_execution_intent` -> `route_type="execution_output"`，required arguments 为 `execution_id`、`idempotency_key`、`created_at`。
- route result 必须保留 `cycle_id`、`action`、`source_status`、`recommended_next_action`、`reason`。

## 3. 建议模型

```python
Phase5SchedulerActionRouteType = Literal[
    "wait_for_next_tick",
    "terminal",
    "diagnostic_output",
    "execution_output",
]

class Phase5SchedulerActionRouteResult(BaseModel):
    cycle_id: str
    action: Phase5SchedulerAction
    source_status: Phase5SchedulerActionExecutionStatus
    recommended_next_action: Phase5SchedulerActionRecommendedNextAction
    route_type: Phase5SchedulerActionRouteType
    required_arguments: tuple[str, ...]
    reason: str
```

建议函数：

```python
route_phase5_scheduler_action_result(result: Phase5SchedulerActionExecutionResult) -> Phase5SchedulerActionRouteResult
```

## 4. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| AV1 | action router、router tests、本评估文件 | 新增 action follow-up route planner |

子进程注意：这不是自动执行下一步任务，只是路由分类合同。任何 artifact 写入或 CLI 调用都视为跑偏。

## 5. 文件规模预算

- `src/ashare_evidence/autonomous_flow_scheduler_action_router.py`：hard 160，warning 130。
- `tests/test_autonomous_flow_scheduler_action_router.py`：hard 200，warning 170。
- `src/ashare_evidence/autonomous_flow_scheduler_action_executor.py`：hard 180，warning 150，不建议修改。

## 6. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_scheduler_action_router.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/autonomous_flow_scheduler_action_router.py tests/test_autonomous_flow_scheduler_action_router.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_AV_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/autonomous_flow_scheduler_action_router.py:160:130 \
  --line-budget tests/test_autonomous_flow_scheduler_action_router.py:200:170 \
  --line-budget src/ashare_evidence/autonomous_flow_scheduler_action_executor.py:180:150 \
  --required-evidence tests/test_autonomous_flow_scheduler_action_router.py:test_action_router_routes_diagnostic_hint_to_required_arguments
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_AV_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_AV_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
