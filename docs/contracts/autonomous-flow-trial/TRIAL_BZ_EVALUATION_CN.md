# Trial BZ 评估记录：CLI Attempt Follow-up Decision Output

状态：verified
输入：`TRIAL_BZ_CONTEXT_PACK_CN.md`
目标：评估 CLI 是否能无副作用输出 attempt/run follow-up decision。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| BZ1 | CLI decision output、focused tests、本评估文件 | 暴露无副作用的 attempt follow-up decision CLI | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 输出语义正确性 | 35 |
| 无副作用边界 | 30 |
| policy 语义保持 | 20 |
| 验证完整性 | 15 |

自动重跑阈值：

- 输出触发 scheduler handlers 或写 artifact。
- 改变 policy 语义。
- 接入实际调度执行。
- focused tests、ruff、process hardening、registry 或 full regression 失败。

## 3. BZ1 结果

- `phase5-local-cycle-step --output` 新增 `attempt-run-followup-decision`。
- handler 读取 attempt/run readout 后调用 BY policy，输出 typed decision JSON，exit code 为 0。
- 新增 focused CLI tests 覆盖 latest blocked 与 empty store，且断言不运行 scheduler handlers。

## 4. 主进程验证

- `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_attempt_followup_decision_output.py tests/test_scheduler_attempt_run_followup_policy.py -q`：通过，6 passed。
- `ruff check src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_outputs.py src/ashare_evidence/cli_autonomous_flow_attempt_readout_outputs.py tests/test_cli_autonomous_flow_attempt_followup_decision_output.py`：通过。
- 行数结果：CLI parser 110 行，dispatcher 128 行，attempt readout outputs 36 行，focused test 114 行。
- `PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check ...`：通过，0 issues。
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check ...`：通过，0 issues。
- `PYTHONPATH=src python3 -m pytest -q`：通过，545 passed，147 deselected。
- 主进程语义复核：该输出只展示 decision，不执行 retry、recovery 或调度。

## 5. 重跑记录

- 无功能重跑。

## 6. 自评

- CLI decision 输出是只读路径，不写 artifact，不触发 scheduler handlers；当前只是展示 policy decision，尚未接实际调度执行。dispatcher 128 行，后续新增 output 前应考虑分组或表驱动路由。
