# Trial CQ 评估记录：Workbench Frontend Contract

状态：verified
输入：`TRIAL_CQ_CONTEXT_PACK_CN.md`
目标：评估 workbench projection 是否已作为前端共享 typed client 和类型契约固化。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| CQ1 | frontend types、dashboard API client、barrel、tests、本评估文件 | 固化跨端 workbench projection 契约 | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 后端 manifest 字段一致性 | 35 |
| PC/mobile 共享入口 | 25 |
| request/core 体系一致性 | 20 |
| 验证完整性 | 20 |

自动重跑阈值：

- 前端 build 失败。
- PC/mobile 需要各自拼 endpoint。
- focused backend endpoint tests 或 full regression 失败。

## 3. CQ1 结果

- 新增 `Phase5WorkbenchProjectionManifest` 及 cycle、recovery、auto-progress 子结构类型。
- 新增 `getOperationsWorkbenchProjection`，通过现有 request/core 访问 workbench projection endpoint。
- API barrel 导出统一 client，PC/mobile 后续可共享同一入口。

## 4. 主进程验证

- Frontend build：`npm --prefix frontend run build`，结果通过；保留既有 Vite large chunk warning。
- Focused backend test：`PYTHONPATH=src python3 -m pytest tests/test_phase5_workbench_frontend_projection.py -q`，结果 `5 passed`。
- Required evidence：`frontend/src/api/dashboard.ts:getOperationsWorkbenchProjection`。
- Required evidence：`frontend/src/types/operations.ts:Phase5WorkbenchProjectionManifest`。
- Contract registry：`contract-registry-check` 覆盖 CQ context/evaluation docs，结果 `status=pass`、`issue_count=0`。
- Full regression：`PYTHONPATH=src python3 -m pytest -q`，结果 `637 passed, 147 deselected`。
- 文件规模：operations types 279 行、dashboard API 168 行、API barrel 122 行，均低于本轮 warning budget。

## 5. 重跑记录

- 暂无。

## 6. 自评

- 本轮没有提前改页面，先把跨端契约固定，符合后续 PC/mobile 双端开发的流程要求。
- typed client 保持在现有 dashboard API 层，避免页面组件直接绑定 endpoint URL。
