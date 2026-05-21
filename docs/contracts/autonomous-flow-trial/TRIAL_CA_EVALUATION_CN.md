# Trial CA 评估记录：CLI Output Dispatcher Split

状态：verified
输入：`TRIAL_CA_CONTEXT_PACK_CN.md`
目标：评估 CLI output dispatcher 拆分是否保持行为兼容并降低中央 dispatcher 增长风险。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| CA1 | dispatcher split、focused tests、本评估文件 | 保持行为不变并降低 dispatcher 文件增长风险 | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 行为兼容 | 35 |
| 文件规模减压 | 35 |
| 模块边界清晰 | 15 |
| 验证完整性 | 15 |

自动重跑阈值：

- 任一已有 output shape 改变。
- dispatcher warning margin 未达到 25。
- focused tests、ruff、process hardening、registry 或 full regression 失败。

## 3. CA1 结果

- 新增 `cli_autonomous_flow_output_dispatch.py`，承载 action、attempt、diagnostic、execution 和 full fallback 分支。
- `cli_autonomous_flow_outputs.py` 保留 status、plan、dry-run 基础路径，其余 output 交给 secondary dispatcher。
- 未新增 output，未改变 output shape。
- `cli_autonomous_flow_outputs.py` 从 128 行降至 36 行，恢复中央入口的维护余量。
- 新 dispatcher 为 96 行，低于 warning 线 140，后续仍有结构余量。

## 4. 主进程验证

- `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_attempt_followup_decision_output.py tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py tests/test_cli_autonomous_flow_action_route_apply_output.py -q` 通过，12 passed。
- `ruff check src/ashare_evidence/cli_autonomous_flow_outputs.py src/ashare_evidence/cli_autonomous_flow_output_dispatch.py` 通过。
- `PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check ...` 通过，确认评估文档、行数预算、warning margin 和 required evidence 均满足。
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check ...` 通过，确认本轮上下文包和评估文档已注册且未废弃。
- `PYTHONPATH=src python3 -m pytest -q` 通过，545 passed，147 deselected。

## 5. 重跑记录

- 首轮 ruff 发现 `cli_autonomous_flow_outputs.py` import 排序问题，执行 `ruff check --fix` 后通过。

## 6. 自评

- 本轮拆分符合“基座代码不继续补丁化”的约束：入口文件回到稳定薄层，细分输出族路由集中到独立 dispatcher。
- 剩余风险是 dispatcher 后续可能继续膨胀；下一轮若新增 output family，应优先拆 family registry 或 handler map，而不是继续堆 `if`。
