# Trial BA 评估记录：Scheduler Action Route Apply Core

状态：completed, main verification passed
输入：`TRIAL_BA_CONTEXT_PACK_CN.md`
目标：评估核心 route apply 层是否能先 preflight、再安全调用现有 diagnostic / execution writer，并把 blocked/conflict/no-op 都转成 typed result。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| BA1 | route apply core、测试、本评估文件 | 实现核心 route apply 函数与门禁 | rejected |
| BA2 | route apply core、测试、本评估文件 | 压缩到 warning 线内并重跑核心门禁 | completed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| preflight 强制与 fail-closed | 30 |
| writer 复用与副作用边界 | 30 |
| typed blocked/conflict/no-op 结果 | 25 |
| 文件规模与门禁 | 15 |

自动重跑阈值：

- route apply 不调用 preflight，或 preflight blocked 后仍调用 writer。
- diagnostic/execution ready route 没有复用现有 writer。
- idempotency conflict 以未结构化异常逃逸到调用方。
- plan/route 不匹配时仍写 artifact。
- 生成 ID、timestamp，读取当前时间，调用 CLI/full service。
- 修改 CLI output、action executor、route mapping 或 route preflight 语义。
- 修改临界 CLI 测试文件。
- focused tests、ruff、process hardening、registry 或 full regression 失败。

## 3. BA1/BA2 结果

BA1 语义方向基本可用，但流程上不合格：

- 新增模块 173/180、新增测试 218/220，均超过 warning line budget。
- 评估文档含未完成 marker，`process-hardening-check` 失败。
- 因此 BA1 不合入，只作为 BA2 的参考实现。

BA2 已完成修正：

- 新增 `src/ashare_evidence/autonomous_flow_scheduler_action_route_executor.py`，148 行，低于 warning 150。
- 新增 `tests/test_autonomous_flow_scheduler_action_route_executor.py`，189 行，低于 warning 190。
- `apply_phase5_scheduler_action_route(...)` 入口先调用 `preflight_phase5_scheduler_action_route(...)`。
- 主进程补充收紧：空字符串不计入 provided argument，避免空 id / 空时间绕过 preflight。
- preflight blocked、plan/route cycle 或 action mismatch、execution idempotency conflict 均返回 typed blocked result。
- ready `diagnostic_output` 复用 `record_phase5_scheduler_plan_diagnostic(...)`。
- ready `execution_output` 复用 `record_phase5_scheduler_plan_execution(...)`。
- `wait_for_next_tick` 与 `terminal` 返回 typed skipped/no-op，不写 artifact。
- 未生成 ID/timestamp，未读取当前时间，未接 CLI/full service。
- 禁止修改的两个 CLI 临界测试文件未修改。

## 4. 主进程验证

BA2 worktree 预验证：

- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_scheduler_action_route_executor.py tests/test_autonomous_flow_scheduler_action_route_preflight.py tests/test_autonomous_flow_scheduler_execution_executor.py tests/test_autonomous_flow_scheduler_executor.py -q`：33 passed。
- `ruff check src/ashare_evidence/autonomous_flow_scheduler_action_route_executor.py tests/test_autonomous_flow_scheduler_action_route_executor.py`：passed。
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check ...`：pass。

主进程复核：

- focused pytest：33 passed。
- ruff：passed。
- process hardening：passed，新增模块 148/150、新增测试 189/190，均低于 warning。
- contract registry：passed，0 issues。
- `git diff --check`：passed。
- full regression：465 passed，147 deselected。

## 5. 重跑记录

- BA1 因文件规模超过 warning 与评估文档 marker 失败，不合入。
- BA2 按同一 context pack 重跑，将新增模块压到 148/150、新增测试压到 189/190，并通过 focused pytest、ruff、registry。

## 6. 自评

本轮先固定核心执行层边界，CLI 封装与自动调度器接线应进入后续独立 trial。流程反思：子进程不能把“低于 hard limit”当作通过，达到 warning 就应压缩或拆分；主进程应继续把 warning 视为返工触发器。
