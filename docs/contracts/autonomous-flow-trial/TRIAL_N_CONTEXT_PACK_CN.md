# Trial N Context Pack：Phase 5 本地 Status Projection

状态：active input  
上游：Trial C / D / E / F / G / H / I / J / K / L / M  
目标：把本地 cycle service 的深层结果压成稳定的小状态摘要，供后续 scheduler 日志、CLI 输出收口和未来中台/API 使用，避免 UI 或调度器直接解析内部 Pydantic 嵌套结构。

## 1. 本轮目标

实现一个纯本地、无副作用的 status projection：

- 输入 `Phase5LocalCycleServiceResult`。
- 输出稳定 typed projection object。
- 摘要包含 cycle id、cycle status、decision status、next action、claim ceiling、missing refs、blocking reasons、closeout applied、finished_at、publish verification 是否存在。
- 输出不包含完整 artifact payload，不包含 release manifest 明细，不包含截图。
- projection 是小 payload，可 JSON 序列化。

## 2. 非目标

- 不改 API / SPA。
- 不构建真实 frontend projection artifact。
- 不写 artifact。
- 不接 LaunchAgent、cron、heartbeat 或真实 scheduler。
- 不读 DB、不读网络、不调用 LLM。
- 不调用 release verifier。
- 不发布 runtime。
- 不新增数据库表。
- 不新增事件 id，不新增 artifact family。

## 3. Owned Files

- `src/ashare_evidence/autonomous_flow_status.py`
- `tests/test_autonomous_flow_status.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_N_EVALUATION_CN.md`

如确需修改 service、resolver、runner、planner、closeout、artifact store、artifact model、registry、API 或前端，必须说明原因；默认不改。

## 4. Registry IDs

本轮不新增事件或 artifact id。只允许引用：

- `phase5_cycle_ledger`
- `phase5_gate_readout`
- `phase5_recovery_ticket`
- `frontend_projection_manifest`
- `runtime.publish.verified.v1`
- `iface.scheduler.phase5-cycle-ledger.v1`
- `iface.projection.api-spa.v1`

## 5. Projection 要求

建议对象和函数，不强制命名完全一致：

- `Phase5LocalCycleStatusProjection`
- `project_phase5_local_cycle_status(...) -> Phase5LocalCycleStatusProjection`

建议输出字段：

- `cycle_id`
- `cycle_status`
- `decision_status`
- `next_action`
- `claim_ceiling`
- `decision_reason`
- `missing_refs`
- `blocking_reasons`
- `source_refs`
- `closeout_applied`
- `finished_at`
- `publish_verification_status`
- `staleness_status`
- `summary_status`

约束：

- projection 是纯函数，不读写文件、不读 DB、不读网络、不调用 LLM、不读取当前时间。
- `summary_status` 应保守汇总：blocked > degraded > completed。
- missing refs 非空时 summary 至少为 degraded。
- publish verification 缺失但本次 decision 没要求 publish 时可以是 `not_required`；如果 decision blocking reasons 包含 publish verification missing，应为 `missing`。
- source refs / missing refs / blocking reasons 稳定去重。
- 输出不应包含完整 nested input bundle 或 artifact payload。

## 6. Tests

至少覆盖：

- completed / dry-run result 投影为 completed 或 degraded，取决于 planner decision。
- blocked decision 投影为 blocked。
- missing refs 会使 summary degraded。
- publish verification missing reason 映射为 `missing`。
- closeout applied 时 finished_at 来自 closeout cycle。
- projection JSON 不包含 nested input bundle / release manifest details。
- projection 不修改输入对象。

## 7. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_status.py -q`
- `ruff check src/ashare_evidence/autonomous_flow_status.py tests/test_autonomous_flow_status.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_N_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_N_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
