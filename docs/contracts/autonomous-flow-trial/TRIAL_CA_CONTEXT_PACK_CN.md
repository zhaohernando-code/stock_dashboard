# Trial CA 上下文包：CLI Output Dispatcher Split

目标：降低 `cli_autonomous_flow_outputs.py` 的增长风险，把 action/attempt/readout 分支迁移到独立 dispatcher helper。保持 CLI 行为不变。

## 1. 背景

BZ 后 `cli_autonomous_flow_outputs.py` 为 128 行，距离 warning 140 只剩 12 行。该文件是所有 output 的中央 if 链，继续新增输出会反复触碰同一基座文件。

本轮做结构减压：新增 output dispatch helper 模块，主 dispatcher 只保留基础 status/plan/dry-run 和最终 fallback；复杂分支交给 helper 处理。

## 2. 本轮范围

必须做：

- 新增 `cli_autonomous_flow_output_dispatch.py` 或类似模块。
- 将 action、attempt、diagnostic、execution 等 output 分支迁移到 helper。
- `cli_autonomous_flow_outputs.py` 行数恢复至少 25 行 warning margin。
- focused tests 覆盖现有 CLI output 关键路径。

不得做：

- 不新增 CLI output。
- 不改任何 output shape。
- 不改 artifact schema。
- 不修改 `process_hardening.py`。

## 3. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| CA1 | dispatcher split、focused tests、本评估文件 | 保持行为不变并降低 dispatcher 文件增长风险 |

## 4. 文件规模预算

- `src/ashare_evidence/cli_autonomous_flow_outputs.py`：hard 160，warning 140，warning margin minimum 25。
- `src/ashare_evidence/cli_autonomous_flow_output_dispatch.py`：hard 180，warning 140。
- `tests/test_cli_autonomous_flow_attempt_followup_decision_output.py`：hard 220，warning 180。
- `tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py`：hard 220，warning 180。
- `docs/contracts/autonomous-flow-trial/TRIAL_CA_EVALUATION_CN.md`：hard 150，warning 120。

## 5. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_attempt_followup_decision_output.py tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py tests/test_cli_autonomous_flow_action_route_apply_output.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/cli_autonomous_flow_outputs.py src/ashare_evidence/cli_autonomous_flow_output_dispatch.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_CA_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/cli_autonomous_flow_outputs.py:160:140 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_output_dispatch.py:180:140 \
  --line-budget tests/test_cli_autonomous_flow_attempt_followup_decision_output.py:220:180 \
  --line-budget tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py:220:180 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_CA_EVALUATION_CN.md:150:120 \
  --line-budget-warning-margin src/ashare_evidence/cli_autonomous_flow_outputs.py:25 \
  --required-evidence tests/test_cli_autonomous_flow_attempt_followup_decision_output.py:test_attempt_followup_decision_output_recommends_recovery_for_blocked_latest \
  --required-evidence tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py:test_attempt_route_auto_apply_output_default_does_not_record_attempt_run
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_CA_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_CA_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
