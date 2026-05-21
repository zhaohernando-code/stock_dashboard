# Trial BM 上下文包：Attempt Route Auto Apply CLI Output

目标：把 Trial BL 的显式 attempt route auto apply core 暴露为 CLI 输出，让无人调度器可以一条命令完成 tick -> plan -> action -> route -> attempt context -> bind/apply，同时保持 `issued_at` 与 `runner_id` 显式输入，不读取当前时间。

## 1. 背景

Trial BL 已提供 `build_attempt_context_and_apply_phase5_scheduler_action_route(...)`，能用显式 `issued_at`、`runner_id` 生成 attempt context 并复用既有 bind/apply。当前缺口是 CLI 仍只有两类入口：`attempt-context` 只生成 ID，`action-route-auto-apply` 要求调用方提供 `attempt_id`。BM 新增一个更适合无人调度器的显式组合输出，但不能改变旧输出语义。

## 2. 本轮范围

必须做：

- 为 `phase5-local-cycle-step` 新增 `--output attempt-route-auto-apply`。
- 该输出执行顺序为 tick -> plan -> action -> route -> `build_attempt_context_and_apply_phase5_scheduler_action_route(...)`。
- 必须显式读取 `--issued-at` 与 `--runner-id`，缺任一参数时返回 typed blocked result，exit code 沿用 blocked action 口径。
- 输出 JSON 为组合 result 的 `model_dump(mode="json")`。
- 不读取当前时间，不使用 random/uuid，不自动生成 `issued_at` 或 `runner_id`。
- 不改变既有 `action-route-auto-apply`：缺 `attempt_id` 仍 blocked。
- 新增 handler 注入点或小 helper，避免让 CLI 分发函数变成大而难测的条件堆。

不得做：

- 不移除或改名 `attempt-context`、`action-route-auto-apply`。
- 不让旧 `action-route-auto-apply` 自动生成 attempt id。
- 不新增 artifact family 或 registry ID。
- 不解析自然语言 reason。
- 不扩写临界测试文件到 warning 以上；BM 新场景应放入独立测试文件。

## 3. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| BM1 | CLI attempt-route-auto-apply 输出、测试、本评估文件 | 暴露 BL core 为显式 CLI 组合输出 |

## 4. 文件规模预算

- `src/ashare_evidence/cli_autonomous_flow.py`：hard 190，warning 170。
- `src/ashare_evidence/cli_autonomous_flow_outputs.py`：hard 190，warning 160。
- `src/ashare_evidence/cli_autonomous_flow_action_outputs.py`：hard 180，warning 150。
- `src/ashare_evidence/cli_autonomous_flow_attempt_outputs.py`：hard 160，warning 120。
- `tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py`：hard 220，warning 180。
- `tests/test_cli_autonomous_flow_action_route_auto_apply_output.py`：hard 220，warning 190，不建议扩写。
- `docs/contracts/autonomous-flow-trial/TRIAL_BM_EVALUATION_CN.md`：hard 150，warning 120。

如果达到 warning，必须拆分或压缩。

## 5. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py tests/test_cli_autonomous_flow_action_route_auto_apply_output.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_outputs.py src/ashare_evidence/cli_autonomous_flow_action_outputs.py src/ashare_evidence/cli_autonomous_flow_attempt_outputs.py tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_BM_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/cli_autonomous_flow.py:190:170 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_outputs.py:190:160 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_action_outputs.py:180:150 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_attempt_outputs.py:160:120 \
  --line-budget tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py:220:180 \
  --line-budget tests/test_cli_autonomous_flow_action_route_auto_apply_output.py:220:190 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_BM_EVALUATION_CN.md:150:120 \
  --required-evidence tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py:test_attempt_route_auto_apply_output_blocks_missing_context_before_core_apply \
  --forbidden-source-token src/ashare_evidence/cli_autonomous_flow_attempt_outputs.py:'datetime.now' \
  --forbidden-source-token src/ashare_evidence/cli_autonomous_flow_attempt_outputs.py:'uuid' \
  --forbidden-source-token src/ashare_evidence/cli_autonomous_flow_attempt_outputs.py:'random' \
  --forbidden-source-token src/ashare_evidence/cli_autonomous_flow_attempt_outputs.py:'route.reason =='
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BM_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BM_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
