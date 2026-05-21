# Trial BX 评估记录：CLI Attempt Output Split

状态：verified
输入：`TRIAL_BX_CONTEXT_PACK_CN.md`
目标：评估 attempt readout handler 拆分是否保持行为兼容并降低文件增长风险。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| BX1 | CLI attempt readout split、focused tests、本评估文件 | 保持行为不变并降低 attempt output 文件增长风险 | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 行为兼容 | 35 |
| 文件规模减压 | 35 |
| 模块边界清晰 | 15 |
| 验证完整性 | 15 |

自动重跑阈值：

- `attempt-run-readout` 行为或输出 shape 改变。
- `attempt-route-auto-apply` 行为改变。
- attempt outputs warning margin 未达到 20。
- focused tests、ruff、process hardening、registry 或 full regression 失败。

## 3. BX1 结果

- 新增 `cli_autonomous_flow_attempt_readout_outputs.py` 承载 `handle_attempt_run_readout_output`。
- `cli_autonomous_flow_attempt_outputs.py` 移除 readout handler，仅保留 attempt context、attempt route apply、recording envelope。
- `cli_autonomous_flow_outputs.py` 从新模块导入 readout handler。

## 4. 主进程验证

- `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_attempt_run_readout_output.py tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py -q`：通过，8 passed。
- `ruff check src/ashare_evidence/cli_autonomous_flow_attempt_outputs.py src/ashare_evidence/cli_autonomous_flow_attempt_readout_outputs.py src/ashare_evidence/cli_autonomous_flow_outputs.py tests/test_cli_autonomous_flow_attempt_run_readout_output.py`：通过。
- 行数结果：attempt outputs 99 行，readout outputs 20 行，dispatcher 122 行；attempt outputs warning margin 21 行，达到本轮 minimum 20。
- `PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check ...`：通过，0 issues。
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check ...`：通过，0 issues。
- `PYTHONPATH=src python3 -m pytest -q`：通过，539 passed，147 deselected。

## 5. 重跑记录

- 无功能重跑。

## 6. 自评

- 行为兼容，readout handler 独立后 attempt outputs 恢复结构余量；后续新增 attempt 子输出应优先建独立模块。
