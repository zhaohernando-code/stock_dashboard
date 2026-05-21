# Trial BT 评估记录：Scheduler Attempt Run Store Query

状态：verified
输入：`TRIAL_BT_CONTEXT_PACK_CN.md`
目标：评估 attempt/run store 的只读查询能力是否能支撑调度器和看板定位最近运行状态。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| BT1 | attempt run store query、focused tests、本评估文件 | 增加稳定的只读查询层 | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 查询语义完整性 | 35 |
| 稳定排序 | 25 |
| 空目录与缺失处理 | 15 |
| 范围隔离 | 15 |
| 验证完整性 | 10 |

自动重跑阈值：

- CLI 写入被修改。
- artifact schema 被修改。
- 从 reason 解析状态。
- 排序不稳定或 latest 不是最近记录。
- focused tests、ruff、process hardening、registry 或 full regression 失败。

## 3. BT1 结果

- `scheduler_attempt_run_artifact_store.py` 新增只读 list/latest helper。
- list 支持 `cycle_id`、`runner_id`、`attempt_status`、`apply_status` 过滤。
- 排序按 `issued_at`、`run_id` 倒序，latest 复用相同排序。
- 空 store 目录返回空列表，latest 返回 None。
- 未改 CLI、artifact schema、`process_hardening.py`，未解析 reason。

## 4. 主进程验证

- `PYTHONPATH=src python3 -m pytest tests/test_scheduler_attempt_run_artifact_store.py -q`：通过，6 passed。
- `ruff check src/ashare_evidence/scheduler_attempt_run_artifact_store.py tests/test_scheduler_attempt_run_artifact_store.py`：通过。
- `PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check ...`：通过，0 issues。
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check ...`：通过，0 issues。
- `PYTHONPATH=src python3 -m pytest -q`：通过，534 passed，147 deselected。

主进程语义复核：

- 查询函数只读取 artifact 文件，不写入、不改 schema、不触碰 CLI。
- 过滤条件均来自结构化字段：`cycle_id`、`runner_id`、`attempt_status`、`apply_status`。
- 排序按 `(issued_at, run_id)` 倒序，latest 与 list 共用同一路径。
- store 文件 114 行，距离 warning 120 只剩 6 行；后续若继续增加查询维度，应拆出 query module。

## 5. 重跑记录

- 无功能重跑；主进程补充 full regression 并通过。

## 6. 自评

- 查询语义完整，排序和 latest 共用同一查询路径。
- 变更限定在 BT1 owned files；下一轮必须避免继续膨胀 store 文件。
