# Trial BC 评估记录：CLI Action Route Apply Output

状态：completed, main verification passed
输入：`TRIAL_BC_CONTEXT_PACK_CN.md`
目标：评估 `phase5-local-cycle-step --output action-route-apply` 是否能通过 CLI 薄封装调用核心 route apply 层，并保持 blocked/conflict/no-op 的 typed 语义。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| BC1 | CLI action-route-apply output、测试、本评估文件 | 暴露核心 route apply CLI 输出 | completed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| CLI apply 链路正确 | 30 |
| 核心 apply 复用 | 30 |
| exit code 与 typed result | 25 |
| 文件规模与门禁 | 15 |

自动重跑阈值：

- `action-route-apply` 不走 `tick -> plan -> action -> route -> apply`。
- CLI handler 绕过 BA core，直接调用 diagnostic/execution writer。
- blocked apply 返回 exit 0，或 applied/skipped 返回非 0。
- 生成 ID/timestamp 或读取当前时间。
- 调用 dry-run、diagnostic output handler、execution output handler、full service。
- 修改临界测试文件。
- focused tests、ruff、process hardening、registry 或 full regression 失败。

## 3. BC1 结果

BC1 已新增 `phase5-local-cycle-step --output action-route-apply`：

- CLI 链路保持 `tick -> plan -> action -> route -> apply`。
- handler 只调用注入的 `apply_scheduler_action_route`，不直接调用 diagnostic/execution writer。
- route apply JSON 直接输出；`applied`/`skipped` exit 0，`blocked` exit 4。
- `diagnostic_id`、`observed_at`、`execution_id`、`idempotency_key`、`created_at` 原样透传；非空 `diagnostic_id` 作为 execution route 的 `diagnostic_refs`。
- 未生成 ID/timestamp，未读当前时间，未调用 dry-run、diagnostic output、execution output 或 full service。

## 4. 主进程验证

BC1 本地验证：

- focused pytest：20 passed。
- ruff：passed。
- registry：passed。
- process-hardening：首次因本文档占位符失败，回填后重跑。
- full regression：469 passed，147 deselected。

主进程复核：

- focused pytest：20 passed。
- ruff：passed。
- process hardening：passed，`cli_autonomous_flow.py` 86/95、`cli_autonomous_flow_outputs.py` 124/170、`cli_autonomous_flow_action_outputs.py` 105/150、新测试 188/190。
- contract registry：passed，0 issues。
- `git diff --check`：passed。
- full regression：469 passed，147 deselected。

## 5. 重跑记录

- BC1 的 process-hardening 首跑因评估文档占位失败，已由子进程回填后通过。

## 6. 自评

本轮将核心 route apply 层接到 CLI，但不扩展新的 writer 语义。新增测试覆盖 core apply 注入、调用顺序、参数透传、blocked exit code 与缺参不写入。
