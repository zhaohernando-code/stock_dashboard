# Trial BW 评估记录：CLI Attempt Run Readout Output

状态：verified
输入：`TRIAL_BW_CONTEXT_PACK_CN.md`
目标：评估 CLI 是否以无副作用方式暴露 attempt/run readout。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| BW1 | CLI readout output、focused tests、本评估文件 | 暴露无副作用的 attempt/run readout CLI | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 输出语义正确性 | 35 |
| 无副作用边界 | 30 |
| 默认行为兼容 | 20 |
| 验证完整性 | 15 |

自动重跑阈值：

- readout 输出调用 tick/plan/action/apply。
- readout 输出写 artifact。
- 改变 `attempt-route-auto-apply` 行为。
- focused tests、ruff、process hardening、registry 或 full regression 失败。

## 3. BW1 结果

- `phase5-local-cycle-step --output` 新增 `attempt-run-readout`。
- 新增 `handle_attempt_run_readout_output`，只调用 BV readout query convenience，输出 readout JSON，exit code 为 0。
- 新增独立 CLI focused tests，覆盖有记录和空 store；测试明确断言不运行 tick/plan/action/route/apply handlers。
- 未改变 `attempt-route-auto-apply` 默认输出或 opt-in recording。

## 4. 主进程验证

- `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_attempt_run_readout_output.py tests/test_scheduler_attempt_run_readout.py -q`：通过，5 passed。
- `ruff check ...`：首次发现 import 排序问题；`ruff --fix` 后通过。
- `PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check ...`：通过，0 issues。
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check ...`：通过，0 issues。
- `PYTHONPATH=src python3 -m pytest -q`：通过，539 passed，147 deselected。
- 主进程语义复核：readout 输出不调用 tick、plan、action、route、apply handlers；只读 artifact store 并输出 BV readout JSON。

## 5. 重跑记录

- ruff import 排序自动修复一次；无功能重跑。

## 6. 自评

- readout CLI 是只读路径，不写 artifact，不触发 scheduler handlers；输出用于人工、调度器和后续中台读取 attempt/run 状态。`cli_autonomous_flow_attempt_outputs.py` 已到 114 行，后续 attempt 输出扩展应拆新模块。
