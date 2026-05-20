# Trial J Context Pack：Phase 5 本地 Runner Façade

状态：active input  
上游：Trial C / D / E / F / G / H / I  
目标：把本地 planner 和 closeout 原语组合成一个稳定 façade，让后续 scheduler 只调用一个确定性本地入口完成“计划下一步 + 可选 closeout”，而不是在 scheduler 中散落业务判断。

## 1. 本轮目标

实现一个无调度副作用、可测试、可复用的 runner façade：

- 输入由调用方传入的 typed artifacts 组成。
- 调用 `plan_phase5_next_step(...)` 得到 planner decision。
- 在 `apply_closeout=True` 时，调用 `finish_phase5_cycle(...)` 写回 cycle closeout。
- 在 `apply_closeout=False` 时，只返回 decision，不写 artifact。
- 输出 typed result，包含 planner decision、是否应用 closeout、closeout cycle、和 skipped reason。
- 所有时间戳由调用方传入；如果应用 closeout，必须显式传入 `finished_at`。

## 2. 非目标

- 不接 LaunchAgent、cron、heartbeat 或真实 scheduler。
- 不读取 artifact store 自动查找 gate/recovery/projection。
- 不启动 runner、LLM、DB、网络或发布脚本。
- 不构建真实 projection payload。
- 不改 API / SPA。
- 不调用 release verifier。
- 不发布 runtime。
- 不新增数据库表。
- 不新增事件 id，不新增 artifact family。

## 3. Owned Files

- `src/ashare_evidence/autonomous_flow_runner.py`
- `tests/test_autonomous_flow_runner.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_J_EVALUATION_CN.md`

如确需修改 planner、closeout、artifact model、store、registry、API 或前端，必须说明原因；默认不改。

## 4. Registry IDs

本轮不新增事件或 artifact id。只允许引用：

- `phase5_cycle_ledger`
- `phase5_gate_readout`
- `phase5_recovery_ticket`
- `frontend_projection_manifest`
- `iface.scheduler.phase5-cycle-ledger.v1`
- `iface.gate.phase5-scheduler.v1`
- `iface.projection.publish-verifier.v1`
- `iface.recovery.scheduler-reviewer.v1`

## 5. Façade 要求

建议对象和函数，不强制命名完全一致：

- `Phase5RunnerResult`
- `run_phase5_local_cycle_step(...) -> Phase5RunnerResult`

建议输入：

- `cycle: Phase5CycleLedgerArtifact`
- `gate_readout: Phase5GateReadoutArtifact | None`
- `recovery_ticket: Phase5RecoveryTicketArtifact | None`
- `projection_manifest: FrontendProjectionManifestArtifact | None`
- `finished_at: str | None`
- `apply_closeout: bool = False`
- `require_publish_verification: bool = False`
- `root: Path | None = None`

建议输出字段：

- `cycle_id`
- `decision`
- `closeout_applied`
- `closeout_cycle`
- `skipped_reason`

约束：

- façade 不读 DB、不读网络、不读文件、不调用 LLM、不读取当前时间。
- `apply_closeout=False` 时不得写 artifact，不得调用 `finish_phase5_cycle`。
- `apply_closeout=True` 且 `finished_at` 缺失时必须 fail-closed，不允许自动取当前时间。
- `apply_closeout=True` 时只能使用 planner 输出的 `closeout_status` 和 `next_action` 调用 `finish_phase5_cycle`。
- 如果 planner 输出 `completed` + `continue_tracking`，不能直接传给 closeout；应在 façade 内保守转换为 `degraded` + `continue_tracking`，或拒绝应用 closeout。推荐保守转换为 `degraded`，因为 closeout schema 允许该组合，且表示本轮需要继续观察而非彻底完成。
- 输出必须保留 planner decision，便于 scheduler 记录和审计。

## 6. Tests

至少覆盖：

- dry run 只返回 decision，不写 artifact。
- apply closeout 会写入 cycle closeout，并保留 planner decision。
- apply closeout 缺 `finished_at` 失败。
- planner blocker 输出会 closeout 为 blocked。
- planner projection stale 会 closeout 为 degraded + rebuild projection。
- planner completed + continue tracking 时，façade 不产生非法 closeout。
- façade 不修改输入对象。

## 7. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_runner.py -q`
- `ruff check src/ashare_evidence/autonomous_flow_runner.py tests/test_autonomous_flow_runner.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_J_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_J_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
