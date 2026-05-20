# Trial AJ 评估记录：Scheduler Safe Execution Entry

状态：已完成  
输入：TRIAL_AJ_CONTEXT_PACK_CN.md  
目标：评估 CLI safe execution entry 是否能把 scheduler plan 安全记录为 execution ledger，并保持无真实 action 副作用。

## 1. 子任务

| 子进程 | owned files | 目标 | 结果 |
| --- | --- | --- | --- |
| AJ1 | scheduler executor、CLI execution output、execution tests、本评估文件 | 接入 safe execution ledger 入口 | 完成 |

## 2. 评分

| 维度 | 权重 | 结果 |
| --- | ---: | --- |
| Execution ledger 集成语义 | 35 | 通过，executor 调用既有 recorder，保留 reservation 与 legacy conflict 语义 |
| CLI 无副作用与参数保护 | 25 | 通过，execution 输出只走 tick、follow-up plan、ledger recorder |
| Idempotency / migration 保护延续 | 20 | 通过，conflict typed error 向上传播，requested ledger 不产生 |
| 文件规模与门禁 | 20 | 通过，新 CLI execution 测试 176 行，smoke execution 测试 81 行 |

自动重跑阈值检查：

- execution output 未执行真实 scheduler action。
- 缺少 execution id、idempotency key、created at 时在 tick 前返回 error JSON，exit code 为 2。
- idempotency conflict 未被吞掉，requested ledger 不写入。
- CLI output 未泄露 nested tick、plan、service payload，也未泄露敏感 refs。
- 新场景没有追加到接近上限的 output 测试文件。

## 3. AJ1 结果

修改文件：

- src/ashare_evidence/autonomous_flow_scheduler_executor.py
- src/ashare_evidence/cli_autonomous_flow.py
- tests/helpers_cli_autonomous_flow.py
- tests/helpers_cli_autonomous_flow_execution.py
- tests/helpers_cli_autonomous_flow_smoke.py
- tests/test_autonomous_flow_scheduler_execution_executor.py
- tests/test_cli_autonomous_flow_execution.py
- tests/test_cli_autonomous_flow_smoke_execution.py
- docs/contracts/autonomous-flow-trial/TRIAL_AJ_EVALUATION_CN.md

实现摘要：

- 新增 ledger record executor result，输出 cycle id、execution id、idempotency key、execution mode、execution status、action、would execute、ledger recorded、cycle event recorded、reason、blocking reasons、diagnostic refs。
- execution status 映射为 blocked、skipped、planned；action 为 none 时 skipped，blocked plan 或 block cycle 时 blocked。
- CLI 新增 execution output 和 execution id、idempotency key、created at 参数，缺参在 tick 前失败。
- CLI execution 路径只调用 tick、follow-up planner 和 execution recorder，不调用 service、dry-run executor 或 diagnostic recorder。
- smoke 覆盖真实 artifact root happy path 和 missing cycle 场景，missing cycle 仍写 ledger 但不记录 cycle event。

## 4. 主进程验证

AJ1 已执行门禁：

- focused pytest：22 passed。
- ruff：passed。
- git diff check：passed。
- full regression：405 passed，147 deselected。
- process hardening：pass，2 warnings；scheduler executor 240 行达到 warning 线 220，CLI 181 行达到 warning 线 170。
- registry check：pass，0 issues。

文件规模：

- scheduler executor：240 行，达到 hard 线 240。
- CLI autonomous flow：181 行，达到 warning 线 170，未超过 hard 线 190。
- CLI execution tests：176 行，低于 hard 线 220。
- CLI smoke execution tests：81 行，低于 hard 线 220。

主进程语义审查：

- 功能方向符合 Context Pack：execution output 只记录 execution ledger，不执行真实 action。
- 缺参保护发生在 tick 前。
- CLI execution 测试没有继续追加到已接近上限的 output 测试文件。
- 但 scheduler executor 达到 240 行 hard line budget，不能作为可接受状态合并。

主进程修正：

- 将 execution ledger record result 与 recorder 拆到 `src/ashare_evidence/autonomous_flow_scheduler_execution_executor.py`。
- `src/ashare_evidence/autonomous_flow_scheduler_executor.py` 保留兼容 re-export，避免破坏既有导入。
- 将 CLI execution fake result/helper 拆到 `tests/helpers_cli_autonomous_flow_execution.py`，避免通用 helper 接近 300 行。
- 拆分后文件规模：scheduler executor 177 行，scheduler execution executor 92 行，CLI autonomous flow 181 行，通用 CLI helper 244 行，execution CLI helper 41 行。

主进程最终门禁：

- focused pytest：22 passed。
- ruff：passed。
- process hardening：pass，1 warning；仅 CLI autonomous flow 达到 warning 线 170，未超过 hard 线 190。
- registry check：pass，0 issues。
- git diff check：passed。
- full regression：405 passed，147 deselected。

## 5. 重跑记录

本轮发生两次修正：

- 子进程阶段 ruff 检出 CLI import 排序问题，已用 ruff fix 修复。
- 主进程阶段发现 scheduler executor 达到 hard line budget，拆出 execution executor 模块后重跑门禁。
- 主进程阶段发现通用 CLI helper 达到 282 行维护性预警，拆出 execution 专用 helper 后重跑门禁。

## 6. 自评

本轮接入方式符合基座能力要求：没有为 CLI 单独重写 idempotency 或 reservation 逻辑，而是复用已有 recorder 作为唯一硬状态边界。主进程已拆出 ledger execution executor，解除 scheduler executor hard limit。残余风险是 CLI 模块仍达到 warning 线；后续如果继续扩展真实 action 执行，应将 CLI output handler 拆到更细的模块，避免在单文件继续堆叠。
