# Trial AA Context Pack：Scheduler Plan Diagnostic Recorder

状态：active input  
上游：Trial T / W / X / Y / Z  
目标：把 scheduler follow-up plan 与 `phase5_scheduler_diagnostic` 持久化原语连接起来，提供一个执行真实 action 前的诊断记录入口。该入口只写 diagnostic，不执行 scheduler action，不写 recovery ticket。

## 1. 背景

当前链路已经具备：

- tick envelope：把 local cycle service 成功/失败收敛成 typed result。
- follow-up plan：把 tick result 转成 scheduler 可消费计划。
- dry-run executor：输出无副作用 execution intent。
- scheduler diagnostic artifact：允许在 cycle 缺失时记录诊断事实。

下一步需要一个很小的执行前记录层：当 scheduler 决定某个 plan 需要被追踪或无法安全执行时，先把 plan 的小摘要写入 diagnostic artifact，保证失败不会只停留在 CLI 输出或会话上下文里。

## 2. 本轮目标

在 scheduler executor 层新增 diagnostic recorder：

- 输入 `Phase5SchedulerFollowupPlan`、`diagnostic_id`、`observed_at`、可选 artifact root。
- 调用 `record_phase5_scheduler_diagnostic(...)` 写 diagnostic artifact。
- cycle 存在时，复用 Trial Y 行为，只追加 diagnostic event ref。
- cycle 缺失时，仍写 diagnostic，不抛错。
- 返回一个小 result，说明 diagnostic 是否写入、cycle event 是否追加、action、severity、reason。
- 不执行真实 scheduler action。

## 3. 非目标

- 不接 CLI。
- 不写 recovery ticket。
- 不创建 follow-up cycle。
- 不执行 retry、projection rebuild、redesign 或 block closeout。
- 不修改 tick、plan、dry-run 输出合同。
- 不改 registry/schema。
- 不改 API / SPA。

## 4. Owned Files

默认只允许修改：

- `src/ashare_evidence/autonomous_flow_scheduler_executor.py`
- `tests/test_autonomous_flow_scheduler_executor.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_AA_EVALUATION_CN.md`

如确需修改 artifact model、artifact store、cycle primitive、CLI、registry 或 schema，必须说明原因；默认不改。

## 5. 合同要求

新增建议函数：

```python
record_phase5_scheduler_plan_diagnostic(
    plan: Phase5SchedulerFollowupPlan,
    *,
    diagnostic_id: str,
    observed_at: str,
    root: Path | None = None,
) -> Phase5SchedulerDiagnosticRecordResult
```

Result 最小字段：

- `cycle_id`
- `diagnostic_id`
- `execution_mode`: `diagnostic_record`
- `execution_status`: `recorded`
- `action`
- `severity`
- `diagnostic_recorded`: `true`
- `cycle_event_recorded`: bool
- `reason`
- `blocking_reasons`

映射要求：

- `plan_status=blocked` 或 `action=block_cycle` -> severity `blocked`
- `action=open_recovery_ticket` 或 `action=retry_failed_step` -> severity `error`
- `action=rebuild_projection` 或 `action=redesign` -> severity `warning`
- `action=continue_tracking` 或 `action=none` -> severity `info`
- recommended recovery action：
  - `open_recovery_ticket` -> `open_recovery_ticket`
  - `retry_failed_step` -> `retry_with_backoff`
  - `block_cycle` -> `block_cycle`
  - 其他 -> `none`
- failure class：
  - blocked plan 或 block cycle -> `blocked-plan`
  - open recovery ticket / retry / rebuild / redesign -> `execution-precondition-failed`
  - continue / none -> `none`

安全要求：

- 输出和 diagnostic payload 不包含完整 tick payload、status projection、input bundle、runner result、release manifest ref、digest、traceback。
- 不修改输入 plan 对象。

## 6. Tests

至少覆盖：

- happy path：cycle 存在时写 diagnostic，并追加 event ref，但不改变 cycle status / next_action / finished_at。
- missing cycle：仍写 diagnostic，result 中 `cycle_event_recorded=false`。
- action 到 severity / recommended recovery action / failure class 的映射。
- 输出不泄露 nested plan/tick payload 或敏感 refs。
- dry-run executor 既有测试继续通过。

## 7. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_scheduler_executor.py tests/test_autonomous_flow.py tests/test_autonomous_flow_artifacts.py -q`
- `ruff check src/ashare_evidence/autonomous_flow_scheduler_executor.py tests/test_autonomous_flow_scheduler_executor.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_AA_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_AA_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
