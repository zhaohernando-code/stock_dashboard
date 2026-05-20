# Trial BD 评估记录：Scheduler Action Route Argument Binding

状态：completed, main verification passed
输入：`TRIAL_BD_CONTEXT_PACK_CN.md`
目标：评估 route argument binding 是否能为无人调度器稳定生成 apply 参数，同时保持纯函数、可重放、无副作用。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| BD1 | route argument binding、测试、本评估文件 | 新增纯参数绑定层 | completed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 参数生成准确 | 35 |
| 纯函数与可重放 | 30 |
| blocked/fail-closed 语义 | 20 |
| 文件规模与门禁 | 15 |

自动重跑阈值：

- 需要时间的 route 在缺 `issued_at` 时仍返回 ready。
- `wait_for_next_tick` / `terminal` 被错误要求参数。
- 参数 id 不稳定、包含文件名不安全字符，或不能由 cycle/action/attempt 追溯。
- 读取当前时间、生成随机数、写 artifact、调用 apply/core writer/CLI。
- 修改 route mapping、route preflight 或 route apply core。
- focused tests、ruff、process hardening、registry 或 full regression 失败。

## 3. BD1 结果

- 新增 `src/ashare_evidence/autonomous_flow_scheduler_action_route_arguments.py`。
- 新增 `Phase5SchedulerActionRouteArgumentBindingResult` 与纯函数 `bind_phase5_scheduler_action_route_arguments(...)`。
- `wait_for_next_tick` / `terminal` 返回 `ready`，不生成参数。
- `diagnostic_output` 在 `issued_at` 存在时生成 `diagnostic_id` / `observed_at`，其中 `observed_at == issued_at`。
- `execution_output` 在 `issued_at` 存在时生成 `execution_id` / `idempotency_key` / `created_at`，其中 `created_at == issued_at`，`idempotency_key` 由 `execution_id` 稳定派生。
- 缺失 `issued_at` 时返回 typed `blocked`，`provided_arguments={}`，不生成部分参数。
- 主进程补充收紧：空字符串 `issued_at` 也视为缺失，避免生成空 `observed_at` / `created_at`。
- ID 由 `cycle_id` / `action` / `attempt_id` 的文件名安全 slug 加稳定 sha256 短摘要组成，不读当前时间、不随机、不写 artifact、不调用 apply/writer/CLI。
- 新增 `tests/test_autonomous_flow_scheduler_action_route_arguments.py` 覆盖 wait/terminal ready、diagnostic/execution 参数生成、缺 `issued_at` blocked、ID 稳定可追溯与无文件副作用。

## 4. 主进程验证

- Focused pytest：`20 passed in 0.40s`。
- Ruff：`All checks passed!`。
- 行数：binding 模块 117 行，测试 140 行，router 114 行，executor 148 行，均低于 warning budget。
- Process hardening：`status=pass`，`issue_count=0`。
- Registry：`status=pass`，`issue_count=0`。
- Full regression：`475 passed, 147 deselected in 22.53s`。

主进程复核：

- focused pytest：20 passed。
- ruff：passed。
- process hardening：passed，binding 模块 117/150，测试 142/190。
- contract registry：passed，0 issues。
- `git diff --check`：passed。
- full regression：475 passed，147 deselected。

## 5. 重跑记录

暂无。

## 6. 自评

本轮补齐无人调度器自动传参前置能力，但仍不接 CLI 和真实 apply。残余风险：本层仅绑定 apply 所需参数，尚未集成到无人调度器调用链；真实 apply 发布与浏览器验证不属于本轮纯函数范围。
