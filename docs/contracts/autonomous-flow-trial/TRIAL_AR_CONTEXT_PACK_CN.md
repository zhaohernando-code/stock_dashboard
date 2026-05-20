# Trial AR 上下文包：Scheduler No-op Action Executor

目标：在已有 scheduler action contract 与 preflight 基础上，接入第一类真实 action 执行入口，但本轮只支持无副作用 action：`continue_tracking` 和 `none`。

## 1. 背景

Trial AP 已集中声明每个 scheduler action 的 required inputs、allowed side effects、durable outputs 和 closeout 边界。Trial AQ 已提供纯 `preflight_phase5_scheduler_action(...)`，可以在执行前判定输入和副作用授权是否满足。

当前缺口是：系统还没有一个“执行入口”把 follow-up plan 映射为 typed action execution result。已有 dry-run 只描述计划效果，execution ledger 只记录执行意图，两者都不能表示一个 action 已经被安全处理。本轮先从无副作用 action 开始，建立 executor 形状和门禁口径。

## 2. 本轮范围

必须做：

- 新增独立 action executor 模块，避免继续膨胀 action contract 或 scheduler executor 文件。
- executor 接收 `Phase5SchedulerFollowupPlan`，先调用 `preflight_phase5_scheduler_action(...)`。
- 仅允许执行 `continue_tracking` 和 `none`。
- `continue_tracking` 与 `none` 不写 artifact、不写 execution ledger、不写 diagnostic、不改 cycle closeout、不读网络/DB/当前时间。
- 返回小型 typed result，表达 action、status、preflight status、performed effects、skipped reason、durable outputs、may close cycle。
- 对不支持的 action 返回 blocked/skipped typed result，而不是尝试执行或抛出未结构化异常。
- 覆盖 input object 不被修改、无文件写入、preflight missing input 阻塞、非 no-op action 阻塞。

不得做：

- 不改 CLI output。
- 不接入 scheduler execution ledger/reservation。
- 不写 recovery ticket、projection、cycle closeout 或 diagnostic artifact。
- 不把 action 执行逻辑塞进 `autonomous_flow.py`。
- 不修改 `Phase5SchedulerAction` 枚举。
- 不让 executor 根据字符串临时拼接未注册副作用。

## 3. 建议接口

建议新增文件：

- `src/ashare_evidence/autonomous_flow_scheduler_action_executor.py`
- `tests/test_autonomous_flow_scheduler_action_executor.py`

建议模型：

```python
Phase5SchedulerActionExecutionStatus = Literal["completed", "blocked"]
Phase5SchedulerActionExecutionMode = Literal["contract_action"]

class Phase5SchedulerActionExecutionResult(BaseModel):
    cycle_id: str
    execution_mode: Phase5SchedulerActionExecutionMode = "contract_action"
    execution_status: Phase5SchedulerActionExecutionStatus
    action: Phase5SchedulerAction
    preflight_status: Phase5SchedulerActionPreflightStatus
    performed_effects: tuple[str, ...]
    skipped_reason: str | None = None
    durable_outputs: tuple[str, ...]
    may_close_cycle: bool
    reason: str
```

建议函数：

```python
execute_phase5_scheduler_noop_action(plan: Phase5SchedulerFollowupPlan) -> Phase5SchedulerActionExecutionResult
```

执行语义：

- `provided_input_names` 至少包含 `cycle_id` 和 `scheduler_followup_plan`。
- `requested_side_effects` 对 no-op action 传空集合。
- `continue_tracking` ready 后返回 `completed`，`performed_effects=("keep_cycle_open_for_next_tick",)`。
- `none` ready 后返回 `completed`，`performed_effects=("no_op",)`。
- 非 no-op action 即使 preflight 输入满足，也返回 `blocked`，`skipped_reason="scheduler action executor only supports no-op actions in this trial"`。
- preflight blocked 时返回 `blocked`，`performed_effects=()`。

## 4. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| AR1 | action executor 模块、测试、本评估文件 | 实现 no-op action executor 并补齐验证 |

子进程必须注意：当前不是孤立代码任务，而是流程基座试运行。实现应服从 Context Pack，不要扩范围补 CLI 或真实写入链路。

## 5. 文件规模预算

- `src/ashare_evidence/autonomous_flow_scheduler_action_executor.py`：hard 180，warning 150。
- `tests/test_autonomous_flow_scheduler_action_executor.py`：hard 220，warning 190。
- `src/ashare_evidence/autonomous_flow_scheduler_action_contract.py`：hard 220，warning 180，不建议修改。
- `src/ashare_evidence/autonomous_flow_scheduler_executor.py`：hard 220，warning 190，不建议修改。

如果达到 warning，必须在本轮拆分或缩小实现，不把规模问题留到后续。

## 6. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_scheduler_action_executor.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/autonomous_flow_scheduler_action_executor.py tests/test_autonomous_flow_scheduler_action_executor.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_AR_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/autonomous_flow_scheduler_action_executor.py:180:150 \
  --line-budget tests/test_autonomous_flow_scheduler_action_executor.py:220:190 \
  --line-budget src/ashare_evidence/autonomous_flow_scheduler_action_contract.py:220:180 \
  --required-evidence tests/test_autonomous_flow_scheduler_action_executor.py:test_noop_action_executor_completes_continue_tracking_without_writes
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_AR_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_AR_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
