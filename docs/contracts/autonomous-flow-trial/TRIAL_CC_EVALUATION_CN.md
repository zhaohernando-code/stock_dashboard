# Trial CC 评估记录：Attempt Run Intervention Apply

状态：verified
输入：`TRIAL_CC_CONTEXT_PACK_CN.md`
目标：评估 attempt-run intervention plan 是否能安全执行最小 diagnostic 写入，并保持无人值守边界。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| CC1 | intervention executor、CLI apply output、tests、本评估文件 | 让 intervention plan 能安全记录 diagnostic | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 写入边界清晰 | 35 |
| 幂等与稳定 ID | 25 |
| CLI 无人值守能力 | 20 |
| 验证完整性 | 20 |

自动重跑阈值：

- apply executor 调用 tick、scheduler action executor 或 route apply executor。
- `observe_only` 写入 artifact。
- blocked latest 无法在不提供 diagnostic id 的情况下记录 diagnostic。
- focused tests、ruff、process hardening、registry 或 full regression 失败。

## 3. CC1 结果

- 新增 `scheduler_attempt_run_intervention_executor.py`，只支持 `scheduler_diagnostic` 最小写入。
- 新增 `scheduler_attempt_run_intervention_diagnostics.py`，集中稳定 diagnostic id、severity、failure_class 和 recovery_action 映射，避免 executor 文件继续膨胀。
- `attempt-run-intervention-apply` CLI 输出会读取 attempt/run artifacts，构造 intervention plan，并在 blocked latest 场景自动记录 scheduler diagnostic。
- apply executor 不调用 tick、scheduler action executor 或 route apply executor，也不创建 recovery ticket、不写 execution ledger。
- `observe_only` 返回 skipped 且不写 artifact；缺少 cycle_id/observed_at 等执行参数时返回 typed blocked。

## 4. 主进程验证

- `PYTHONPATH=src python3 -m pytest tests/test_scheduler_attempt_run_intervention_executor.py tests/test_cli_autonomous_flow_attempt_intervention_apply_output.py tests/test_scheduler_attempt_run_intervention_plan.py tests/test_cli_autonomous_flow_attempt_intervention_plan_output.py -q` 通过，13 passed。
- `ruff check src/ashare_evidence/scheduler_attempt_run_intervention_executor.py src/ashare_evidence/scheduler_attempt_run_intervention_diagnostics.py src/ashare_evidence/scheduler_attempt_run_intervention_plan.py src/ashare_evidence/cli_autonomous_flow_attempt_readout_outputs.py src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_output_dispatch.py tests/test_scheduler_attempt_run_intervention_executor.py tests/test_cli_autonomous_flow_attempt_intervention_apply_output.py` 通过。
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check ...` 通过，issue_count 0。
- `PYTHONPATH=src python3 -m pytest -q` 通过，558 passed，147 deselected。

## 5. 重跑记录

- 首轮实现后 executor 为 174 行，距离 warning 180 仅剩 6 行，不适合作为基座模块进入主线。
- 将 diagnostic id 和诊断分类规则拆出后，executor 降至 140 行，诊断规则模块为 47 行；聚焦测试重新通过。

## 6. 自评

- 本轮把“自运行介入”从只读计划推进到最小安全写入，但只开放 diagnostic 写入，避免提前扩大副作用。
- 下一轮应补 attempt-run intervention apply 的运行记录 artifact，形成“读取 -> 计划 -> 执行 -> 结果硬存储”的完整闭环。
