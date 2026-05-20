# Trial K Context Pack：Phase 5 Runner Input Resolver

状态：active input  
上游：Trial C / D / E / F / G / H / I / J  
目标：实现一个只读本地 resolver，把 `phase5_cycle_ledger` 中的 refs 解析成 runner façade 需要的 typed inputs，避免后续 scheduler 自己拼路径、解析 ref 字符串或静默忽略缺失 artifact。

## 1. 本轮目标

实现一个只读、可测试、可复用的 input resolver：

- 根据 `cycle_id` 从 artifact store 读取 `phase5_cycle_ledger`。
- 默认选择最新 gate readout ref、最新 recovery ticket ref、最新 frontend projection manifest ref。
- 也允许调用方显式指定 gate/recovery/projection id。
- 返回 typed bundle，包含 cycle、gate_readout、recovery_ticket、projection_manifest 和 missing refs。
- 缺 gate / projection 不抛错，返回 `None` 并记录 missing ref，让 planner 保守降级。
- 缺 cycle 必须 fail-closed。

## 2. 非目标

- 不调用 runner façade。
- 不调用 planner。
- 不调用 closeout。
- 不写 artifact。
- 不接 LaunchAgent、cron、heartbeat 或真实 scheduler。
- 不读 DB、不读网络、不调用 LLM。
- 不构建真实 projection payload。
- 不改 API / SPA。
- 不调用 release verifier。
- 不发布 runtime。
- 不新增数据库表。
- 不新增事件 id，不新增 artifact family。

## 3. Owned Files

- `src/ashare_evidence/autonomous_flow_resolver.py`
- `tests/test_autonomous_flow_resolver.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_K_EVALUATION_CN.md`

如确需修改 artifact store、runner、planner、closeout、artifact model、registry、API 或前端，必须说明原因；默认不改。

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

## 5. Resolver 要求

建议对象和函数，不强制命名完全一致：

- `Phase5RunnerInputBundle`
- `resolve_phase5_runner_inputs(...) -> Phase5RunnerInputBundle`

建议输入：

- `cycle_id: str`
- `gate_id: str | None = None`
- `recovery_ticket_id: str | None = None`
- `projection_id: str | None = None`
- `root: Path | None = None`

建议输出字段：

- `cycle`
- `gate_readout`
- `recovery_ticket`
- `projection_manifest`
- `missing_refs`

约束：

- resolver 只读 artifact store，不写文件。
- 缺 cycle 必须抛出明确错误，不能返回空 bundle。
- gate 默认取 `cycle.gate_readout_refs[-1]`。
- recovery 默认取 `cycle.recovery_ticket_refs[-1]`；如果没有 recovery ref，可以返回 `None` 且不视为 missing。
- projection 默认从 `cycle.artifact_refs` 中倒序找 `frontend_projection_manifest:<projection_id>`。
- 显式传入 id 时优先使用显式 id。
- ref 存在但 artifact 文件缺失时，返回 `None` 并记录 missing ref。
- ref 解析出的 artifact 如果 `cycle_id` 与请求 cycle 不一致，必须 fail-closed。
- `missing_refs` 必须稳定去重。
- 不读取当前时间。

## 6. Tests

至少覆盖：

- 成功解析 cycle + gate + recovery + projection。
- 无 recovery ref 时不记录 missing。
- 缺 gate ref 时记录 missing gate。
- projection ref 在 artifact refs 中倒序选择最新。
- 显式传入 id 覆盖 cycle refs。
- ref 指向缺失 artifact 时记录 missing ref。
- ref 指向其他 cycle 的 artifact 时 fail-closed。
- 缺 cycle fail-closed。
- resolver 不写 artifact；可通过 before/after 文件列表断言。

## 7. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_resolver.py -q`
- `ruff check src/ashare_evidence/autonomous_flow_resolver.py tests/test_autonomous_flow_resolver.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_K_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_K_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
