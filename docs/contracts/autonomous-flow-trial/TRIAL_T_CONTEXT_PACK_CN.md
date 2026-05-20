# Trial T Context Pack：Phase 5 Scheduler Follow-up Plan

状态：active input  
上游：Trial P / Q / R / S  
目标：把 `Phase5LocalCycleTickResult` 转换为稳定的 scheduler follow-up plan。该层只产生命令计划，不执行重试、不写 recovery ticket、不修改 cycle、不接真实 scheduler。

## 1. 本轮目标

实现纯本地 follow-up planner：

- 输入 `Phase5LocalCycleTickResult`。
- 输出 typed scheduler plan，可 JSON 序列化。
- 成功 tick 根据 `summary_status` 与 `recommended_next_action` 生成 follow-up action。
- 失败 tick 根据 `error.recommended_recovery_action` 与 `summary_status` 生成 follow-up action。
- 输出包含 cycle id、plan status、action、reason、source tick status、summary status、claim ceiling（如有）、blocking reasons。
- 计划结果是小 payload，不包含完整 tick status payload、input bundle、artifact payload、release manifest ref、digest 或 traceback。

## 2. 非目标

- 不执行 retry/backoff。
- 不创建 recovery ticket。
- 不写 artifact。
- 不修改 cycle closeout。
- 不改 CLI / tick / resolver / service / runner / planner / status projection。
- 不新增 artifact / event / registry id。
- 不接 LaunchAgent、cron、heartbeat 或真实 scheduler。
- 不读 DB、不读网络、不调用 LLM、不读取当前时间。
- 不发布 runtime。
- 不改 API / SPA。

## 3. Owned Files

默认只允许修改：

- `src/ashare_evidence/autonomous_flow_scheduler_plan.py`
- `tests/test_autonomous_flow_scheduler_plan.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_T_EVALUATION_CN.md`

如确需修改生产既有模块、registry、API 或前端，必须说明原因；默认不改。

## 4. Registry IDs

本轮不新增事件或 artifact id。只允许引用：

- `phase5_cycle_ledger`
- `phase5_gate_readout`
- `phase5_recovery_ticket`
- `frontend_projection_manifest`
- `runtime.publish.verified.v1`
- `iface.scheduler.phase5-cycle-ledger.v1`
- `iface.projection.api-spa.v1`

## 5. Plan 合同要求

建议对象和函数，不强制命名完全一致：

- `Phase5SchedulerFollowupPlan`
- `plan_phase5_scheduler_followup(...) -> Phase5SchedulerFollowupPlan`

建议字段：

- `cycle_id`
- `plan_status`: `ready` 或 `blocked`
- `action`: `continue_tracking`、`rebuild_projection`、`retry_failed_step`、`open_recovery_ticket`、`block_cycle`、`redesign`、`none`
- `reason`
- `source_tick_status`
- `summary_status`
- `claim_ceiling`
- `blocking_reasons`

映射建议：

- tick ok + summary completed + next_action continue_tracking：`ready / continue_tracking`。
- tick ok + next_action rebuild_projection：`ready / rebuild_projection`。
- tick ok + next_action retry_failed_step：`ready / retry_failed_step`。
- tick ok + next_action redesign：`ready / redesign`。
- tick ok + next_action blocked 或 summary blocked：`blocked / block_cycle`。
- tick error + recovery action open_recovery_ticket：`ready / open_recovery_ticket`。
- tick error + recovery action retry_with_backoff：`ready / retry_failed_step`。
- tick error + recovery action block_cycle：`blocked / block_cycle`。

约束：

- planner 是纯函数，不读写文件、不读 DB、不读网络、不调用 LLM、不读取当前时间。
- 不解析错误消息字符串。
- 稳定去重 blocking reasons。
- 输出不应包含完整 `status` 或 `error` nested payload。
- 输入不应被修改。

## 6. Tests

至少覆盖：

- completed continue tracking。
- degraded rebuild projection。
- degraded retry failed step。
- blocked ok tick 转为 block cycle。
- missing cycle error/open recovery ticket。
- unexpected error/retry with backoff 转为 retry failed step。
- contract violation/block cycle。
- payload 不泄露 nested status/error、release manifest ref、digest。
- blocking reasons 稳定去重。
- 不修改输入对象。

## 7. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_scheduler_plan.py tests/test_autonomous_flow_tick.py -q`
- `ruff check src/ashare_evidence/autonomous_flow_scheduler_plan.py tests/test_autonomous_flow_scheduler_plan.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_T_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_T_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
