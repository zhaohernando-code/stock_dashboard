# Trial AX 评估记录：Split CLI Action Output Handlers

状态：implemented, main verification queued
输入：`TRIAL_AX_CONTEXT_PACK_CN.md`
目标：评估 CLI action/action-route 输出拆分是否降低 dispatcher 规模风险，并保持行为完全不变。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| AX1 | CLI action output handler split、测试、本评估文件 | 拆分 action/action-route 输出逻辑 | completed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 行为兼容 | 35 |
| 模块边界清晰 | 25 |
| 文件规模改善 | 25 |
| 门禁完整 | 15 |

自动重跑阈值：

- `action` completed/blocked exit code 变化。
- `action-route` exit code 或 JSON schema 变化。
- `execution` conflict exit code 3 或 `status` tick exit code 回归。
- `cli_autonomous_flow_outputs.py` 未降到 warning 以下。
- 修改临界文件 `tests/test_cli_autonomous_flow_action_output.py`。
- focused tests、ruff、process hardening、registry 或 full regression 失败。

## 3. AX1 结果

- 新增 `src/ashare_evidence/cli_autonomous_flow_action_outputs.py`，承接 `action` / `action-route` 输出逻辑与 blocked exit code helper。
- 主进程发现 action split 后 dispatcher 仍触发 warning，继续新增 `src/ashare_evidence/cli_autonomous_flow_diagnostic_outputs.py` 拆出 diagnostic 输出逻辑。
- `src/ashare_evidence/cli_autonomous_flow_outputs.py` 仅保留轻量 dispatcher 委托调用。
- 目标行为保持不变：`action` completed 返回 0，blocked 返回 4 且打印 action result JSON；`action-route` 返回 0 且打印 route result JSON。
- 未修改 parser choices/help、action executor、router、ledger/reservation、artifact store、diagnostic/recovery/projection/closeout。
- 未修改 `tests/test_cli_autonomous_flow_action_output.py`。

## 4. 主进程验证

主进程语义审查：

- action/action-route 输出链路被移出主 dispatcher；主 dispatcher 只调用 `handle_action_output(...)` 与 `handle_action_route_output(...)`。
- 拆分模块仍通过注入的 `run_tick_from_args` 和 `print_json` 复用原有 tick 参数绑定与 JSON 输出，不引入新的 IO 或 writer。
- `action` / `action-route` 的 handler 顺序、exit code、JSON 输出语义保持不变。
- `execution` conflict exit code 3 和 `status` tick exit code 不在本轮修改范围内，并由 focused regression 覆盖。
- `cli_autonomous_flow_outputs.py` 在主进程二次拆分后降到 warning 200 以下；临界测试文件未修改。

主进程门禁：

- focused pytest：24 passed。
- ruff：passed。
- process hardening：first main run exposed dispatcher warning after action-only split; final rerun passed，0 issues。
- contract registry：passed，0 issues。
- diff check：passed。
- full regression：448 passed，147 deselected。

## 5. 重跑记录

- AX1 隔离 worktree 首次 process hardening 因评估文档占位失败；补齐文档后通过。
- 主进程首次 hardening 暴露 action-only split 后 dispatcher 仍为 213/200，已继续拆出 diagnostic handler。

## 6. 自评

本轮是结构拆分，不扩展功能。后续继续增加 CLI output 分支时，应优先新增专门 handler 模块，而不是继续膨胀 `cli_autonomous_flow_outputs.py`。
