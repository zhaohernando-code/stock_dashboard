# Trial CS 上下文包：Workbench Status UI

目标：把 workbench projection 显示到 PC/mobile 运营工作台，让用户能在复盘入口看到自动化平台运行状态。

## 1. 初始需求对齐

- 中台需要一屏看见项目/任务/自动推进状态，不能只停留在 API 和文档。
- PC web 和手机端都必须消费同一个 typed client 和 projection 数据。
- UI 必须是查看/管理导向，只展示状态、阻塞原因和刷新入口，不让用户参与底层调度。

## 2. 本轮范围

必须做：

- 新增共享 `WorkbenchProjectionPanel`。
- PC 运营复盘页展示 workbench projection 状态卡。
- 手机复盘页展示同一状态卡的移动布局。
- `App` 加载 operations 时并行加载 workbench projection，失败不阻断原复盘数据。
- 前端 build 与浏览器验证通过。

不得做：

- 不改自动推进执行逻辑。
- 不新增独立页面路由。
- 不扩大现有 operations tab 结构。

## 3. 文件规模预算

- `frontend/src/components/WorkbenchProjectionPanel.tsx`：hard 140，warning 120。
- `frontend/src/styles/workbench.css`：hard 120，warning 100。
- `frontend/src/App.tsx`：hard 3200，warning 3160。
- `frontend/src/components/mobile/MobileOperations.tsx`：hard 460，warning 430。
- `frontend/src/components/mobile/types.ts`：hard 100，warning 90。
- `frontend/src/main.tsx`：hard 220，warning 200。
- `docs/contracts/autonomous-flow-trial/TRIAL_CS_EVALUATION_CN.md`：hard 160，warning 130。

## 4. 验证命令

```bash
npm --prefix frontend run build
PYTHONPATH=src python3 -m pytest tests/test_phase5_workbench_frontend_projection.py -q
PYTHONPATH=src python3 -m pytest -q
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_CS_EVALUATION_CN.md \
  --line-budget frontend/src/components/WorkbenchProjectionPanel.tsx:140:120 \
  --line-budget frontend/src/styles/workbench.css:120:100 \
  --line-budget frontend/src/App.tsx:3200:3160 \
  --line-budget frontend/src/components/mobile/MobileOperations.tsx:460:430 \
  --line-budget frontend/src/components/mobile/types.ts:100:90 \
  --line-budget frontend/src/main.tsx:220:200 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_CS_EVALUATION_CN.md:160:130 \
  --required-evidence frontend/src/components/WorkbenchProjectionPanel.tsx:WorkbenchProjectionPanel \
  --required-evidence frontend/src/App.tsx:getOperationsWorkbenchProjection
```
