# Trial CJ 评估记录：Recovery Follow-up Apply

状态：verified
输入：`TRIAL_CJ_CONTEXT_PACK_CN.md`
目标：评估 ready recovery follow-up intent 是否能幂等创建新的 follow-up cycle。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| CJ1 | executor、CLI output、tests、本评估文件 | 幂等创建 follow-up cycle | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| cycle 创建正确性 | 35 |
| 幂等性 | 25 |
| blocked 结构化 | 20 |
| 验证完整性 | 20 |

自动重跑阈值：

- intent 模块新增写入副作用。
- 重复 apply 覆盖或重复创建 follow-up cycle。
- focused tests、ruff、process hardening 或 full regression 失败。

## 3. CJ1 结果

- 新增 `apply_phase5_scheduler_recovery_followup_intent` executor，输入 ready follow-up intent 后创建新的 `phase5_cycle_ledger`。
- follow-up cycle 使用 `trigger=recovery_followup`，`started_at` 来自显式 `created_at` 输入，scope 记录 source cycle、source ticket、source ticket ref 与 source evidence refs。
- 重复 apply 同一 intent 返回 `already_started`；existing cycle scope 不一致时返回 blocked，避免覆盖冲突。
- intent skipped/blocked、ready 字段缺失、`created_at` 缺失均返回结构化结果。
- CLI 新增 `attempt-run-recovery-followup-apply`，从硬存储读取 intent 后执行 apply；blocked 返回 exit code 4。

## 4. 主进程验证

- Focused tests：`PYTHONPATH=src python3 -m pytest tests/test_scheduler_recovery_followup_executor.py tests/test_cli_autonomous_flow_attempt_recovery_followup_apply_output.py -q`，结果 `7 passed`。
- Required evidence：`tests/test_scheduler_recovery_followup_executor.py:test_recovery_followup_apply_starts_ready_followup_cycle`。
- Required evidence：`tests/test_cli_autonomous_flow_attempt_recovery_followup_apply_output.py:test_attempt_recovery_followup_apply_output_starts_cycle`。
- Ruff：`ruff check src/ashare_evidence/scheduler_recovery_followup_executor.py src/ashare_evidence/cli_autonomous_flow_recovery_outputs.py src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_output_dispatch.py tests/test_scheduler_recovery_followup_executor.py tests/test_cli_autonomous_flow_attempt_recovery_followup_apply_output.py`，结果 `All checks passed!`。
- Contract registry：`contract-registry-check` 覆盖 CJ context/evaluation docs，结果 `status=pass`、`issue_count=0`。
- Full regression：`PYTHONPATH=src python3 -m pytest -q`，结果 `606 passed, 147 deselected`。
- 文件规模：executor 127 行、CLI recovery outputs 42 行、dispatcher 132 行、主 CLI 128 行，均低于本轮 warning budget。

## 5. 重跑记录

- 无需重跑。focused tests、ruff、registry check 与 full regression 均一次通过。

## 6. 自评

- 本轮完成了当前 intervention/recovery 纵向闭环：attempt run 阻塞后可记录 intervention diagnostic、生成 recovery ticket、写入 ticket、推导 follow-up intent、创建 follow-up cycle。
- 边界仍然清晰：follow-up intent 只读，follow-up executor 负责唯一写入。
- 下一步建议回到更高层编排：把这些独立 CLI 串成一个可观测的 auto-progress command，并引入冲突检测与任务队列状态。
