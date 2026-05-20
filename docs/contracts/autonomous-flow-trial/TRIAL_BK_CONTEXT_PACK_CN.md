# Trial BK 上下文包：Attempt Context CLI Output

目标：把 Trial BJ 的 scheduler attempt context core 暴露为显式 CLI 输出，让无人调度器可以用同一条可审计规则生成 `attempt_id`，但仍不改变 `action-route-auto-apply` 的 fail-closed 语义。

## 1. 背景

Trial BJ 已新增纯核心函数 `build_phase5_scheduler_attempt_context(...)`，要求调用方显式提供 `cycle_id`、`issued_at`、`runner_id`。当前缺口是 shell、cron、heartbeat 或外层 orchestrator 没有稳定 CLI 入口取得 attempt context，容易重新出现各处自行拼 ID 的分歧。

本轮只做显式查询入口，不做执行入口。`phase5-local-cycle-step --output action-route-auto-apply` 仍必须在缺少 `attempt_id` 时 blocked，避免 CLI 在执行路径里隐式生成不可审计状态。

## 2. 本轮范围

必须做：

- 为 `phase5-local-cycle-step` 新增 `--output attempt-context`。
- 新增 CLI 参数 `--runner-id`，仅供 attempt context 输出使用。
- `attempt-context` 输出调用 `build_phase5_scheduler_attempt_context(...)`。
- 输出 JSON 为 typed result 的 `model_dump(mode="json")`。
- 缺 `issued_at` 或 `runner_id` 时返回 core blocked result，exit code 使用现有 blocked action exit code 口径。
- ready 时 exit code 为 0。
- 不运行 tick，不读取 artifact root，不写 artifact，不调用 plan/action/route/apply/writer。
- 不读取当前时间，不使用 random/uuid，不自动推导 `issued_at`。
- 保持 `action-route-auto-apply` 缺 `attempt_id` 的 fail-closed 行为不变。

不得做：

- 不让 `action-route-auto-apply` 自动生成 `attempt_id`。
- 不新增 artifact family 或 registry ID。
- 不修改 scheduler action route core。
- 不扩大 `cli_autonomous_flow.py` 或 action output helper 到 warning 线以上；必要时拆分新 helper。

## 3. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| BK1 | CLI attempt context 输出、测试、本评估文件 | 以最小入口暴露 BJ core，不改变执行路径 |

## 4. 文件规模预算

- `src/ashare_evidence/cli_autonomous_flow.py`：hard 190，warning 170。
- `src/ashare_evidence/cli_autonomous_flow_outputs.py`：hard 180，warning 150。
- `src/ashare_evidence/cli_autonomous_flow_action_outputs.py`：hard 180，warning 150。
- 可选新 helper `src/ashare_evidence/cli_autonomous_flow_attempt_outputs.py`：hard 140，warning 110。
- `tests/test_cli_autonomous_flow_attempt_context_output.py`：hard 190，warning 160。
- `docs/contracts/autonomous-flow-trial/TRIAL_BK_EVALUATION_CN.md`：hard 140，warning 110。

如果达到 warning，必须拆分或压缩，不允许继续堆叠到既有接近 warning 的文件。

## 5. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_attempt_context_output.py tests/test_cli_autonomous_flow_action_route_auto_apply_output.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_outputs.py src/ashare_evidence/cli_autonomous_flow_action_outputs.py src/ashare_evidence/cli_autonomous_flow_attempt_outputs.py tests/test_cli_autonomous_flow_attempt_context_output.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_BK_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/cli_autonomous_flow.py:190:170 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_outputs.py:180:150 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_action_outputs.py:180:150 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_attempt_outputs.py:140:110 \
  --line-budget tests/test_cli_autonomous_flow_attempt_context_output.py:190:160 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_BK_EVALUATION_CN.md:140:110 \
  --required-evidence tests/test_cli_autonomous_flow_attempt_context_output.py:test_attempt_context_output_does_not_run_tick_or_apply \
  --forbidden-source-token src/ashare_evidence/cli_autonomous_flow_attempt_outputs.py:'datetime.now' \
  --forbidden-source-token src/ashare_evidence/cli_autonomous_flow_attempt_outputs.py:'uuid' \
  --forbidden-source-token src/ashare_evidence/cli_autonomous_flow_attempt_outputs.py:'random'
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BK_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BK_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
