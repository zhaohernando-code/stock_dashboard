# Trial CP 评估记录：Workbench Projection Endpoint

状态：verified
输入：`TRIAL_CP_CONTEXT_PACK_CN.md`
目标：评估 workbench projection 是否可通过现有 frontend projection 体系和 API 被 PC/mobile 工作台直接消费。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| CP1 | projection refresh、API、CLI、tests、本评估文件 | 暴露工作台 projection endpoint | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| frontend projection 体系一致性 | 30 |
| API 可消费性 | 30 |
| fallback 与缓存语义 | 20 |
| 验证完整性 | 20 |

自动重跑阈值：

- endpoint 或 frontend projection 调用 auto-progress apply。
- missing cycle 不能返回结构化 blocked projection。
- focused tests、ruff、process hardening 或 full regression 失败。

## 3. CP1 结果

- 新增 phase5 workbench frontend projection key、payload builder、refresh helper。
- `/dashboard/operations/workbench-projection` 通过独立 router 注册，支持缓存读取、只读 fallback、显式 refresh 后持久化缓存。
- `frontend-projections-refresh` CLI 支持手动物化 workbench projection，并要求显式 cycle id。
- missing cycle 仍返回结构化 blocked projection，页面可展示阻塞原因。

## 4. 主进程验证

- Focused tests：`PYTHONPATH=src python3 -m pytest tests/test_phase5_workbench_frontend_projection.py tests/test_frontend_projections.py -q`，结果 `13 passed`。
- Required evidence：`tests/test_phase5_workbench_frontend_projection.py:test_phase5_workbench_projection_materializes_ready_frontend_payload`。
- Required evidence：`tests/test_phase5_workbench_frontend_projection.py:test_phase5_workbench_projection_api_returns_fallback_and_refresh_cache`。
- Ruff：`ruff check src/ashare_evidence/frontend_projections.py src/ashare_evidence/api.py src/ashare_evidence/api_workbench_projection.py src/ashare_evidence/cli.py tests/test_phase5_workbench_frontend_projection.py`，结果 `All checks passed!`。
- Contract registry：`contract-registry-check` 覆盖 CP context/evaluation docs，结果 `status=pass`、`issue_count=0`。
- Full regression：`PYTHONPATH=src python3 -m pytest -q`，结果 `637 passed, 147 deselected`。
- 文件规模：frontend projection 421 行、API 2206 行、workbench router 39 行、CLI 1248 行、CP test 166 行，均低于本轮 warning budget。

## 5. 重跑记录

- 暂无。

## 6. 自评

- 本轮把工作台状态输入接入了实际 API/projection 通道，PC/mobile 页面无需理解 CLI 输出或 artifact 目录。
- API endpoint 已抽到独立 router，避免后续工作台端点继续扩大主 API 文件。
- refresh 使用显式 cycle id，避免 `all` projection 在没有运行上下文时误写无意义缓存。
- API fallback 保持只读，适合新环境、缓存过期和恢复态页面。
