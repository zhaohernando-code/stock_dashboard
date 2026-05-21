# Trial BZ 上下文包：CLI Attempt Follow-up Decision Output

目标：把 BY 的 attempt/run follow-up policy 暴露为只读 CLI 输出，形成 `attempt-run-readout -> follow-up decision` 的可观察链路。本轮不触发实际调度、不写 artifact。

## 1. 背景

BY 已能将 attempt/run readout 转换为 typed follow-up decision，但目前只能被 Python 代码调用。为了让自动化流程和 reviewer 能看见系统“下一步打算做什么”，需要一个 CLI 输出。

本轮新增 `--output attempt-run-followup-decision`。它读取 artifacts 生成 readout，再调用 policy 输出 decision。该输出是决策展示，不直接执行 recovery、retry 或调度。

## 2. 本轮范围

必须做：

- `phase5-local-cycle-step --output` 新增 `attempt-run-followup-decision`。
- 输出 BY decision JSON，exit code 为 0。
- 不调用 tick、plan、action、route、apply handlers。
- 不写 artifact。
- 新增 focused CLI tests 覆盖 blocked latest 和 empty store。

不得做：

- 不接实际调度执行。
- 不改 policy 语义。
- 不改 artifact schema。
- 不修改 `process_hardening.py`。

## 3. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| BZ1 | CLI decision output、focused tests、本评估文件 | 暴露无副作用的 attempt follow-up decision CLI |

## 4. 文件规模预算

- `src/ashare_evidence/cli_autonomous_flow.py`：hard 140，warning 125。
- `src/ashare_evidence/cli_autonomous_flow_outputs.py`：hard 160，warning 140。
- `src/ashare_evidence/cli_autonomous_flow_attempt_readout_outputs.py`：hard 120，warning 90。
- `tests/test_cli_autonomous_flow_attempt_followup_decision_output.py`：hard 220，warning 180。
- `docs/contracts/autonomous-flow-trial/TRIAL_BZ_EVALUATION_CN.md`：hard 150，warning 120。

## 5. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_attempt_followup_decision_output.py tests/test_scheduler_attempt_run_followup_policy.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_outputs.py src/ashare_evidence/cli_autonomous_flow_attempt_readout_outputs.py tests/test_cli_autonomous_flow_attempt_followup_decision_output.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_BZ_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/cli_autonomous_flow.py:140:125 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_outputs.py:160:140 \
  --line-budget src/ashare_evidence/cli_autonomous_flow_attempt_readout_outputs.py:120:90 \
  --line-budget tests/test_cli_autonomous_flow_attempt_followup_decision_output.py:220:180 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_BZ_EVALUATION_CN.md:150:120 \
  --required-evidence tests/test_cli_autonomous_flow_attempt_followup_decision_output.py:test_attempt_followup_decision_output_recommends_recovery_for_blocked_latest \
  --required-evidence tests/test_cli_autonomous_flow_attempt_followup_decision_output.py:test_attempt_followup_decision_output_handles_empty_store
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BZ_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BZ_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
