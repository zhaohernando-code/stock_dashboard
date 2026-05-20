# Trial W Context Pack：Phase 5 Scheduler Plan Dry-run Executor

状态：active input  
上游：Trial T / U / V  
目标：实现 scheduler follow-up plan 的 dry-run executor。该层只把 plan 解释为可执行意图，不执行动作、不写 artifact、不修改 cycle，为后续真实 scheduler 执行层建立安全边界。

## 1. 本轮目标

新增纯本地 dry-run executor：

- 输入 `Phase5SchedulerFollowupPlan`。
- 输出 typed dry-run result，可 JSON 序列化。
- 输出包含 cycle id、execution mode、execution status、planned action、would execute 标志、planned effects、reason、blocking reasons。
- 对 `ready` plan 输出 `execution_status=planned`。
- 对 `blocked` plan 输出 `execution_status=blocked`。
- 不执行 retry/backoff，不创建 recovery ticket，不写 artifact，不修改 cycle。

## 2. 非目标

- 不接真实 scheduler / LaunchAgent / cron / heartbeat。
- 不执行 follow-up plan。
- 不创建 recovery ticket。
- 不写 cycle closeout。
- 不改 CLI / tick / resolver / service / runner / planner / status projection / scheduler plan。
- 不新增 artifact / event / registry id。
- 不读 DB、不读网络、不调用 LLM、不读取当前时间。
- 不发布 runtime。
- 不改 API / SPA。

## 3. Owned Files

默认只允许修改：

- `src/ashare_evidence/autonomous_flow_scheduler_executor.py`
- `tests/test_autonomous_flow_scheduler_executor.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_W_EVALUATION_CN.md`

如确需修改既有生产模块、CLI、registry、API 或前端，必须说明原因；默认不改。

## 4. Registry IDs

本轮不新增事件或 artifact id。只允许引用：

- `phase5_cycle_ledger`
- `phase5_gate_readout`
- `phase5_recovery_ticket`
- `frontend_projection_manifest`
- `runtime.publish.verified.v1`
- `iface.scheduler.phase5-cycle-ledger.v1`
- `iface.projection.api-spa.v1`

## 5. Dry-run 合同要求

建议对象和函数，不强制命名完全一致：

- `Phase5SchedulerDryRunResult`
- `dry_run_phase5_scheduler_plan(...) -> Phase5SchedulerDryRunResult`

建议字段：

- `cycle_id`
- `execution_mode`: `dry_run`
- `execution_status`: `planned` 或 `blocked`
- `planned_action`
- `would_execute`: 必须为 `False`
- `planned_effects`
- `reason`
- `blocking_reasons`

动作到 planned effects 的建议映射：

- `continue_tracking`：`keep_cycle_open_for_next_tick`
- `rebuild_projection`：`schedule_projection_rebuild`
- `retry_failed_step`：`schedule_retry`
- `open_recovery_ticket`：`prepare_recovery_ticket`
- `block_cycle`：`mark_cycle_blocked`
- `redesign`：`schedule_redesign_review`
- `none`：`no_op`

约束：

- 纯函数，不读写文件、不读 DB、不读网络、不调用 LLM、不读取当前时间。
- 不执行任何 action。
- 输出不包含完整 plan nested payload、tick payload、artifact payload、release manifest ref、digest 或 traceback。
- 稳定去重 planned effects 和 blocking reasons。
- 不修改输入对象。

## 6. Tests

至少覆盖：

- ready continue tracking dry-run。
- ready rebuild projection dry-run。
- ready retry failed step dry-run。
- ready open recovery ticket dry-run。
- blocked block cycle dry-run。
- ready redesign dry-run。
- none/no-op dry-run。
- planned effects 和 blocking reasons 稳定去重。
- payload 不泄露 nested plan/tick payload 或敏感 refs。
- 不修改输入对象。

## 7. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_scheduler_executor.py tests/test_autonomous_flow_scheduler_plan.py -q`
- `ruff check src/ashare_evidence/autonomous_flow_scheduler_executor.py tests/test_autonomous_flow_scheduler_executor.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_W_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_W_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
