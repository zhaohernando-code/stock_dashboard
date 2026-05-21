# Trial BU 评估记录：Attempt Run Query Module Split

状态：verified
输入：`TRIAL_BU_CONTEXT_PACK_CN.md`
目标：评估 attempt/run 查询逻辑是否完成模块拆分，并保持 BT 查询行为兼容。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| BU1 | query module split、focused tests、本评估文件 | 保持行为不变并降低 store 文件增长风险 | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 行为兼容 | 35 |
| 文件规模减压 | 30 |
| 模块边界清晰 | 20 |
| 验证完整性 | 15 |

自动重跑阈值：

- 查询排序或过滤语义改变。
- store 不再导出 BT 的 public query 函数。
- store warning margin 未达到 20 行。
- focused tests、ruff、process hardening、registry 或 full regression 失败。

## 3. BU1 结果

- 新增 `scheduler_attempt_run_artifact_queries.py`，承载 list/latest 查询实现。
- `scheduler_attempt_run_artifact_store.py` 保留 BT public query 函数名的 import/re-export，兼容现有调用方。
- 查询过滤、排序、latest 行为保持不变。
- store 文件从 114 行降到 70 行，warning margin 从 6 行恢复到 50 行；使用 `__all__` 保留兼容 re-export。

## 4. 主进程验证

- `PYTHONPATH=src python3 -m pytest tests/test_scheduler_attempt_run_artifact_store.py -q`：通过，6 passed。
- `ruff check src/ashare_evidence/scheduler_attempt_run_artifact_store.py src/ashare_evidence/scheduler_attempt_run_artifact_queries.py tests/test_scheduler_attempt_run_artifact_store.py`：通过。
- `process-hardening-check`：第一次因评估占位符和 wrapper 方案 margin 不足失败；改为 `__all__` re-export 后通过。
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check ...`：通过，0 issues。
- `PYTHONPATH=src python3 -m pytest -q`：通过，534 passed，147 deselected。

## 5. 重跑记录

- 第一次 ruff 因直接 re-export 被视为 unused import 失败；改为 wrapper 后 focused tests 通过。
- 第一次 process hardening 因 wrapper 方案仍未满足 20 行 margin 失败；改为 `__all__` re-export 后重跑。

## 6. 自评

- BU 保持 BT 查询行为不变，并把查询实现迁移到独立模块。store 仍导出原 public query 函数名，后续查询扩展应进入 query module。
