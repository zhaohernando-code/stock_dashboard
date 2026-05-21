# Trial BO 评估记录：CLI Output Context Split

状态：verified
输入：`TRIAL_BO_CONTEXT_PACK_CN.md`
目标：评估 CLI output dispatcher 是否完成结构性减压，并用 warning margin 防止继续堆叠。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| BO1 | CLI output context helper、导入调整、本评估文件 | 拆分共享结构并保持行为不变 | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 结构减压 | 35 |
| 行为兼容 | 30 |
| margin 门禁 | 20 |
| 文件规模与验证 | 15 |

自动重跑阈值：

- 新增或改变 CLI output 行为。
- `cli_autonomous_flow_outputs.py` 未满足 warning margin。
- 修改临界 BM 测试文件。
- focused tests、ruff、process hardening、registry 或 full regression 失败。

## 3. BO1 结果

完成：

- 新增 `src/ashare_evidence/cli_autonomous_flow_output_context.py`，承接 `Phase5LocalCycleStepHandlers`、`run_tick_from_args`、`print_json`。
- `src/ashare_evidence/cli_autonomous_flow_outputs.py` 仅保留 output 分发和轻量委托；`Phase5LocalCycleStepHandlers` 仍可从该模块导入，入口兼容。
- 未新增 output，未修改 exit code 或 JSON shape，未修改 `tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py`。

文件规模：

- `cli_autonomous_flow_outputs.py`：118 行，低于 warning 160，剩余 42 行，通过 margin 15。
- `cli_autonomous_flow_output_context.py`：40 行，低于 warning 110。
- `cli_autonomous_flow.py`：105 行，低于 warning 170。
- `test_cli_autonomous_flow_attempt_route_auto_apply_output.py`：178 行，未修改。

## 4. 主进程验证

主进程复核隔离 worktree diff 后并入集成分支；BO1 本地验证与主进程 focused gates 均通过：

- Focused tests：BO1 `9 passed`；main `9 passed in 0.60s`。
- Ruff：passed。
- Process hardening：status=pass，issue_count=0；`cli_autonomous_flow_outputs.py` 118 行，warning 160，margin remaining 42。
- Registry：status=pass，issue_count=0。
- Full regression：main `522 passed, 147 deselected in 23.45s`。

主进程语义复核：

- 未新增 output，未改变 exit code 或 JSON shape。
- `Phase5LocalCycleStepHandlers` 仍可从 `cli_autonomous_flow_outputs.py` 导入，保持入口兼容。
- 未修改临界 BM 测试文件。

## 5. 重跑记录

BO1 本地验证通过；主进程复跑 focused gates：

- focused tests：passed，9 passed。
- ruff：passed。
- process hardening：passed，`status=pass`。
- contract registry：passed，`status=pass`。
- full regression：BO1 passed，522 passed，147 deselected；main `522 passed, 147 deselected in 23.45s`。

## 6. 自评

结构减压完成，dispatcher 从 150 行降到 118 行；共享 helper 保持窄职责，没有引入新抽象框架。后续 CLI output 新增应继续使用 margin gate，避免 dispatcher 再次接近 warning。
