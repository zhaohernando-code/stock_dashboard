# Trial BR 上下文包：Scheduler Attempt Run Recorder

目标：把 BM/BL 的 typed attempt route apply result 转换并记录为 BQ 的 `phase5_scheduler_attempt_run` artifact。该层只做结构化映射和 store 写入，为后续 CLI 或调度器接入硬存储提供薄入口。

## 1. 背景

BQ 已建立 attempt/run 总结 artifact 与 store，但还没有把现有 `Phase5SchedulerAttemptRouteApplyResult` 接入持久化模型。当前 CLI 输出和 artifact store 之间仍靠人工理解字段关系，后续接入 CLI 写盘时容易把映射逻辑散落在 dispatcher 里。

本轮补一个独立 recorder：它从 typed result 读取结构化字段，结合显式 `runner_id`、`issued_at`、可选 `run_id`，产出并写入 `phase5_scheduler_attempt_run`。如果未传 `run_id`，允许使用确定性的 run id builder，但不得使用本地时间、随机数或 UUID。

## 2. 本轮范围

必须做：

- 新增独立 recorder 模块，例如 `scheduler_attempt_run_recorder.py`。
- 提供纯 builder：从 `Phase5SchedulerAttemptRouteApplyResult` 生成 `Phase5SchedulerAttemptRunArtifact`，不写盘。
- 提供 recorder：调用 builder 后写入 store，并返回 artifact 与路径等结构化结果。
- run id 必须显式传入或由结构化输入确定性生成。
- 映射字段必须来自 typed result：attempt status、route type、preflight status、apply status、applied output、required/missing arguments、diagnostic/execution/idempotency、cycle event、reason、error type。
- blocking reasons 不能解析 reason；可以使用显式输入，或从 `missing_arguments` 这类结构化字段降级生成。
- 新增 focused tests 覆盖 applied、blocked missing context、deterministic id、写读。

不得做：

- 不接 CLI 写盘。
- 不解析自然语言 reason。
- 不修改 BQ schema，除非发现 schema 与 recorder 必须字段不一致。
- 不修改 `process_hardening.py`。

## 3. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| BR1 | recorder module、focused tests、本评估文件 | 建立 typed result 到 attempt/run artifact 的稳定映射层 |

## 4. 文件规模预算

- `src/ashare_evidence/scheduler_attempt_run_recorder.py`：hard 180，warning 140。
- `tests/test_scheduler_attempt_run_recorder.py`：hard 240，warning 190。
- `docs/contracts/autonomous-flow-trial/TRIAL_BR_EVALUATION_CN.md`：hard 150，warning 120。

## 5. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_scheduler_attempt_run_recorder.py tests/test_scheduler_attempt_run_artifact_store.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/scheduler_attempt_run_recorder.py tests/test_scheduler_attempt_run_recorder.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_BR_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/scheduler_attempt_run_recorder.py:180:140 \
  --line-budget tests/test_scheduler_attempt_run_recorder.py:240:190 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_BR_EVALUATION_CN.md:150:120 \
  --required-evidence tests/test_scheduler_attempt_run_recorder.py:test_build_attempt_run_artifact_from_applied_result \
  --required-evidence tests/test_scheduler_attempt_run_recorder.py:test_record_attempt_run_artifact_writes_store \
  --forbidden-source-token src/ashare_evidence/scheduler_attempt_run_recorder.py:datetime.now \
  --forbidden-source-token src/ashare_evidence/scheduler_attempt_run_recorder.py:uuid \
  --forbidden-source-token src/ashare_evidence/scheduler_attempt_run_recorder.py:random \
  --forbidden-source-token src/ashare_evidence/scheduler_attempt_run_recorder.py:"route.reason =="
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BR_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BR_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
