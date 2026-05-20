# Trial AM 评估记录：CLI Execution Conflict Output

状态：completed, main verification passed
输入：`TRIAL_AM_CONTEXT_PACK_CN.md`
目标：评估 CLI execution conflict 是否被结构化收口，避免无人流程因幂等冲突异常卡死。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| AM1 | CLI execution output、execution tests、本评估文件 | 捕获 idempotency conflict 并输出 typed JSON |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 冲突收口语义 | 35 |
| 无副作用边界 | 25 |
| 行为兼容与测试 | 25 |
| 文件规模治理 | 15 |

自动重跑阈值：

- conflict 仍以未捕获异常退出。
- conflict 输出缺 existing / requested execution id。
- conflict 分支写入 requested ledger 或修改 cycle。
- successful execution、missing args 或 error tick execution 行为回归。
- focused tests、ruff、process hardening、registry 或 full regression 失败。

## 3. AM1 结果

结论：通过 AM1 自测。

- 实现：`phase5-local-cycle-step --output execution` 捕获 `Phase5SchedulerExecutionIdempotencyConflictError`，返回 exit code 3 和 typed JSON；JSON 包含 `status=error`、`command`、`error_type`、`message`、`idempotency_key`、`existing_execution_id`、`requested_execution_id`、`recommended_next_action`。
- 无副作用：unit 覆盖 conflict 分支不调用 service、dry-run executor、diagnostic recorder；smoke 覆盖真实 artifact root 下预置 reservation 后再次请求不同 execution id，CLI 返回 conflict JSON，requested ledger 未写入，cycle ledger 未变化。
- 兼容性：successful execution、missing args、error tick execution 测试保持通过。
- 文件规模：handler 191 行、execution test 186 行、smoke execution test 131 行、execution helper 99 行、smoke helper 225 行，均低于 warning 线。
- 已跑 gates：focused pytest、ruff、process-hardening-check、contract-registry-check 通过；full regression 已由 AM1 执行。

## 4. 主进程验证

主进程语义审查：

- conflict 捕获范围只包住 execution recorder，不吞掉 tick、plan 或其他未知异常。
- missing args 仍在 tick 前返回 exit code 2。
- successful execution 仍输出 ledger record payload，未改变 JSON shape。
- smoke conflict 使用真实 artifact root 和 existing reservation，验证 requested ledger 不存在、cycle ledger 与冲突前一致。
- 未修改 scheduler execution ledger / reservation store 语义文件，未新增真实 scheduler action。

主进程门禁：

- focused pytest：12 passed。
- ruff：passed。
- process hardening：passed。
- contract registry：passed。
- diff check：passed。
- full regression：407 passed，147 deselected。

## 5. 重跑记录

暂无重跑。AM1 首轮实现经主进程审查后未发现必须回炉的问题。

## 6. 自评

本轮把幂等冲突从“异常卡死”升级为“可调度系统消费的 typed failure”，符合无人流程优先自恢复的方向。仍未进入真实 scheduler action；后续接入真实执行前，需要继续保持 ledger/reservation 作为唯一硬状态边界，并为每类 action 单独定义可恢复输出与副作用合同。
