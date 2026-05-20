# Trial BE 上下文包：Scheduler Action Route Bind-and-Apply Core

目标：新增一个核心 bind-and-apply 层，把 Trial BD 的参数绑定与 Trial BA 的 route apply 串成一个可复用调用点。它让无人调度器只需提供 plan、route、attempt id、issued_at 和 root，即可得到 typed apply result。本轮不接 CLI，不生成时间，不新增 writer 语义。

## 1. 背景

Trial BD 提供纯参数绑定，Trial BA 提供核心 route apply。下一步调度器如果分别调用二者，仍需要自己处理 binding blocked、参数字典映射和 diagnostic refs 传递。为避免上层重复拼分支，本轮新增 core façade：先 bind，再 apply。

该 façade 必须仍保持可重放：`issued_at` 与 `attempt_id` 都由调用方显式传入，不读取当前时间。

## 2. 本轮范围

必须做：

- 新增独立模块，例如 `src/ashare_evidence/autonomous_flow_scheduler_action_route_auto_apply.py`。
- 提供函数，例如 `bind_and_apply_phase5_scheduler_action_route(...)`。
- 输入：`Phase5SchedulerFollowupPlan`、`Phase5SchedulerActionRouteResult`、`attempt_id`、可选 `issued_at`、可选 `root`。
- 先调用 `bind_phase5_scheduler_action_route_arguments(...)`。
- binding blocked 时返回 `Phase5SchedulerActionRouteApplyResult` typed blocked，不调用 apply，不写 artifact。
- binding ready 时调用 `apply_phase5_scheduler_action_route(...)`。
- 参数映射必须来自 binding result 的 `provided_arguments`。
- execution route 的 `diagnostic_refs` 为空；本层不把 diagnostic id 伪造为 execution diagnostic ref。
- `wait_for_next_tick` / `terminal` 经 binding ready 后 apply，应返回 skipped/no-op。
- 不读取当前时间，不生成随机数，不写 artifact，除非 apply core 根据 ready route 调用现有 writer。
- 不修改 binding、route apply core、route mapping 或 route preflight 语义。

不得做：

- 不接 CLI。
- 不新增参数生成规则。
- 不直接调用 diagnostic/execution writer。
- 不解析 route reason 自然语言。

## 3. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| BE1 | bind-and-apply core、测试、本评估文件 | 新增核心组合层 |

子进程注意：本层是 façade，只组合 BD/BA，不重写它们的内部逻辑。

## 4. 文件规模预算

- `src/ashare_evidence/autonomous_flow_scheduler_action_route_auto_apply.py`：hard 160，warning 130。
- `tests/test_autonomous_flow_scheduler_action_route_auto_apply.py`：hard 220，warning 190。
- `src/ashare_evidence/autonomous_flow_scheduler_action_route_arguments.py`：hard 180，warning 150，不建议修改。
- `src/ashare_evidence/autonomous_flow_scheduler_action_route_executor.py`：hard 180，warning 150，不建议修改。
- `tests/test_autonomous_flow_scheduler_action_route_executor.py`：hard 220，warning 190，不得修改。

如果达到 warning，必须拆分或压缩。

## 5. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_scheduler_action_route_auto_apply.py tests/test_autonomous_flow_scheduler_action_route_arguments.py tests/test_autonomous_flow_scheduler_action_route_executor.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/autonomous_flow_scheduler_action_route_auto_apply.py tests/test_autonomous_flow_scheduler_action_route_auto_apply.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_BE_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/autonomous_flow_scheduler_action_route_auto_apply.py:160:130 \
  --line-budget tests/test_autonomous_flow_scheduler_action_route_auto_apply.py:220:190 \
  --line-budget src/ashare_evidence/autonomous_flow_scheduler_action_route_arguments.py:180:150 \
  --line-budget src/ashare_evidence/autonomous_flow_scheduler_action_route_executor.py:180:150 \
  --line-budget tests/test_autonomous_flow_scheduler_action_route_executor.py:220:190 \
  --required-evidence tests/test_autonomous_flow_scheduler_action_route_auto_apply.py:test_bind_and_apply_blocks_without_issued_at_before_apply
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BE_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BE_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
