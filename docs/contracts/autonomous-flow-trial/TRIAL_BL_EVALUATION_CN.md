# Trial BL 评估记录：Attempt Route Auto Apply Core

状态：verified
输入：`TRIAL_BL_CONTEXT_PACK_CN.md`
目标：评估显式 attempt context + action route bind/apply 组合 core 是否能减少外层编排解析，同时保持执行边界可审计。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| BL1 | attempt route auto-apply core、测试、本评估文件 | 新增显式组合原语 | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 显式 attempt context 组合 | 30 |
| 执行路径隔离与 fail-closed | 30 |
| 结果可审计性 | 20 |
| 文件规模与验证 | 20 |

自动重跑阈值：

- 缺 `issued_at` 或 `runner_id` 时调用 bind/apply 或写 artifact。
- 读取当前时间、使用 random/uuid、调用 CLI 或解析自然语言 reason。
- 既有 auto-apply 缺 `attempt_id` fail-closed 行为被改变。
- 组合 result 不暴露 `attempt_id` 或丢失 apply 结果关键字段。
- focused tests、ruff、process hardening、registry 或 full regression 失败。

## 3. BL1 结果

- 新增 `build_attempt_context_and_apply_phase5_scheduler_action_route(...)` 作为显式组合 core。
- 组合层先调用 `build_phase5_scheduler_attempt_context(cycle_id=route.cycle_id, issued_at=issued_at, runner_id=runner_id)`；blocked 时直接返回 typed result，不调用 bind/apply。
- context ready 后只把生成的 `attempt_id` 传给既有 `bind_and_apply_phase5_scheduler_action_route(...)`，未改变其缺 `attempt_id` fail-closed 行为。
- `Phase5SchedulerAttemptRouteApplyResult` 暴露 attempt context 状态、apply 状态、preflight、输出、参数缺失、artifact id、idempotency 与错误类型。
- 未接 CLI，未读取当前时间，未使用 random/uuid，未解析 `route.reason`，未新增 artifact family。

## 4. 主进程验证

主进程复核隔离 worktree diff 后并入集成分支。BL1 本地验证与主进程 focused gates 均通过：

- Focused tests：BL1 `9 passed in 0.25s`；main `9 passed in 0.27s`。
- Ruff：passed。
- Process hardening：status=pass，issue_count=0。
- Registry：status=pass，issue_count=0。
- Full regression：BL1 `509 passed, 147 deselected in 21.26s`；main `509 passed, 147 deselected in 21.10s`。

主进程语义复核：

- 新组合模块 94 行，低于 warning；既有 auto-apply 模块保持 64 行、旧测试保持 182 行，未继续堆叠临界文件。
- 缺 `issued_at` 或 `runner_id` 时不调用 bind/apply，且没有 artifact 写入。
- 组合 result 保留 attempt context 与 apply result 关键字段，可作为后续无人入口的审计载体。

## 5. 重跑记录

- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_scheduler_action_route_attempt_auto_apply.py tests/test_autonomous_flow_scheduler_action_route_auto_apply.py -q`：9 passed。
- `ruff check src/ashare_evidence/autonomous_flow_scheduler_action_route_attempt_auto_apply.py src/ashare_evidence/autonomous_flow_scheduler_action_route_auto_apply.py tests/test_autonomous_flow_scheduler_action_route_attempt_auto_apply.py`：passed。
- `PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check ...`：status=pass，issue_count=0。
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check ...`：status=pass，issue_count=0。
- `PYTHONPATH=src python3 -m pytest -q`：509 passed，147 deselected。

## 6. 自评

实现范围保持在 core 组合层；既有 auto-apply 模块和测试未扩写，后续无人入口可直接复用该 typed result 做审计和状态传播。
