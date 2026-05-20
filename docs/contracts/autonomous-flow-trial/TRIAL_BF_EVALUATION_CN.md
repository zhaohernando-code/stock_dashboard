# Trial BF 评估记录：Action Route Auto Apply CLI

状态：verified
输入：`TRIAL_BF_CONTEXT_PACK_CN.md`
目标：评估 CLI auto apply 是否能稳定调用 BE facade，并在缺少显式调度参数时 fail closed。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| BF1 | CLI parser/dispatcher/action handler、聚焦测试、本评估文件 | 暴露 auto apply CLI 并验证 fail-closed | rejected |
| BF2 | core facade 输入校验、CLI parser/dispatcher/action handler、聚焦测试、本评估文件 | 将 fail-closed 规则收敛到 core 后重跑 | completed |
| BF3 | core facade typed blocked result、core 测试、本评估文件 | 修正缺 `attempt_id` 时 required/missing 语义一致性 | completed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 调用链路顺序与 handler 隔离 | 30 |
| 缺失参数 fail-closed 且不落盘 | 30 |
| CLI 参数语义清晰且不自动生成时间 | 25 |
| 文件规模与门禁 | 15 |

自动重跑阈值：

- CLI 层读取当前时间、生成随机数或直接调用 writer。
- auto apply 输出绕过 `bind_and_apply_phase5_scheduler_action_route(...)`。
- 缺少 `attempt_id` 或 `issued_at` 时生成 artifact。
- 修改 `action-route-apply` 的既有显式参数行为。
- focused tests、ruff、process hardening、registry 或 full regression 失败。

## 3. BF1 结果

BF1 功能上跑通，但主进程审查后不合入：

- 优点：新增 `action-route-auto-apply`，链路顺序和 handler 隔离测试充分；缺 `issued_at` 与缺 `attempt_id` 都能阻断且不落盘。
- 问题：缺 `attempt_id` 的 typed blocked 结果在 CLI handler 中构造，而不是收敛到 `bind_and_apply_phase5_scheduler_action_route(...)`。这会让未来非 CLI 调度器仍可能重复实现同一阻断规则，不符合“基座能力不打补丁”的要求。
- 结论：重跑 BF2，要求 CLI handler 只调用 core facade，不自己构造 apply result。

## 4. 主进程验证

BF2 子进程在独立 worktree
`worker-workspaces/stock_dashboard/20260521-bf2-action-route-auto-apply` 完成以下验证：

- BF2 focused tests：`15 passed in 0.53s`。
- BF2 ruff：`All checks passed!`。
- BF2 process hardening：`status=pass`，`issue_count=0`，所有文件低于 warning line budget。
- BF2 registry check：`status=pass`，`issue_count=0`。
- BF2 full regression：`486 passed, 147 deselected in 21.56s`。

主进程审查 BF2 发现：缺 `attempt_id` 时 typed blocked result 的
`missing_arguments=("attempt_id",)`，但 `required_arguments` 仍沿用 route 的 required arguments，
required/missing 语义不一致。BF3 基于 BF2 产物进行窄修正，并完成以下验证：

- BF3 focused tests：`15 passed in 0.54s`。
- BF3 ruff：`All checks passed!`。
- BF3 process hardening：`status=pass`，`issue_count=0`，所有文件低于 warning line budget。
- BF3 registry check：`status=pass`，`issue_count=0`。
- BF3 full regression：`486 passed, 147 deselected in 21.27s`。

主进程合入 BF3 产物后完成以下复验：

- focused tests：`15 passed in 0.55s`。
- ruff：`All checks passed!`。
- process hardening：`status=pass`，`issue_count=0`，所有文件低于 warning line budget。
- registry check：`status=pass`，`issue_count=0`。
- full regression：`486 passed, 147 deselected in 21.18s`。

## 5. 重跑记录

- BF1 rejected：将跨入口通用的 `attempt_id` fail-closed 放在 CLI 层，设计收敛不足。
- BF2 修正：`bind_and_apply_phase5_scheduler_action_route(...)` 在 core facade 层对缺失
  `attempt_id` 返回 typed blocked result，且在该分支不会调用 argument binding 或 route apply。
- BF2 CLI：`action-route-auto-apply` 仅按 tick -> plan -> action -> route -> bind-and-apply
  顺序编排，传入 `attempt_id=args.attempt_id`、`issued_at=args.issued_at`、`root=args.artifact_root`，
  不读取当前时间、不生成随机数、不直接调用 writer、不调用 preflight 或 legacy apply handler。
- BF3 修正：缺 `attempt_id` 的 core facade blocked result 中，`required_arguments` 改为
  `("attempt_id",)`，与 `missing_arguments=("attempt_id",)` 保持同一阻断条件语义；core test
  明确断言该值。CLI handler 仍只调用 core，不构造 apply result。

## 6. 自评

BF3 继承 BF2 设计约束：缺 `attempt_id` 与缺 `issued_at` 都通过 core facade fail closed 且不落盘；
CLI handler 不构造 `Phase5SchedulerActionRouteApplyResult`，只打印 core result 并映射 exit code。
`action-route-apply` 的显式参数模式未改变。主进程已确认 `attempt_id` 作为 scheduler binding
入口参数出现在 `required_arguments`/`missing_arguments` 中符合本轮契约口径。
