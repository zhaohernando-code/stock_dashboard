# Trial AY 上下文包：Action Route Apply Preflight

目标：为 action follow-up route 增加纯 preflight，判断 route 所需参数是否已经由调度器提供。该 preflight 只返回 typed ready/blocked，不生成参数、不执行 route。

## 1. 背景

Trial AV 新增了 `route_phase5_scheduler_action_result(...)`，Trial AW 将 route 暴露为 `--output action-route`。route result 已声明 `required_arguments`，但上层调度器仍需要自行判断是否具备这些参数。

无人化流程需要一个标准 preflight，避免 shell/cron/agent 在缺少 `diagnostic_id`、`observed_at`、`execution_id`、`idempotency_key` 或 `created_at` 时继续执行到错误路径。

## 2. 本轮范围

必须做：

- 新增纯函数，例如 `preflight_phase5_scheduler_action_route(...)`。
- 输入 `Phase5SchedulerActionRouteResult` 和 `provided_argument_names`。
- 输出 typed result，至少包含 `cycle_id`、`route_type`、`status`、`missing_arguments`、`required_arguments`、`ready`、`reason`。
- `terminal` 和 `wait_for_next_tick` 无 required args，应返回 ready。
- `diagnostic_output` 缺 `diagnostic_id` 或 `observed_at` 时 blocked。
- `execution_output` 缺 `execution_id`、`idempotency_key` 或 `created_at` 时 blocked。
- 不修改 route result 输入对象。
- 不生成 ID/timestamp，不读取当前时间，不写 artifact，不调用 CLI/writer。

不得做：

- 不执行 diagnostic/ledger/recovery/projection/closeout。
- 不修改 CLI。
- 不修改 action executor/result 语义。
- 不解析 route reason 自然语言。

## 3. 建议实现

建议放在 `autonomous_flow_scheduler_action_router.py`，但如文件接近 warning，拆出独立模块。

建议模型：

```python
Phase5SchedulerActionRoutePreflightStatus = Literal["ready", "blocked"]

class Phase5SchedulerActionRoutePreflightResult(BaseModel):
    cycle_id: str
    route_type: Phase5SchedulerActionRouteType
    status: Phase5SchedulerActionRoutePreflightStatus
    required_arguments: tuple[str, ...]
    missing_arguments: tuple[str, ...]
    reason: str

    @property
    def ready(self) -> bool: ...
```

## 4. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| AY1 | route preflight、tests、本评估文件 | 新增 route apply preflight |

子进程注意：这是 apply 前检查，不是 apply 执行。

## 5. 文件规模预算

- `src/ashare_evidence/autonomous_flow_scheduler_action_router.py`：hard 180，warning 150。
- `tests/test_autonomous_flow_scheduler_action_router.py`：hard 240，warning 210。
- 可选新测试文件 `tests/test_autonomous_flow_scheduler_action_route_preflight.py`：hard 180，warning 150。

如果任一文件达到 warning，必须拆分。

## 6. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_scheduler_action_router.py tests/test_autonomous_flow_scheduler_action_route_preflight.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/autonomous_flow_scheduler_action_router.py tests/test_autonomous_flow_scheduler_action_router.py tests/test_autonomous_flow_scheduler_action_route_preflight.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_AY_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/autonomous_flow_scheduler_action_router.py:180:150 \
  --line-budget tests/test_autonomous_flow_scheduler_action_router.py:240:210 \
  --line-budget tests/test_autonomous_flow_scheduler_action_route_preflight.py:180:150 \
  --required-evidence tests/test_autonomous_flow_scheduler_action_route_preflight.py:test_action_route_preflight_blocks_missing_diagnostic_arguments
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_AY_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_AY_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
