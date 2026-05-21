# Trial BT 上下文包：Scheduler Attempt Run Store Query

目标：为 `phase5_scheduler_attempt_run` store 增加只读查询能力，让调度器、reviewer 和未来看板能按 cycle、runner、状态快速定位最近的 attempt/run 记录。本轮不改 CLI 写入。

## 1. 背景

BS 已能在显式开关下把 CLI attempt run 写入 artifact，但当前 store 仍主要支持按 run id 读取。真正自运行时，系统需要回答“某个 cycle 最近一次 run 是什么状态”、“是否已经有同 runner 的 blocked 记录”、“看板怎么列出最近 attempt runs”等问题。

如果每个调用方都自己扫目录并过滤，就会出现重复 IO、排序不一致和状态判断散落的问题。本轮把这部分收敛为 store 层只读查询。

## 2. 本轮范围

必须做：

- 在 `scheduler_attempt_run_artifact_store.py` 增加 list/query 函数，读取已存在的 attempt/run artifacts。
- 支持按 `cycle_id`、`runner_id`、`attempt_status`、`apply_status` 过滤。
- 排序必须稳定，优先按 `issued_at`、再按 `run_id` 倒序，保证最近记录在前。
- 提供 `find_latest_phase5_scheduler_attempt_run_artifact(...)` 之类的 latest helper。
- 忽略不存在的目录，返回空列表或 None。
- 新增 focused tests 覆盖空目录、稳定排序、过滤、latest。

不得做：

- 不改 CLI 写入。
- 不修改 artifact schema。
- 不解析 reason。
- 不修改 `process_hardening.py`。

## 3. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| BT1 | attempt run store query、focused tests、本评估文件 | 增加稳定的只读查询层 |

## 4. 文件规模预算

- `src/ashare_evidence/scheduler_attempt_run_artifact_store.py`：hard 160，warning 120。
- `tests/test_scheduler_attempt_run_artifact_store.py`：hard 220，warning 180。
- `docs/contracts/autonomous-flow-trial/TRIAL_BT_EVALUATION_CN.md`：hard 150，warning 120。

## 5. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_scheduler_attempt_run_artifact_store.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/scheduler_attempt_run_artifact_store.py tests/test_scheduler_attempt_run_artifact_store.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_BT_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/scheduler_attempt_run_artifact_store.py:160:120 \
  --line-budget tests/test_scheduler_attempt_run_artifact_store.py:220:180 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_BT_EVALUATION_CN.md:150:120 \
  --required-evidence tests/test_scheduler_attempt_run_artifact_store.py:test_list_attempt_run_artifacts_filters_and_sorts \
  --required-evidence tests/test_scheduler_attempt_run_artifact_store.py:test_find_latest_attempt_run_artifact_returns_none_for_empty_store \
  --forbidden-source-token src/ashare_evidence/scheduler_attempt_run_artifact_store.py:"reason ==" \
  --forbidden-source-token src/ashare_evidence/scheduler_attempt_run_artifact_store.py:datetime.now \
  --forbidden-source-token src/ashare_evidence/scheduler_attempt_run_artifact_store.py:uuid \
  --forbidden-source-token src/ashare_evidence/scheduler_attempt_run_artifact_store.py:random
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BT_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BT_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
