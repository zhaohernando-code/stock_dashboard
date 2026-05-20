# Trial W 评估记录：Phase 5 Scheduler Plan Dry-run Executor

状态：进行中  
输入：`TRIAL_W_CONTEXT_PACK_CN.md`  
目标：评估 scheduler follow-up plan 是否能被解释为 dry-run 执行意图，并保持无副作用。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| W1 | dry-run executor 模块、测试、本评估文件 | 实现 plan dry-run executor |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| Dry-run 合同符合度 | 35 |
| 行为映射完整性 | 30 |
| 副作用隔离 | 20 |
| 测试覆盖 | 15 |

自动重跑阈值：

- 总分低于 85。
- executor 执行动作、写 artifact、写 recovery ticket 或修改 cycle。
- executor 读写文件、读 DB、读网络、调用 LLM 或读取当前时间。
- 输出包含完整 nested plan/tick payload、release manifest ref 或 digest。
- focused tests 失败。

## 3. W1 结果

完成。

改动文件：

- `src/ashare_evidence/autonomous_flow_scheduler_executor.py`
- `tests/test_autonomous_flow_scheduler_executor.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_W_EVALUATION_CN.md`

实现内容：

- 新增 `Phase5SchedulerDryRunResult`。
- 新增 `dry_run_phase5_scheduler_plan(...)`。
- 输入 `Phase5SchedulerFollowupPlan`，输出扁平 dry-run payload。
- `ready` plan 映射为 `execution_status=planned`。
- `blocked` plan 映射为 `execution_status=blocked`。
- `would_execute` 固定为 `False`。
- action 到 planned effects 映射如下：
  - `continue_tracking` -> `keep_cycle_open_for_next_tick`
  - `rebuild_projection` -> `schedule_projection_rebuild`
  - `retry_failed_step` -> `schedule_retry`
  - `open_recovery_ticket` -> `prepare_recovery_ticket`
  - `block_cycle` -> `mark_cycle_blocked`
  - `redesign` -> `schedule_redesign_review`
  - `none` -> `no_op`
- executor 层再次脱敏 `release-manifest:*` 与 `sha256:*`。
- 稳定去重 `planned_effects` 与 `blocking_reasons`。
- 不修改输入 plan 对象。

边界确认：

- 未改 CLI / tick / resolver / service / runner / planner / status projection / scheduler plan。
- 未改 artifact model / registry / API / frontend。
- executor 不读写文件、不读 DB、不读网络、不调用 LLM、不读取当前时间。
- executor 不执行 action，不创建 recovery ticket，不修改 cycle closeout。
- 输出不包含完整 nested plan/tick payload、release manifest ref、digest、traceback。

## 4. 主进程验证

主进程复核结论：通过。

已验证：

- `dry_run_phase5_scheduler_plan(...)` 是纯函数，只读取 `Phase5SchedulerFollowupPlan`。
- 输出为扁平 `Phase5SchedulerDryRunResult`，不包含完整 nested plan/tick payload。
- `would_execute` 固定为 `False`。
- `ready` plan 映射为 `execution_status=planned`，`blocked` plan 映射为 `execution_status=blocked`。
- 覆盖所有当前 action 的 planned effect：continue tracking、rebuild projection、retry failed step、open recovery ticket、block cycle、redesign、none。
- reason 和 blocking reasons 对 release manifest ref / digest 做脱敏。
- planned effects 和 blocking reasons 稳定去重。
- 不修改输入对象。

跑偏检查：

- 本轮未修改 CLI、tick、resolver、service、runner、planner、status projection、scheduler plan、artifact model、registry、API 或 frontend。
- executor 没有执行 retry/backoff，没有创建 recovery ticket，没有写 artifact，没有修改 cycle closeout。
- 没有接入 LaunchAgent、cron、heartbeat 或真实 scheduler。
- 当前 planned effects 是静态字符串映射；后续如果 action 带参数，应升级为结构化 effect 模型，而不是继续拼字符串。

主进程门禁：

| 命令 | 结果 |
| --- | --- |
| `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_scheduler_executor.py tests/test_autonomous_flow_scheduler_plan.py -q` | 22 passed |
| `ruff check src/ashare_evidence/autonomous_flow_scheduler_executor.py tests/test_autonomous_flow_scheduler_executor.py` | pass |
| `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_W_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_W_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated` | status=pass, issue_count=0 |
| `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_scheduler_executor.py tests/test_autonomous_flow_scheduler_plan.py tests/test_autonomous_flow_tick.py tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_outputs.py tests/test_cli_autonomous_flow_smoke.py -q` | 46 passed |
| `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage` | pass |
| `git diff --check` | pass |
| `PYTHONPATH=src python3 -m pytest -q` | 336 passed, 147 deselected |

运行时发布验证：本轮只新增本地 dry-run executor，不改变用户可见 Web/runtime 行为，因此不触发发布或浏览器验收。

## 5. 重跑记录

无需重跑子进程。

原因：

- W1 输出满足 Context Pack 的 owned files 与非目标边界。
- 未发现执行副作用、输出泄露、IO/DB/网络/LLM/时间依赖或测试缺口。

## 6. 自评

评分：94 / 100。

- Dry-run 合同符合度：35 / 35。仅解释 plan 为执行意图，`would_execute=False`，无副作用。
- 行为映射完整性：29 / 30。Context Pack 列出的 action 均有测试覆盖；后续如果 `Phase5SchedulerAction` 扩展，需要同步 executor 映射。
- 副作用隔离：20 / 20。模块无文件、DB、网络、LLM、当前时间依赖。
- 测试覆盖：10 / 15。覆盖核心映射、脱敏、去重和输入不可变；未接真实 CLI，因为本轮硬约束要求不改 CLI。

子进程验证：

- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_scheduler_executor.py tests/test_autonomous_flow_scheduler_plan.py -q`：22 passed。
- `ruff check src/ashare_evidence/autonomous_flow_scheduler_executor.py tests/test_autonomous_flow_scheduler_executor.py`：passed。
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_W_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_W_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`：passed，`issue_count=0`。
- `git diff --check`：passed。

剩余风险：

- 当前是 dry-run executor，不接真实 scheduler / LaunchAgent / cron / heartbeat。
- 当前 `planned_effects` 是静态映射；后续如果 scheduler plan 引入更细粒度 action 参数，需要升级为结构化 effect 模型。
