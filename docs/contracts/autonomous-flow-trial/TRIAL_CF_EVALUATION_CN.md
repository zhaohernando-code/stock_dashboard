# Trial CF 评估记录：Intervention Follow-up Policy

状态：verified
输入：`TRIAL_CF_CONTEXT_PACK_CN.md`
目标：评估 intervention run readout 是否能转换为下一步 typed follow-up decision。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| CF1 | policy、CLI output、tests、本评估文件 | 输出 intervention 后续决策 | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 下一步决策清晰 | 35 |
| 纯策略边界 | 25 |
| CLI 只读边界 | 20 |
| 验证完整性 | 20 |

自动重跑阈值：

- policy 解析 reason 文本。
- CLI follow-up decision 写 artifact 或调用 scheduler handler。
- focused tests、ruff、process hardening 或 full regression 失败。

## 3. CF1 结果

- 新增 `scheduler_attempt_run_intervention_followup_policy.py`，基于 intervention run readout 输出 typed follow-up decision。
- 新增 CLI 输出 `attempt-run-intervention-followup-decision`，只读 intervention run artifacts，不调用 scheduler handler、不写 artifact。
- latest applied diagnostic 映射为 `open_recovery_ticket`，latest blocked 映射为 `retry_failed_step`，empty/skipped 映射为 `continue_tracking`。
- 策略只使用 typed readout 字段，不解析 reason 文本。

## 4. 主进程验证

- `PYTHONPATH=src python3 -m pytest tests/test_scheduler_attempt_run_intervention_followup_policy.py tests/test_cli_autonomous_flow_attempt_intervention_followup_decision_output.py -q` 通过，6 passed。
- `ruff check ...` 首轮发现 import 排序问题，`ruff check --fix` 后通过。
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check ...` 通过，issue_count 0。
- `PYTHONPATH=src python3 -m pytest -q` 通过，576 passed，147 deselected。

## 5. 重跑记录

- 无逻辑重跑；仅修复 ruff import 排序。

## 6. 自评

- 本轮把 intervention 结果推进为下一步调度决策，但仍不执行恢复票创建，保持“策略层”和“副作用层”分离。
- 下一轮若继续推进，应新增 recovery-ticket intent/apply 层，不能直接在 policy 或 CLI readout 中写恢复票。
