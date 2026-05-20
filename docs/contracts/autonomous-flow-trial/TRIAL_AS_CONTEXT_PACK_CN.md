# Trial AS 上下文包：CLI No-op Action Output

目标：把 Trial AR 的 no-op scheduler action executor 接入 `phase5-local-cycle-step`，形成可调用的 CLI 输出模式。本轮只暴露无副作用 action 执行结果，不执行 ledger/durable write action。

## 1. 背景

当前 CLI 已支持：

- `status`：输出 tick envelope。
- `plan`：输出 scheduler follow-up plan。
- `dry-run`：输出无副作用计划预览。
- `diagnostic`：写 diagnostic artifact。
- `execution`：写 scheduler execution ledger。
- `full`：输出 service result。

Trial AR 新增了 `execute_phase5_scheduler_noop_action(plan)`，但还没有入口可由调度命令调用。AS 的目标是建立最小可调用入口，让平台可以在无需人工介入时推进无副作用 action，同时仍阻止真实写入 action 越权执行。

## 2. 本轮范围

必须做：

- 为 `phase5-local-cycle-step` 新增输出模式，例如 `--output action`。
- CLI handler 运行顺序必须是 `tick -> plan -> execute_phase5_scheduler_noop_action`。
- `--output action` 不要求 `--execution-id`、`--idempotency-key`、`--created-at`。
- `--output action` 不调用 dry-run、diagnostic、execution ledger 或 full service。
- happy path 真实 artifact root 应输出 `execution_mode="contract_action"`、`execution_status="completed"`、`action="continue_tracking"`。
- missing cycle / recovery action 等非 no-op plan 应输出 typed `blocked` action result，而不是写 recovery ticket 或 ledger。
- 新增测试应放在独立文件，避免继续膨胀已有 CLI 测试文件。
- 更新 help 文案，避免把 action output 描述成 ledger execution。

不得做：

- 不修改 action executor 语义，除非发现无法接入且需要在评估中说明。
- 不写 execution ledger/reservation。
- 不写 recovery ticket、projection、cycle closeout 或 diagnostic artifact。
- 不新增真实 durable output action。
- 不改变既有 `execution` output 的 required args 和幂等冲突语义。

## 3. 建议实现

建议修改：

- `src/ashare_evidence/cli_autonomous_flow.py`
- `src/ashare_evidence/cli_autonomous_flow_outputs.py`

建议新增：

- `tests/test_cli_autonomous_flow_action_output.py`

建议 handler dataclass 增加：

```python
execute_scheduler_noop_action: Callable[..., Any]
```

建议 output branch：

```python
if args.output == "action":
    tick_result = _run_tick_from_args(args, handlers)
    plan = handlers.plan_followup(tick_result)
    action_result = handlers.execute_scheduler_noop_action(plan)
    _print_json(action_result.model_dump(mode="json"))
    return 0
```

## 4. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| AS1 | CLI action output、测试、本评估文件 | 接入 no-op action executor |

子进程必须注意：这是入口接入任务，不是扩展真实写入能力。任何 ledger、diagnostic、recovery ticket、projection 或 closeout 写入都视为跑偏。

## 5. 文件规模预算

- `src/ashare_evidence/cli_autonomous_flow.py`：hard 100，warning 90。
- `src/ashare_evidence/cli_autonomous_flow_outputs.py`：hard 240，warning 220。
- `tests/test_cli_autonomous_flow_action_output.py`：hard 220，warning 190。
- `tests/test_cli_autonomous_flow_execution.py`：hard 220，warning 200，不建议修改。
- `tests/test_cli_autonomous_flow_smoke.py`：hard 220，warning 200，不建议修改。

如果达到 warning，必须拆分或缩小实现。

## 6. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_action_output.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_outputs.py tests/test_cli_autonomous_flow_action_output.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_AS_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/cli_autonomous_flow.py:100:90 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_outputs.py:240:220 \
  --line-budget tests/test_cli_autonomous_flow_action_output.py:220:190 \
  --required-evidence tests/test_cli_autonomous_flow_action_output.py:test_phase5_local_cycle_step_action_output_calls_noop_executor_only
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_AS_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_AS_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
