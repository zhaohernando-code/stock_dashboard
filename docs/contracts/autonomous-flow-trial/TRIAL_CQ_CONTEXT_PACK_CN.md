# Trial CQ 上下文包：Workbench Frontend Contract

目标：把 workbench projection endpoint 固化为前端共享 typed client 和类型契约，供 PC/mobile 工作台后续共用。

## 1. 初始需求对齐

- PC web 和手机端后续不能各自拼 URL 或手写字段结构。
- 工作台 projection 是跨端一屏状态输入，类型必须和后端 manifest 字段保持一致。
- 本轮只做契约和 client，不改视觉 UI，避免在数据契约未稳定前扩大页面改造面。

## 2. 本轮范围

必须做：

- 在 operations 类型域新增 workbench projection manifest 的 TS 类型。
- 在 dashboard API client 新增 `getOperationsWorkbenchProjection`。
- 在 API barrel 中导出该 client，保证 PC/mobile 使用同一入口。
- 前端 build 必须通过。

不得做：

- 不修改 PC/mobile 页面布局。
- 不引入独立的工作台状态缓存。
- 不绕过现有 request/core 行为。

## 3. 文件规模预算

- `frontend/src/types/operations.ts`：hard 310，warning 290。
- `frontend/src/api/dashboard.ts`：hard 190，warning 175。
- `frontend/src/api/index.ts`：hard 150，warning 130。
- `docs/contracts/autonomous-flow-trial/TRIAL_CQ_EVALUATION_CN.md`：hard 140，warning 110。

## 4. 验证命令

```bash
npm --prefix frontend run build
PYTHONPATH=src python3 -m pytest tests/test_phase5_workbench_frontend_projection.py -q
PYTHONPATH=src python3 -m pytest -q
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_CQ_EVALUATION_CN.md \
  --line-budget frontend/src/types/operations.ts:310:290 \
  --line-budget frontend/src/api/dashboard.ts:190:175 \
  --line-budget frontend/src/api/index.ts:150:130 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_CQ_EVALUATION_CN.md:140:110 \
  --required-evidence frontend/src/api/dashboard.ts:getOperationsWorkbenchProjection \
  --required-evidence frontend/src/types/operations.ts:Phase5WorkbenchProjectionManifest
```
