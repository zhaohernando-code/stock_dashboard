# Trial BJ 上下文包：Scheduler Attempt Context Core

目标：新增一个纯核心层，用显式输入生成稳定的 scheduler attempt context。它为后续无人调度器提供统一 `attempt_id` 生成规则，避免每个 CLI wrapper 或 cron/heartbeat 自己拼 ID；本轮不读当前时间、不接 CLI、不写 artifact。

## 1. 背景

Trial BF/BG 已让 `phase5-local-cycle-step --output action-route-auto-apply` 通过 `attempt_id` 与 `issued_at` 完成 bind-and-apply。当前问题是：调用方仍需要自行构造 `attempt_id`。如果后续多个 scheduler wrapper 各自拼 ID，会再次出现不可审计和不可复放的分歧。本轮先做一个小而稳定的 core：显式传入 `cycle_id`、`issued_at`、`runner_id`，返回 typed attempt context。

## 2. 本轮范围

必须做：

- 新增独立模块，例如 `src/ashare_evidence/autonomous_flow_scheduler_attempt.py`。
- 提供 typed result，例如 `Phase5SchedulerAttemptContextResult`。
- 提供函数，例如 `build_phase5_scheduler_attempt_context(...)`。
- 输入至少包含 `cycle_id`、`issued_at`、可选 `runner_id`。
- 缺 `cycle_id`、`issued_at` 或 `runner_id` 时返回 typed blocked result，不抛异常。
- ready result 必须包含 `attempt_id`、`cycle_id`、`issued_at`、`runner_id`、`required_arguments`、`missing_arguments`、`reason`。
- `attempt_id` 必须稳定、文件名安全，并包含可读语义前缀：cycle slug、runner slug、issued_at slug，以及短 digest。
- digest 输入必须包含原始 `cycle_id`、`runner_id`、`issued_at`，避免 slug 碰撞。
- 不读取当前时间，不生成随机数，不写 artifact，不调用 CLI，不调用 route/apply/writer。
- 空字符串视为缺失。

不得做：

- 不改变 `action-route-auto-apply` CLI 的 fail-closed 行为。
- 不让 CLI 自动生成 `attempt_id`。
- 不新增 artifact family。
- 不解析自然语言 reason。

## 3. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| BJ1 | attempt context core、测试、本评估文件 | 新增稳定 attempt context core |

## 4. 文件规模预算

- `src/ashare_evidence/autonomous_flow_scheduler_attempt.py`：hard 180，warning 150。
- `tests/test_autonomous_flow_scheduler_attempt.py`：hard 220，warning 190。
- `docs/contracts/autonomous-flow-trial/TRIAL_BJ_EVALUATION_CN.md`：hard 140，warning 110。

如果达到 warning，必须拆分或压缩。

## 5. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_scheduler_attempt.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/autonomous_flow_scheduler_attempt.py tests/test_autonomous_flow_scheduler_attempt.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_BJ_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/autonomous_flow_scheduler_attempt.py:180:150 \
  --line-budget tests/test_autonomous_flow_scheduler_attempt.py:220:190 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_BJ_EVALUATION_CN.md:140:110 \
  --required-evidence tests/test_autonomous_flow_scheduler_attempt.py:test_attempt_context_blocks_missing_inputs_without_io \
  --forbidden-source-token src/ashare_evidence/autonomous_flow_scheduler_attempt.py:'datetime.now' \
  --forbidden-source-token src/ashare_evidence/autonomous_flow_scheduler_attempt.py:'uuid' \
  --forbidden-source-token src/ashare_evidence/autonomous_flow_scheduler_attempt.py:'random'
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BJ_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BJ_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
