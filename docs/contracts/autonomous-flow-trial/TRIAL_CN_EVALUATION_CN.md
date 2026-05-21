# Trial CN 评估记录：Auto Progress Run Readout

状态：verified
输入：`TRIAL_CN_CONTEXT_PACK_CN.md`
目标：评估 auto-progress run 历史是否能被只读聚合为工作台 readout。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| CN1 | query、readout、CLI、tests、本评估文件 | 汇总 auto-progress run 历史 | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 聚合字段完整性 | 35 |
| 过滤与排序正确性 | 25 |
| 只读边界 | 20 |
| 验证完整性 | 20 |

自动重跑阈值：

- readout 模块调用 apply 或写 artifact。
- 空 store 创建目录或抛异常。
- focused tests、ruff、process hardening 或 full regression 失败。

## 3. CN1 结果

- 新增 `list_phase5_scheduler_auto_progress_run_artifacts` 与 latest query，支持 cycle、runner、phase、apply_status 过滤。
- 新增 `Phase5SchedulerAutoProgressRunReadout`，汇总 total/latest、phase、plan/apply/applied output、applied/blocked/idle counts、latest refs、evidence refs 与 result refs。
- CLI 新增 `attempt-run-auto-progress-readout`，只读输出 auto-progress run 历史。
- 空 store 返回 degraded readout，不创建 artifact 目录。
- Store `__all__` 导出 query/list，供后续 projection builder 复用。

## 4. 主进程验证

- Focused tests 初次失败：测试只期待 latest result ref，但 readout 设计为汇总所有历史 result refs；修正测试以匹配工作台历史汇总语义。
- Focused tests：`PYTHONPATH=src python3 -m pytest tests/test_scheduler_auto_progress_readout.py tests/test_cli_autonomous_flow_auto_progress_readout_output.py -q`，结果 `5 passed`。
- Required evidence：`tests/test_scheduler_auto_progress_readout.py:test_auto_progress_readout_summarizes_latest_run`。
- Required evidence：`tests/test_cli_autonomous_flow_auto_progress_readout_output.py:test_auto_progress_readout_output_reads_recorded_runs`。
- Ruff：`ruff check src/ashare_evidence/scheduler_auto_progress_artifact_queries.py src/ashare_evidence/scheduler_auto_progress_readout.py src/ashare_evidence/scheduler_auto_progress_artifact_store.py src/ashare_evidence/cli_autonomous_flow_auto_progress_outputs.py src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_output_dispatch.py tests/test_scheduler_auto_progress_readout.py tests/test_cli_autonomous_flow_auto_progress_readout_output.py`，结果 `All checks passed!`。
- Contract registry：`contract-registry-check` 覆盖 CN context/evaluation docs，结果 `status=pass`、`issue_count=0`。
- Full regression：`PYTHONPATH=src python3 -m pytest -q`，结果 `626 passed, 147 deselected`。
- 文件规模：query 60 行、readout 116 行、store 49 行、CLI auto-progress outputs 101 行、dispatcher 146 行，均低于本轮 warning budget。

## 5. 重跑记录

- 1 次测试语义修正：result refs 为历史汇总而非 latest-only。

## 6. 自评

- 本轮完成了 auto-progress 历史的只读 readout，可以作为平台侧工作台“状态一览”的输入候选。
- 读取链路没有执行 apply 或写 artifact，适合作为后续平台系统读取的只读证据源。
- 后续不得在 `stock_dashboard` 内继续推进 workbench projection manifest、工作台 API 或前端平台总览；这些属于独立自动化平台本体。若要继续 Trial CO，必须先切换到平台宿主，并只把本项目作为被纳管样本或 fixture。
