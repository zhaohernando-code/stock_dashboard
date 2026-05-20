# Trial I Context Pack：Phase 5 本地 Planner 决策原语

状态：active input  
上游：Trial C / D / E / F / G / H  
目标：在已有 cycle、gate、recovery、projection、closeout 原语基础上，实现一个纯本地 planner，让后续 scheduler 能根据 durable artifacts 得到下一步动作建议，而不是在 scheduler 内部散落业务判断。

## 1. 本轮目标

实现一个无副作用、可测试、可复用的 planner：

- 输入由调用方传入的 typed artifacts 组成。
- 输出一个 typed decision object，包含建议的 closeout status、next action、claim ceiling、decision reason、blocking reasons 和 source refs。
- 对 gate blocked、recovery blocked、projection stale/degraded、缺 gate、publish verification pending 等状态做保守决策。
- 不写 artifact、不更新 cycle、不启动 scheduler。
- 不新增事件 id，不新增 artifact family。

## 2. 非目标

- 不接 LaunchAgent、cron、heartbeat 或真实 scheduler。
- 不读取 artifact store。
- 不调用 `finish_phase5_cycle`。
- 不写 `phase5_cycle_ledger`。
- 不改 API / SPA。
- 不调用 release verifier。
- 不发布 runtime。
- 不新增数据库表。

## 3. Owned Files

- `src/ashare_evidence/autonomous_flow_planner.py`
- `tests/test_autonomous_flow_planner.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_I_EVALUATION_CN.md`

如确需修改 `autonomous_flow.py`、artifact model、store、registry、API 或前端，必须说明原因；默认不改。

## 4. Registry IDs

本轮不新增事件或 artifact id。只允许引用：

- `phase5_cycle_ledger`
- `phase5_gate_readout`
- `phase5_recovery_ticket`
- `frontend_projection_manifest`
- `runtime.publish.verified.v1`
- `iface.scheduler.phase5-cycle-ledger.v1`
- `iface.gate.phase5-scheduler.v1`
- `iface.projection.publish-verifier.v1`
- `iface.recovery.scheduler-reviewer.v1`

## 5. Planner 要求

建议对象和函数，不强制命名完全一致：

- `Phase5PlannerDecision`
- `plan_phase5_next_step(...) -> Phase5PlannerDecision`

建议输入：

- `cycle: Phase5CycleLedgerArtifact`
- `gate_readout: Phase5GateReadoutArtifact | None`
- `recovery_ticket: Phase5RecoveryTicketArtifact | None`
- `projection_manifest: FrontendProjectionManifestArtifact | None`
- `require_publish_verification: bool = False`

建议输出字段：

- `cycle_id`
- `closeout_status`: `completed` / `degraded` / `blocked`
- `next_action`: ledger 既有 next action 枚举
- `claim_ceiling`
- `decision_reason`
- `blocking_reasons`
- `source_refs`

约束：

- planner 是纯函数，不读 DB、不读网络、不读文件、不写文件、不调用 LLM、不读取当前时间。
- cycle 已经是 `blocked` 时，输出 `blocked` + `next_action="blocked"`。
- recovery ticket `final_status="blocked"` 时，输出 `blocked` + `next_action="blocked"`。
- gate readout `gate_status="blocked"` 时，输出 `blocked` + `next_action="blocked"`。
- gate 缺失时，输出 `degraded` + `next_action="retry_failed_step"`，claim ceiling 不得高于 `research_observation`。
- projection 缺失时，输出 `degraded` + `next_action="rebuild_projection"`。
- projection `staleness_status` 为 `stale` 或 `degraded` 时，输出 `degraded` + `next_action="rebuild_projection"`。
- `require_publish_verification=True` 且 cycle 没有 publish verification ref 时，输出 `degraded` + `next_action="retry_failed_step"`。
- gate `next_action` 为 `redesign` / `retry_failed_step` / `rebuild_projection` / `continue_tracking` 时，planner 应保留该方向，除非更高优先级 blocker 已触发。
- planner 不得提升 claim ceiling；输出 claim ceiling 来自 gate readout，缺 gate 或 blocker 时保守降级。

建议优先级：

1. cycle 已 blocked。
2. recovery blocked。
3. gate blocked。
4. gate missing。
5. projection missing/stale/degraded。
6. publish verification pending。
7. gate requested next action。
8. completed + none。

## 6. Tests

至少覆盖：

- cycle 已 blocked 直接 blocked。
- recovery blocked 优先于 gate passed。
- gate blocked 优先于 projection fresh。
- 缺 gate 降级 retry。
- 缺 projection 降级 rebuild projection。
- stale/degraded projection 降级 rebuild projection。
- require publish verification 但缺 ref 时降级 retry。
- gate requested redesign / retry / rebuild / continue tracking 被保留。
- 所有输出 source refs 可追溯到输入 artifact id。
- planner 不修改输入对象。

## 7. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_planner.py -q`
- `ruff check src/ashare_evidence/autonomous_flow_planner.py tests/test_autonomous_flow_planner.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_I_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_I_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
