# Trial AP 评估记录：Scheduler Action Contract

状态：completed, main verification passed
输入：`TRIAL_AP_CONTEXT_PACK_CN.md`
目标：评估 scheduler action contract 是否能在真实 action 接入前集中表达副作用边界。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| AP1 | action contract、executor 复用、测试、本评估文件 | 建立无副作用 scheduler action contract |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| action 覆盖完整性 | 30 |
| 副作用边界清晰度 | 30 |
| executor 复用与兼容 | 25 |
| 文件规模治理 | 15 |

自动重跑阈值：

- 任一 scheduler action 缺 contract。
- contract 函数执行 IO、DB、网络或 artifact 写入。
- dry-run 与 contract 出现重复且不一致的 planned effects 映射。
- 真实 action、副作用写入、CLI output 或 ledger/reservation 语义被改动。
- focused tests、ruff、process hardening、registry 或 full regression 失败。

## 3. AP1 结果

实现完成：

- 新增 `autonomous_flow_scheduler_action_contract.py`，为所有 `Phase5SchedulerAction` 声明 execution strategy、planned effects、required inputs、allowed side effects、durable outputs 与 `may_close_cycle`。
- `continue_tracking` / `none` 明确 `allowed_side_effects=("none",)` 且无 durable outputs。
- `open_recovery_ticket` / `retry_failed_step` / `rebuild_projection` / `redesign` / `block_cycle` 均声明 required inputs 与 durable outputs。
- `block_cycle` 声明 `may_close_cycle=True`，但本轮只作为 contract 描述，不执行 closeout。
- dry-run executor 删除本地 planned effects 映射，改为复用 action contract 的 `planned_effects`。
- 未执行真实 scheduler action，未写 recovery ticket，未修改 cycle closeout，未新增 CLI output，未修改 scheduler execution ledger / reservation store 语义文件。

AP1 focused gates：

- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_scheduler_action_contract.py tests/test_autonomous_flow_scheduler_executor.py -q`：通过，19 passed。
- `ruff check src/ashare_evidence/autonomous_flow_scheduler_action_contract.py src/ashare_evidence/autonomous_flow_scheduler_executor.py tests/test_autonomous_flow_scheduler_action_contract.py tests/test_autonomous_flow_scheduler_executor.py`：通过。
- `PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check ...`：通过。
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check ...`：通过。
- `git diff --check`：通过。
- `PYTHONPATH=src python3 -m pytest -q`：通过，421 passed, 147 deselected。

## 4. 主进程验证

主进程语义审查：

- 所有 `Phase5SchedulerAction` 均有 contract，dry-run executor 已删除本地 planned effects 映射并改为读取 contract。
- contract 模块只包含 Pydantic model 与静态映射，无 IO、DB、网络、artifact 写入或当前时间读取。
- 未修改 CLI output、ledger / reservation store、cycle closeout、recovery ticket 写入或真实 action 执行路径。
- 主进程发现 AP1 的 `durable_outputs` 中包含未注册的新概念名：retry intent、redesign review intent 与 cycle closeout。由于本轮非目标是不新增 artifact family，主进程已收敛为既有注册输出：`phase5_scheduler_execution_ledger`、`phase5_scheduler_diagnostic`、`phase5_cycle_ledger`，并新增测试防止 durable outputs 漂到未注册概念。

主进程门禁：

- focused pytest：19 passed。
- ruff：passed。
- process hardening：passed。
- contract registry：passed。
- diff check：passed。
- full regression：421 passed，147 deselected。

## 5. 重跑记录

无需重跑子进程。主进程修正的是合同命名边界：AP1 通过了功能门禁，但声明了未注册 durable output 概念；已在主进程补测试并复跑门禁。

## 6. 自评

本轮把 scheduler action 语义集中到纯 contract 层，为后续真实 action 接入提供了前置边界。残余风险是 contract 仍是声明式约束，下一轮真实 action 接入时必须把 allowed side effects 与 idempotency ledger、reservation、durable output 校验绑定起来。
