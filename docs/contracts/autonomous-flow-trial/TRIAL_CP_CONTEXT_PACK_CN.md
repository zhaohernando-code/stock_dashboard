# Trial CP 上下文包：Workbench Projection Endpoint

目标：把 Trial CO 的 workbench projection manifest 接入现有 frontend projection 体系，并提供 PC/mobile 工作台可直接消费的 API endpoint。

## 1. 初始需求对齐

- 中台需要单页工作台直接读取一屏状态输入，不能依赖人工从 CLI 拼装结果。
- Projection 必须复用已有 frontend projection 缓存边界，避免为工作台额外发明一套状态通道。
- API 缺少缓存时必须能只读 fallback，保证新环境或缓存失效时页面仍能展示 blocked/degraded 状态。

## 2. 本轮范围

必须做：

- 增加 phase5 workbench frontend projection key、payload builder、refresh helper。
- 增加 `/dashboard/operations/workbench-projection` endpoint。
- endpoint 支持缓存读取、只读 fallback、显式 refresh 后持久化缓存。
- refresh CLI 支持手动物化 workbench projection。
- 覆盖函数级持久化、API fallback、API refresh cache、missing cycle blocked 输出。

不得做：

- 不修改 workbench manifest 的核心状态语义。
- 不让 endpoint 执行 auto-progress apply 或写业务 artifact。
- 不修改 `process_hardening.py`。

## 3. 文件规模预算

- `src/ashare_evidence/frontend_projections.py`：hard 460，warning 430。
- `src/ashare_evidence/api.py`：hard 2220，warning 2210。
- `src/ashare_evidence/api_workbench_projection.py`：hard 120，warning 90。
- `src/ashare_evidence/cli.py`：hard 1300，warning 1270。
- `tests/test_phase5_workbench_frontend_projection.py`：hard 220，warning 190。
- `docs/contracts/autonomous-flow-trial/TRIAL_CP_EVALUATION_CN.md`：hard 150，warning 120。

## 4. 验证命令

```bash
PYTHONPATH=src python3 -m pytest tests/test_phase5_workbench_frontend_projection.py tests/test_frontend_projections.py -q
ruff check src/ashare_evidence/frontend_projections.py src/ashare_evidence/api.py src/ashare_evidence/api_workbench_projection.py src/ashare_evidence/cli.py tests/test_phase5_workbench_frontend_projection.py
PYTHONPATH=src python3 -m pytest -q
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_CP_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/frontend_projections.py:460:430 \
  --line-budget src/ashare_evidence/api.py:2220:2210 \
  --line-budget src/ashare_evidence/api_workbench_projection.py:120:90 \
  --line-budget src/ashare_evidence/cli.py:1300:1270 \
  --line-budget tests/test_phase5_workbench_frontend_projection.py:220:190 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_CP_EVALUATION_CN.md:150:120 \
  --required-evidence tests/test_phase5_workbench_frontend_projection.py:test_phase5_workbench_projection_materializes_ready_frontend_payload \
  --required-evidence tests/test_phase5_workbench_frontend_projection.py:test_phase5_workbench_projection_api_returns_fallback_and_refresh_cache \
  --forbidden-source-token src/ashare_evidence/api_workbench_projection.py:apply_phase5 \
  --forbidden-source-token src/ashare_evidence/frontend_projections.py:write_
```
