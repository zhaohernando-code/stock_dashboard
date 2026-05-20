# Trial BB 评估记录：Split CLI Execution Output Handlers

状态：completed, main verification passed
输入：`TRIAL_BB_CONTEXT_PACK_CN.md`
目标：评估 CLI execution/full 输出拆分是否降低 dispatcher 规模风险，并保持 CLI 行为完全不变。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| BB1 | CLI execution/full output handler split、本评估文件 | 行为保持拆分 | completed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 行为兼容 | 40 |
| dispatcher 规模改善 | 25 |
| 模块边界清晰 | 20 |
| 门禁完整 | 15 |

自动重跑阈值：

- `execution` missing args 不再先于 tick 返回 exit 2。
- `execution` conflict exit code 3 或 typed JSON 变化。
- `execution` 正常路径调用 service/dry-run/diagnostic recorder。
- `full` 输出成功/异常 exit code 或 JSON 变化。
- `status` tick exit code 回归。
- 修改 parser choices/help 或新增 CLI output。
- 修改临界测试文件。
- focused tests、ruff、process hardening、registry 或 full regression 失败。

## 3. BB1 结果

BB1 已完成行为保持拆分：

- 新增 `src/ashare_evidence/cli_autonomous_flow_execution_outputs.py`，迁移 execution/full handler、execution conflict payload、missing argument helper、jsonable result helper。
- `src/ashare_evidence/cli_autonomous_flow_outputs.py` 仅保留 status/plan/dry-run/action/route/diagnostic 分发，以及 execution/full 的轻量委托。
- 未修改 parser choices/help，未新增 CLI output，未接 action-route-apply core。
- 未修改临界测试文件。

规模结果：

- `src/ashare_evidence/cli_autonomous_flow_outputs.py`：114 行，低于 warning 170。
- `src/ashare_evidence/cli_autonomous_flow_execution_outputs.py`：110 行，低于 warning 150。

## 4. 主进程验证

BB1 本地验证：

- Focused pytest：`20 passed in 0.84s`。
- Ruff：`All checks passed!`。
- Registry：pass，`issue_count: 0`。
- Process hardening：pass，`issue_count: 0`。
- Full regression：`465 passed, 147 deselected in 21.57s`。

主进程复核：

- focused pytest：20 passed。
- ruff：passed。
- process hardening：passed，`cli_autonomous_flow_outputs.py` 从 198 行降到 114 行，新 execution output 模块 110 行。
- contract registry：passed，0 issues。
- `git diff --check`：passed。
- full regression：465 passed，147 deselected。

## 5. 重跑记录

1. Process hardening 首跑失败：评估文档仍包含未完成占位标记。
2. 已更新评估文档，移除占位并补充 BB1 结果，随后重跑门禁。
3. 最终 process-hardening 与 registry 均通过。

## 6. 自评

本轮是结构性拆分，为后续 CLI route apply 接线清理空间，不扩展功能。核心行为保持点由 focused tests 覆盖：execution missing args 仍先于 tick 返回 2；conflict 仍返回 exit 3 typed JSON；execution 正常路径仍为 tick -> plan -> record；full 成功/异常 exit code 保持；status tick exit code 透传保持。
