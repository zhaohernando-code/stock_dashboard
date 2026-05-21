# Trial BQ 上下文包：Scheduler Attempt Run Artifact Store

目标：为一次 scheduler attempt/run 增加可持久化的总结 artifact 与读写存储层。它用于保存 attempt context、route、preflight、apply 结果的稳定摘要，后续 CLI 或调度器可以在此基础上恢复状态。本轮只做模型与 store，不把 CLI 写盘接入。

## 1. 背景

BM 已提供 `attempt-route-auto-apply` 输出，能在一条命令里完成 tick、plan、action、route、attempt context、preflight 与 apply。当前缺口是：这次 run 的整体结果只存在于 CLI JSON 输出里，没有统一 artifact 可被下一轮调度、reviewer 或看板读取。

这会影响用户最初要求的“运行中状态硬存储”和“不跑偏”：如果进程中断，系统只能依赖日志或重新推导，无法稳定知道某个 attempt 是否 blocked、skipped 或 applied。

## 2. 本轮范围

必须做：

- 新增独立模型模块，承载 `phase5_scheduler_attempt_run` artifact，避免继续膨胀 `autonomous_flow_artifacts.py`。
- 新增独立 store 模块，提供 write、read、read-if-exists。
- 更新 artifact folder 映射、registry 与 schema，使 artifact family 被正式注册。
- artifact 字段需要覆盖：run id、attempt id、cycle id、runner id、issued at、attempt status、route type、preflight status、apply status、applied output、required/missing arguments、diagnostic id、execution id、idempotency key、cycle event、error type、reason、blocking reasons、event refs。
- 字段验证需要去重 refs，并拒绝或清洗敏感 diagnostic token。
- 使用显式输入，不引入本地时间、随机数或 UUID。
- 新增 focused tests 覆盖写读、missing 返回 None、结构化 apply 摘要字段、敏感字段防护、refs 去重。

不得做：

- 不把 CLI `attempt-route-auto-apply` 接入写盘。
- 不解析自然语言 reason 来推断结构化状态。
- 不修改 `src/ashare_evidence/process_hardening.py`。
- 不扩大已有 near-warning 文件。

## 3. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| BQ1 | attempt run artifact model、store、schema、registry、focused tests、本评估文件 | 建立可持久化的 attempt/run 总结底座 |

## 4. 文件规模预算

- `src/ashare_evidence/scheduler_attempt_run_artifacts.py`：hard 180，warning 140。
- `src/ashare_evidence/scheduler_attempt_run_artifact_store.py`：hard 160，warning 120。
- `tests/test_scheduler_attempt_run_artifact_store.py`：hard 220，warning 180。
- `docs/contracts/registry/schemas/phase5_scheduler_attempt_run.schema.json`：hard 220，warning 180。
- `docs/contracts/autonomous-flow-trial/TRIAL_BQ_EVALUATION_CN.md`：hard 150，warning 120。

## 5. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_scheduler_attempt_run_artifact_store.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/scheduler_attempt_run_artifacts.py src/ashare_evidence/scheduler_attempt_run_artifact_store.py tests/test_scheduler_attempt_run_artifact_store.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_BQ_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/scheduler_attempt_run_artifacts.py:180:140 \
  --line-budget src/ashare_evidence/scheduler_attempt_run_artifact_store.py:160:120 \
  --line-budget tests/test_scheduler_attempt_run_artifact_store.py:220:180 \
  --line-budget docs/contracts/registry/schemas/phase5_scheduler_attempt_run.schema.json:220:180 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_BQ_EVALUATION_CN.md:150:120 \
  --required-evidence tests/test_scheduler_attempt_run_artifact_store.py:test_write_read_and_missing_scheduler_attempt_run_artifact \
  --required-evidence tests/test_scheduler_attempt_run_artifact_store.py:test_scheduler_attempt_run_rejects_sensitive_identity_fields \
  --forbidden-source-token src/ashare_evidence/scheduler_attempt_run_artifacts.py:datetime.now \
  --forbidden-source-token src/ashare_evidence/scheduler_attempt_run_artifacts.py:uuid \
  --forbidden-source-token src/ashare_evidence/scheduler_attempt_run_artifacts.py:random \
  --forbidden-source-token src/ashare_evidence/scheduler_attempt_run_artifact_store.py:datetime.now \
  --forbidden-source-token src/ashare_evidence/scheduler_attempt_run_artifact_store.py:uuid \
  --forbidden-source-token src/ashare_evidence/scheduler_attempt_run_artifact_store.py:random
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BQ_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BQ_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
