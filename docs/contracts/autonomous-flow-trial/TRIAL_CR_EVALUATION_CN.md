# Trial CR 评估记录：Workbench Latest Cycle Resolution

状态：verified
输入：`TRIAL_CR_CONTEXT_PACK_CN.md`
目标：评估 workbench projection 是否能在未传 cycle id 时自动解析最新 cycle。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| CR1 | projection、API、frontend client、tests、本评估文件 | 默认解析最新 cycle | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| latest 解析正确性 | 35 |
| blocked fallback 结构化 | 25 |
| API/frontend 契约一致性 | 20 |
| 验证完整性 | 20 |

自动重跑阈值：

- 没有 cycle ledger 时抛未结构化异常。
- endpoint 仍要求前端必传 cycle id。
- focused tests、frontend build、ruff、process hardening 或 full regression 失败。

## 3. CR1 结果

- workbench projection 支持 `cycle_id=None`，从 cycle ledger artifact 目录按 `started_at/cycle_id` 解析最新 cycle。
- 没有 cycle ledger 时返回结构化 blocked projection，包含 `phase5_cycle_ledger:<latest>` missing ref。
- API endpoint 支持不传 `cycle_id`，默认读取最新 cycle projection。
- 前端 typed client 的 `cycleId` 改为可选，PC/mobile 可直接调用默认工作台状态。

## 4. 主进程验证

- Focused tests：`PYTHONPATH=src python3 -m pytest tests/test_scheduler_workbench_projection.py tests/test_phase5_workbench_frontend_projection.py -q`，结果 `12 passed`。
- Frontend build：`npm --prefix frontend run build`，结果通过；保留既有 Vite large chunk warning。
- Ruff：`ruff check src/ashare_evidence/scheduler_workbench_projection.py src/ashare_evidence/api_workbench_projection.py src/ashare_evidence/frontend_projections.py tests/test_scheduler_workbench_projection.py tests/test_phase5_workbench_frontend_projection.py`，结果 `All checks passed!`。
- Required evidence：`tests/test_scheduler_workbench_projection.py:test_workbench_projection_defaults_to_latest_cycle`。
- Required evidence：`tests/test_phase5_workbench_frontend_projection.py:test_phase5_workbench_projection_api_defaults_to_latest_cycle`。
- Contract registry：`contract-registry-check` 覆盖 CR context/evaluation docs，结果 `status=pass`、`issue_count=0`。
- Full regression：`PYTHONPATH=src python3 -m pytest -q`，结果 `640 passed, 147 deselected`。
- 文件规模：projection 279 行、API router 44 行、frontend projection 421 行、dashboard client 170 行，均低于本轮 warning budget。

## 5. 重跑记录

- 暂无。

## 6. 自评

- 本轮移除了前端展示工作台状态前必须知道 cycle id 的人工前置条件。
- latest 解析仍是只读硬存储读取，符合“状态不跑偏”和“无需人工介入”的流程目标。
