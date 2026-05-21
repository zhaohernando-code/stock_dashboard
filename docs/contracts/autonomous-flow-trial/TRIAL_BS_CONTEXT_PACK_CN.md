# Trial BS 上下文包：CLI Attempt Run Recording Opt-in

目标：把 `phase5-local-cycle-step --output attempt-route-auto-apply` 接入 BR recorder，但必须通过显式开关启用。默认 CLI 输出与文件副作用保持不变。

## 1. 背景

BQ 建立了 attempt/run artifact store，BR 建立了 typed result 到 artifact 的 recorder。当前最后一段缺口是 CLI 仍只输出 apply result，不会写入 attempt/run 总结 artifact。

本轮只做 opt-in CLI 接入，不改变默认行为。用户后续可以让调度器开启该开关，实现每轮 attempt/run 的硬存储；旧脚本不打开开关时仍得到原始 apply result JSON。

## 2. 本轮范围

必须做：

- 为 `phase5-local-cycle-step` 增加 `--record-attempt-run` 显式开关。
- 可选增加 `--attempt-run-id`，用于显式覆盖 recorder 的 deterministic run id。
- handler 打开开关后调用 `record_phase5_scheduler_attempt_run_artifact`。
- 默认未打开开关时，`attempt-route-auto-apply` 输出 shape 与不写文件行为必须保持不变。
- 打开开关后输出 envelope，至少包含 `apply_result`、`attempt_run_artifact`、`attempt_run_artifact_path`、`attempt_run_record_status`。
- 如果缺少 recorder 必须的显式上下文，例如 `issued_at` 或 `runner_id`，不得崩溃；返回 blocked record envelope，不写 artifact，exit code 仍按 apply result blocked 语义处理。
- focused tests 覆盖默认不写、record 写入、record precondition blocked。

不得做：

- 不改变旧 `action-route-auto-apply`。
- 不让默认 `attempt-route-auto-apply` 产生新文件或 envelope。
- 不解析自然语言 reason。
- 不修改 `process_hardening.py`。

## 3. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| BS1 | CLI opt-in 接入、focused tests、本评估文件 | 显式开关下写 attempt/run artifact，默认保持兼容 |

## 4. 文件规模预算

- `src/ashare_evidence/cli_autonomous_flow.py`：hard 140，warning 125。
- `src/ashare_evidence/cli_autonomous_flow_output_context.py`：hard 120，warning 100。
- `src/ashare_evidence/cli_autonomous_flow_attempt_outputs.py`：hard 150，warning 120。
- `tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py`：hard 220，warning 180。
- `tests/helpers_cli_autonomous_flow_attempt_recording.py`：hard 160，warning 120。
- `tests/helpers_cli_autonomous_flow_attempt_route.py`：hard 160，warning 120。
- `docs/contracts/autonomous-flow-trial/TRIAL_BS_EVALUATION_CN.md`：hard 150，warning 120。

## 5. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py tests/test_scheduler_attempt_run_recorder.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_output_context.py src/ashare_evidence/cli_autonomous_flow_attempt_outputs.py tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py tests/helpers_cli_autonomous_flow_attempt_recording.py tests/helpers_cli_autonomous_flow_attempt_route.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_BS_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/cli_autonomous_flow.py:140:125 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_output_context.py:120:100 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_attempt_outputs.py:150:120 \
  --line-budget tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py:220:180 \
  --line-budget tests/helpers_cli_autonomous_flow_attempt_recording.py:160:120 \
  --line-budget tests/helpers_cli_autonomous_flow_attempt_route.py:160:120 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_BS_EVALUATION_CN.md:150:120 \
  --required-evidence tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py:test_attempt_route_auto_apply_output_default_does_not_record_attempt_run \
  --required-evidence tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py:test_attempt_route_auto_apply_output_records_attempt_run_when_enabled \
  --forbidden-source-token src/ashare_evidence/cli_autonomous_flow_attempt_outputs.py:"route.reason ==" \
  --forbidden-source-token src/ashare_evidence/cli_autonomous_flow_attempt_outputs.py:datetime.now \
  --forbidden-source-token src/ashare_evidence/cli_autonomous_flow_attempt_outputs.py:uuid \
  --forbidden-source-token src/ashare_evidence/cli_autonomous_flow_attempt_outputs.py:random
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BS_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BS_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
