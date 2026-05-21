# Trial CO 评估记录：Workbench Projection Manifest

状态：verified
输入：`TRIAL_CO_CONTEXT_PACK_CN.md`
目标：评估工作台一屏 projection manifest 是否能只读组合 cycle/recovery/auto-progress 状态。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| CO1 | projection、CLI、tests、本评估文件 | 输出工作台 projection manifest | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| projection 字段完整性 | 35 |
| 状态降级语义 | 25 |
| 只读边界 | 20 |
| 验证完整性 | 20 |

自动重跑阈值：

- projection 模块调用 apply 或写 artifact。
- cycle 缺失时抛未结构化异常。
- focused tests、ruff、process hardening 或 full regression 失败。

## 3. CO1 结果

- 新增 `Phase5WorkbenchProjectionManifest`，组合 cycle summary、recovery summary、auto-progress summary。
- CLI 新增 `attempt-run-workbench-projection`，输出 PC/mobile 工作台一屏状态输入。
- projection 覆盖 source refs、missing refs、blocking reasons、recommended next action。
- cycle 缺失返回 blocked projection 与 exit code 4，不抛未结构化异常。
- 空 auto-progress history 返回 degraded projection，推荐 `run_auto_progress_plan`。
- 本轮只读，不写 artifact，不调用 auto-progress apply。

## 4. 主进程验证

- Focused tests 初次失败：测试期望 recovery ticket 后 projection 为 current；实际 cycle status 已因 recovery ticket final_status=degraded 降级。修正测试为 degraded，保留降级语义。
- Focused tests：`PYTHONPATH=src python3 -m pytest tests/test_scheduler_workbench_projection.py tests/test_cli_autonomous_flow_workbench_projection_output.py -q`，结果 `6 passed`。
- Required evidence：`tests/test_scheduler_workbench_projection.py:test_workbench_projection_combines_cycle_recovery_and_auto_progress`。
- Required evidence：`tests/test_cli_autonomous_flow_workbench_projection_output.py:test_workbench_projection_output_reads_projection_manifest`。
- Ruff：`ruff check src/ashare_evidence/scheduler_workbench_projection.py src/ashare_evidence/cli_autonomous_flow_workbench_outputs.py src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_output_dispatch.py tests/test_scheduler_workbench_projection.py tests/test_cli_autonomous_flow_workbench_projection_output.py`，结果 `All checks passed!`。
- Contract registry：`contract-registry-check` 覆盖 CO context/evaluation docs，结果 `status=pass`、`issue_count=0`。
- Full regression：`PYTHONPATH=src python3 -m pytest -q`，结果 `632 passed, 147 deselected`。
- 文件规模：projection 226 行、CLI workbench outputs 20 行、dispatcher 150 行、主 CLI 138 行，均低于本轮 warning budget。

## 5. 重跑记录

- 1 次测试预期修正：recovery ticket 后 cycle/projection 应为 degraded。

## 6. 自评

- 本轮把后端自动推进状态收束为工作台可消费的一屏 projection，开始回到初始“现代中台”目标。
- projection 仍是只读输出，前端可先消费 CLI/API JSON；后续可再做持久化或 API endpoint。
- 下一步建议进入 Trial CP：为 workbench projection 增加可选 persisted artifact 或 API projection endpoint，服务 PC/mobile 页面。
