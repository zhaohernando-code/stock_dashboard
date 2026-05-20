# Trial AU 上下文包：Action Result Recovery Hint

目标：为 scheduler action execution result 增加机器可消费的下一步建议，让无人化调度器在 action completed / blocked 后能继续决策，而不是只依赖自然语言 reason。

## 1. 背景

Trial AR 建立了 no-op action executor。Trial AS 把 executor 接入 CLI。Trial AT 固化了 blocked action 的 exit code 4。

当前缺口：blocked action 虽然有 exit code 和 `skipped_reason`，但上层调度器仍需要解析自然语言才能判断下一步应该记录 diagnostic、记录 execution intent，还是继续等待。无人化流程不应依赖自然语言字符串分支。

本轮只在 typed result 里增加分类字段，不自动执行建议动作。

## 2. 本轮范围

必须做：

- 在 action executor result 中新增 typed `recommended_next_action` 字段。
- completed `continue_tracking` 返回 `continue_scheduler_tracking`。
- completed `none` 返回 `finish_without_followup`。
- preflight blocked 返回 `record_scheduler_diagnostic`。
- 非 no-op action 但 preflight ready 返回 `record_scheduler_execution_intent`。
- 保持 JSON 仍为扁平 action result，不嵌套 plan/tick payload。
- 更新 executor tests；CLI action smoke 如天然透传新字段，只需覆盖关键字段即可，不膨胀临界测试文件。

不得做：

- 不自动调用 diagnostic、execution ledger、recovery ticket、projection 或 closeout。
- 不修改 CLI exit code。
- 不修改 action contract / preflight 语义。
- 不让上层逻辑解析自然语言 reason 来决定下一步。

## 3. 建议模型

建议 literal：

```python
Phase5SchedulerActionRecommendedNextAction = Literal[
    "continue_scheduler_tracking",
    "finish_without_followup",
    "record_scheduler_diagnostic",
    "record_scheduler_execution_intent",
]
```

建议 result 字段：

```python
recommended_next_action: Phase5SchedulerActionRecommendedNextAction
```

建议 helper：

```python
def _completed_next_action(action: Phase5SchedulerAction) -> Phase5SchedulerActionRecommendedNextAction:
    if action == "none":
        return "finish_without_followup"
    return "continue_scheduler_tracking"
```

## 4. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| AU1 | action executor、executor tests、本评估文件 | 为 typed action result 增加下一步建议 |

子进程注意：这是 result contract 扩展，不是调度器执行任务。不得写 artifact，也不得修改 CLI exit code。

## 5. 文件规模预算

- `src/ashare_evidence/autonomous_flow_scheduler_action_executor.py`：hard 180，warning 150。
- `tests/test_autonomous_flow_scheduler_action_executor.py`：hard 220，warning 190。
- `tests/test_cli_autonomous_flow_action_output.py`：hard 220，warning 190，不建议修改。

如果目标文件达到 warning，必须拆分或缩小实现。

## 6. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_scheduler_action_executor.py tests/test_cli_autonomous_flow_action_output.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/autonomous_flow_scheduler_action_executor.py tests/test_autonomous_flow_scheduler_action_executor.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_AU_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/autonomous_flow_scheduler_action_executor.py:180:150 \
  --line-budget tests/test_autonomous_flow_scheduler_action_executor.py:220:190 \
  --line-budget tests/test_cli_autonomous_flow_action_output.py:220:190 \
  --required-evidence tests/test_autonomous_flow_scheduler_action_executor.py:recommended_next_action
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_AU_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_AU_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
