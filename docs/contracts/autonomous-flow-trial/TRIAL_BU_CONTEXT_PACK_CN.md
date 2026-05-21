# Trial BU 上下文包：Attempt Run Query Module Split

目标：把 BT 加入 store 的查询实现迁移到独立 query 模块，降低 `scheduler_attempt_run_artifact_store.py` 的增长压力。保持 public import 兼容，不改变查询行为。

## 1. 背景

BT 后 `scheduler_attempt_run_artifact_store.py` 为 114 行，距离 warning 120 只剩 6 行。后续看板、调度器和 reviewer 都会继续增加查询维度，如果继续把逻辑塞进 store，会快速变成不可维护的基座文件。

本轮不新增业务能力，只做模块边界调整：store 保留 write/read/read-if-exists 与兼容 re-export，查询扫描、过滤、排序迁移到 `scheduler_attempt_run_artifact_queries.py`。

## 2. 本轮范围

必须做：

- 新增独立 query 模块承载 list/latest 查询实现。
- store 模块保留原有 query 函数名的 import/re-export，避免破坏调用方。
- focused tests 行为不变；必要时新增针对 query module 直接 import 的轻量断言。
- 文件预算要让 store 恢复充足 margin。

不得做：

- 不改 CLI。
- 不改 artifact schema。
- 不改查询语义或排序。
- 不修改 `process_hardening.py`。

## 3. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| BU1 | query module split、focused tests、本评估文件 | 保持行为不变并降低 store 文件增长风险 |

## 4. 文件规模预算

- `src/ashare_evidence/scheduler_attempt_run_artifact_store.py`：hard 160，warning 120，warning margin minimum 20。
- `src/ashare_evidence/scheduler_attempt_run_artifact_queries.py`：hard 160，warning 120。
- `tests/test_scheduler_attempt_run_artifact_store.py`：hard 220，warning 180。
- `docs/contracts/autonomous-flow-trial/TRIAL_BU_EVALUATION_CN.md`：hard 150，warning 120。

## 5. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_scheduler_attempt_run_artifact_store.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/scheduler_attempt_run_artifact_store.py src/ashare_evidence/scheduler_attempt_run_artifact_queries.py tests/test_scheduler_attempt_run_artifact_store.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_BU_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/scheduler_attempt_run_artifact_store.py:160:120 \
  --line-budget src/ashare_evidence/scheduler_attempt_run_artifact_queries.py:160:120 \
  --line-budget tests/test_scheduler_attempt_run_artifact_store.py:220:180 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_BU_EVALUATION_CN.md:150:120 \
  --line-budget-warning-margin src/ashare_evidence/scheduler_attempt_run_artifact_store.py:20 \
  --required-evidence tests/test_scheduler_attempt_run_artifact_store.py:test_list_attempt_run_artifacts_filters_and_sorts \
  --required-evidence tests/test_scheduler_attempt_run_artifact_store.py:test_find_latest_attempt_run_artifact_returns_none_for_empty_store
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BU_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BU_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
