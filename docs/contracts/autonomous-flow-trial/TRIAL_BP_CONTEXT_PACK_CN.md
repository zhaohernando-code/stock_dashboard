# Trial BP 上下文包：CLI Attempt Route Test Split

目标：把 `tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py` 从临界行数中解耦，拆出共享 test helper 或分拆测试文件，让 BN 的 warning margin gate 能通过。本轮不改生产行为。

## 1. 背景

BN 新增 warning margin gate 后，BM 的 CLI 测试文件被准确识别为结构风险：178 行，warning 180，剩余 2 行，低于 minimum 5。BO 已处理 dispatcher 文件，本轮处理测试文件，避免后续 CLI 输出测试继续堆在同一个临界文件里。

## 2. 本轮范围

必须做：

- 降低 `tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py` 行数，使其 warning margin 至少保留 10 行。
- 优先新增 helper，例如 `tests/helpers_cli_autonomous_flow_attempt_route.py`，承接 `_FakeResult`、`_result`、`_apply_result` 或文件枚举 helper。
- 或者拆出新的 focused test 文件，但不能通过删除断言来降行数。
- 不修改生产代码。
- 不改变测试语义：仍覆盖 handler 顺序、参数透传、blocked 缺上下文不写 artifact、旧 bind/apply 不应进入。
- 不修改 `tests/test_cli_autonomous_flow_action_route_auto_apply_output.py`。

不得做：

- 不降低 warning margin 要求。
- 不删除关键断言。
- 不修改 CLI production code。
- 不新增 output 或 artifact 行为。

## 3. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| BP1 | attempt-route CLI 测试拆分、本评估文件 | 降低临界测试文件行数并保持语义 |

## 4. 文件规模预算

- `tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py`：hard 220，warning 180，margin minimum 10。
- 可选 helper `tests/helpers_cli_autonomous_flow_attempt_route.py`：hard 160，warning 120。
- `tests/test_cli_autonomous_flow_action_route_auto_apply_output.py`：hard 220，warning 190，不允许修改。
- `docs/contracts/autonomous-flow-trial/TRIAL_BP_EVALUATION_CN.md`：hard 150，warning 120。

如果主测试文件仍不满足 margin，必须继续拆分。

## 5. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py tests/test_cli_autonomous_flow_action_route_auto_apply_output.py -q
```

Ruff：

```bash
ruff check tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py tests/helpers_cli_autonomous_flow_attempt_route.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_BP_EVALUATION_CN.md \
  --line-budget tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py:220:180 \
  --line-budget tests/helpers_cli_autonomous_flow_attempt_route.py:160:120 \
  --line-budget tests/test_cli_autonomous_flow_action_route_auto_apply_output.py:220:190 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_BP_EVALUATION_CN.md:150:120 \
  --required-evidence tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py:test_attempt_route_auto_apply_output_blocks_missing_context_before_core_apply \
  --line-budget-warning-margin tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py:10
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BP_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BP_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
