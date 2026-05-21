# Trial BL 上下文包：Attempt Route Auto Apply Core

目标：新增一个纯组合 core，把显式 scheduler attempt context 与既有 action route bind-and-apply 串起来，为后续无人调度入口提供可复放执行原语。本轮不接 CLI，不读取当前时间，不新增 artifact family。

## 1. 背景

Trial BJ 固化了稳定 attempt context core；Trial BK 暴露了显式 CLI 查询入口。当前无人调度器若想执行 route，仍需要先调用 attempt-context，再解析 `attempt_id`，再调用 `action-route-auto-apply`。这会把 orchestration 逻辑留在 shell 或外层 agent 中，容易出现解析差异。

本轮只在 Python core 层新增组合函数：显式输入 `issued_at` 和 `runner_id`，先构建 attempt context，ready 后调用既有 `bind_and_apply_phase5_scheduler_action_route(...)`。这不是让既有 auto-apply 隐式补 ID；它是一个新的、显式参数齐全的组合原语。

## 2. 本轮范围

必须做：

- 新增独立模块，例如 `src/ashare_evidence/autonomous_flow_scheduler_action_route_attempt_auto_apply.py`。
- 提供 typed result，例如 `Phase5SchedulerAttemptRouteApplyResult`。
- 提供函数，例如 `build_attempt_context_and_apply_phase5_scheduler_action_route(...)`。
- 函数输入：`plan`、`route`、`issued_at`、`runner_id`、可选 `root`。
- attempt context 使用显式 `cycle_id`、`issued_at`、`runner_id`；`cycle_id` 应与后续 apply 使用的 route/plan cycle 保持一致。
- 缺 `issued_at` 或 `runner_id` 时返回 typed blocked result，不调用 bind/apply，不写 artifact。
- ready 后将生成的 `attempt_id` 传给既有 `bind_and_apply_phase5_scheduler_action_route(...)`。
- 返回结果必须保留 `attempt_id`、`attempt_context_status`、`execution_status`、`preflight_status`、`applied_output`、`required_arguments`、`missing_arguments`、`diagnostic_id`、`execution_id`、`idempotency_key`、`cycle_event_recorded`、`reason`。
- 不读取当前时间，不使用 random/uuid，不调用 CLI，不解析 reason。
- 保持既有 `bind_and_apply_phase5_scheduler_action_route(...)` 缺 `attempt_id` fail-closed 行为不变。

不得做：

- 不修改 `action-route-auto-apply` CLI。
- 不让既有 `bind_and_apply_phase5_scheduler_action_route(...)` 自动生成 attempt id。
- 不新增 artifact family 或 registry ID。
- 不写 shell/orchestrator 解析逻辑。
- 不扩大现有 auto-apply 模块到 warning 线以上；必要时新模块承载组合逻辑。

## 3. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| BL1 | attempt route auto-apply core、测试、本评估文件 | 新增显式 attempt context + bind/apply 组合原语 |

## 4. 文件规模预算

- `src/ashare_evidence/autonomous_flow_scheduler_action_route_attempt_auto_apply.py`：hard 170，warning 130。
- `src/ashare_evidence/autonomous_flow_scheduler_action_route_auto_apply.py`：hard 170，warning 130，不建议修改。
- `tests/test_autonomous_flow_scheduler_action_route_attempt_auto_apply.py`：hard 220，warning 180。
- `tests/test_autonomous_flow_scheduler_action_route_auto_apply.py`：hard 220，warning 190，不建议扩写。
- `docs/contracts/autonomous-flow-trial/TRIAL_BL_EVALUATION_CN.md`：hard 140，warning 110。

如果达到 warning，必须拆分或压缩。

## 5. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_scheduler_action_route_attempt_auto_apply.py tests/test_autonomous_flow_scheduler_action_route_auto_apply.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/autonomous_flow_scheduler_action_route_attempt_auto_apply.py src/ashare_evidence/autonomous_flow_scheduler_action_route_auto_apply.py tests/test_autonomous_flow_scheduler_action_route_attempt_auto_apply.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_BL_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/autonomous_flow_scheduler_action_route_attempt_auto_apply.py:170:130 \
  --line-budget src/ashare_evidence/autonomous_flow_scheduler_action_route_auto_apply.py:170:130 \
  --line-budget tests/test_autonomous_flow_scheduler_action_route_attempt_auto_apply.py:220:180 \
  --line-budget tests/test_autonomous_flow_scheduler_action_route_auto_apply.py:220:190 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_BL_EVALUATION_CN.md:140:110 \
  --required-evidence tests/test_autonomous_flow_scheduler_action_route_attempt_auto_apply.py:test_attempt_route_auto_apply_blocks_missing_context_before_bind_or_apply \
  --forbidden-source-token src/ashare_evidence/autonomous_flow_scheduler_action_route_attempt_auto_apply.py:'datetime.now' \
  --forbidden-source-token src/ashare_evidence/autonomous_flow_scheduler_action_route_attempt_auto_apply.py:'uuid' \
  --forbidden-source-token src/ashare_evidence/autonomous_flow_scheduler_action_route_attempt_auto_apply.py:'random' \
  --forbidden-source-token src/ashare_evidence/autonomous_flow_scheduler_action_route_attempt_auto_apply.py:'route.reason =='
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BL_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BL_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
