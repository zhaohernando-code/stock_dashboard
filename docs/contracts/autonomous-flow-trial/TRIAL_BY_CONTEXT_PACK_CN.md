# Trial BY 上下文包：Attempt Run Follow-up Policy

目标：基于 BV/BW 的 attempt/run readout 生成纯策略 follow-up decision，用于自运行介入机制的下一步判断。本轮只做策略判断，不触发任务、不写 artifact、不改 CLI。

## 1. 背景

当前系统已经能写入 attempt/run artifact、查询最近状态、输出 readout。下一步需要把“看到 blocked / empty / applied 后怎么办”固化成结构化策略，而不是每个 agent 读 JSON 后自行解释。

本轮先建立纯 policy：输入 readout，输出 typed decision。后续调度器可以引用该 decision 决定是否继续跟踪、重试、打开 recovery ticket 或不动作。

## 2. 本轮范围

必须做：

- 新增独立模块，例如 `scheduler_attempt_run_followup_policy.py`。
- 提供 Pydantic decision model，字段至少包含：`decision_status`、`recommended_action`、`reason_code`、`source_latest_run_id`、`source_total_runs`、`blocking_reasons`、`confidence`。
- 输入只接受 `Phase5SchedulerAttemptRunReadout`。
- 策略建议：
  - 空 readout：`recommended_action=continue_tracking`，`reason_code=no_attempt_runs_recorded`。
  - latest blocked：`recommended_action=open_recovery_ticket`，`reason_code=latest_attempt_blocked`。
  - latest applied：`recommended_action=continue_tracking`，`reason_code=latest_attempt_applied`。
  - latest skipped：`recommended_action=continue_tracking`，`reason_code=latest_attempt_skipped`。
- 不解析 reason，不读取 artifact，不调用 CLI。
- 新增 focused tests 覆盖 empty、blocked、applied、skipped。

不得做：

- 不改 scheduler plan。
- 不改 CLI。
- 不写 artifact。
- 不修改 `process_hardening.py`。

## 3. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| BY1 | follow-up policy module、focused tests、本评估文件 | 生成自运行介入的 typed decision |

## 4. 文件规模预算

- `src/ashare_evidence/scheduler_attempt_run_followup_policy.py`：hard 180，warning 140。
- `tests/test_scheduler_attempt_run_followup_policy.py`：hard 220，warning 180。
- `docs/contracts/autonomous-flow-trial/TRIAL_BY_EVALUATION_CN.md`：hard 150，warning 120。

## 5. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_scheduler_attempt_run_followup_policy.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/scheduler_attempt_run_followup_policy.py tests/test_scheduler_attempt_run_followup_policy.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_BY_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/scheduler_attempt_run_followup_policy.py:180:140 \
  --line-budget tests/test_scheduler_attempt_run_followup_policy.py:220:180 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_BY_EVALUATION_CN.md:150:120 \
  --required-evidence tests/test_scheduler_attempt_run_followup_policy.py:test_attempt_run_followup_policy_recommends_tracking_for_empty_readout \
  --required-evidence tests/test_scheduler_attempt_run_followup_policy.py:test_attempt_run_followup_policy_recommends_recovery_for_blocked_latest \
  --forbidden-source-token src/ashare_evidence/scheduler_attempt_run_followup_policy.py:"reason ==" \
  --forbidden-source-token src/ashare_evidence/scheduler_attempt_run_followup_policy.py:datetime.now \
  --forbidden-source-token src/ashare_evidence/scheduler_attempt_run_followup_policy.py:uuid \
  --forbidden-source-token src/ashare_evidence/scheduler_attempt_run_followup_policy.py:random
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BY_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BY_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
