# Trial CE 评估记录：Intervention Run Readout

状态：verified
输入：`TRIAL_CE_CONTEXT_PACK_CN.md`
目标：评估 intervention run artifact 是否具备稳定查询与 readout 输出。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| CE1 | queries、readout、CLI output、tests、本评估文件 | 输出 intervention run 聚合状态 | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 查询稳定性 | 30 |
| readout 可消费性 | 30 |
| CLI 只读边界 | 20 |
| 验证完整性 | 20 |

自动重跑阈值：

- CLI readout 触发 scheduler handler 或写 artifact。
- readout 通过 reason 文本判断状态。
- focused tests、ruff、process hardening 或 full regression 失败。

## 3. CE1 结果

- 新增 `scheduler_attempt_run_intervention_artifact_queries.py`，支持按 cycle、runner、execution_status 查询 intervention run artifacts，并按 issued_at/run id 稳定倒序。
- `scheduler_attempt_run_intervention_artifact_store.py` re-export query helpers，保持 store 入口统一。
- 新增 `scheduler_attempt_run_intervention_readout.py`，输出 total/latest/status counts/run refs，供调度器和中台消费。
- 新增 CLI 输出 `attempt-run-intervention-readout`，只读 intervention run artifact，不触发 scheduler handler，不写 artifact。
- 为避免 CLI handler 文件膨胀，将 intervention 相关 CLI 输出拆到 `cli_autonomous_flow_attempt_intervention_outputs.py`。

## 4. 主进程验证

- `PYTHONPATH=src python3 -m pytest tests/test_scheduler_attempt_run_intervention_artifact_store.py tests/test_scheduler_attempt_run_intervention_readout.py tests/test_cli_autonomous_flow_attempt_intervention_readout_output.py -q` 通过，8 passed。
- `ruff check ...` 首轮发现 import 排序问题，`ruff check --fix` 后通过。
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check ...` 通过，issue_count 0。
- `PYTHONPATH=src python3 -m pytest -q` 通过，570 passed，147 deselected。

## 5. 重跑记录

- 首轮把 intervention readout/plan/apply 都留在 `cli_autonomous_flow_attempt_readout_outputs.py`，文件达到 139 行，距离 warning 140 只剩 1 行。
- 主进程判断这不符合基座可维护性要求，拆出 `cli_autonomous_flow_attempt_intervention_outputs.py` 后，readout outputs 降至 36 行，intervention outputs 为 110 行。

## 6. 自评

- 本轮没有扩大 side effect，只补齐读取层，符合“中台/调度器看 typed 状态，不扫原始 JSON”的方向。
- 后续如果继续新增 attempt-run intervention 输出，应优先扩展 intervention outputs 模块或再按职责拆分，不能回到中央 dispatcher 或 readout 文件里堆分支。
