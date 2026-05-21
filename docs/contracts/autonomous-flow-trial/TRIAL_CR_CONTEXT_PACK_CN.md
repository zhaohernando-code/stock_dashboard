# Trial CR 上下文包：Workbench Latest Cycle Resolution

目标：让 workbench projection endpoint 在未传 `cycle_id` 时自动解析最新 cycle，避免 PC/mobile 工作台要求用户手工输入运行编号。

## 1. 初始需求对齐

- 单页中台应默认展示当前运行态，人工只查看和管理，不应先知道 cycle id。
- latest 解析必须来自硬存储 cycle ledger，不从页面状态或临时内存推断。
- 没有 cycle ledger 时仍返回结构化 blocked projection，不能让前端进入未处理错误态。

## 2. 本轮范围

必须做：

- workbench projection 支持 `cycle_id=None` 并解析最新 cycle ledger。
- API endpoint 支持不传 `cycle_id` 的默认工作台状态读取。
- 前端 typed client 的 `cycleId` 改为可选。
- 覆盖 latest cycle、empty ledger blocked、API default latest。

不得做：

- 不引入 UI 改造。
- 不调用 auto-progress apply。
- 不写业务 artifact。

## 3. 文件规模预算

- `src/ashare_evidence/scheduler_workbench_projection.py`：hard 310，warning 290。
- `src/ashare_evidence/api_workbench_projection.py`：hard 100，warning 80。
- `src/ashare_evidence/frontend_projections.py`：hard 460，warning 430。
- `frontend/src/api/dashboard.ts`：hard 190，warning 175。
- `tests/test_scheduler_workbench_projection.py`：hard 240，warning 210。
- `tests/test_phase5_workbench_frontend_projection.py`：hard 220，warning 190。
- `docs/contracts/autonomous-flow-trial/TRIAL_CR_EVALUATION_CN.md`：hard 150，warning 120。

## 4. 验证命令

```bash
PYTHONPATH=src python3 -m pytest tests/test_scheduler_workbench_projection.py tests/test_phase5_workbench_frontend_projection.py -q
npm --prefix frontend run build
ruff check src/ashare_evidence/scheduler_workbench_projection.py src/ashare_evidence/api_workbench_projection.py src/ashare_evidence/frontend_projections.py tests/test_scheduler_workbench_projection.py tests/test_phase5_workbench_frontend_projection.py
PYTHONPATH=src python3 -m pytest -q
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_CR_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/scheduler_workbench_projection.py:310:290 \
  --line-budget src/ashare_evidence/api_workbench_projection.py:100:80 \
  --line-budget src/ashare_evidence/frontend_projections.py:460:430 \
  --line-budget frontend/src/api/dashboard.ts:190:175 \
  --line-budget tests/test_scheduler_workbench_projection.py:240:210 \
  --line-budget tests/test_phase5_workbench_frontend_projection.py:220:190 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_CR_EVALUATION_CN.md:150:120 \
  --required-evidence tests/test_scheduler_workbench_projection.py:test_workbench_projection_defaults_to_latest_cycle \
  --required-evidence tests/test_phase5_workbench_frontend_projection.py:test_phase5_workbench_projection_api_defaults_to_latest_cycle \
  --forbidden-source-token src/ashare_evidence/api_workbench_projection.py:apply_phase5 \
  --forbidden-source-token src/ashare_evidence/scheduler_workbench_projection.py:write_
```
