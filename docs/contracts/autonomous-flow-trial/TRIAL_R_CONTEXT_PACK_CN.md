# Trial R Context Pack：Phase 5 Structured Resolution Errors

状态：active input  
上游：Trial K / P / Q  
目标：让 resolver 的 fail-closed 错误携带结构化分类，tick envelope 能区分“缺失工件”和“合同违规”，不再把所有 resolver `ValueError` 都粗略映射为 blocked。

## 1. 本轮目标

结构化 autonomous-flow 输入解析错误：

- `Phase5RunnerInputResolutionError` 保持 `ValueError` 兼容性。
- error 增加小型结构化字段，例如 `failure_class`、`recommended_recovery_action`、`summary_status`、`recommended_next_action`。
- 缺失必需 cycle ledger 时归类为 `artifact-missing`，tick 输出 degraded + retry。
- artifact cycle mismatch 时归类为 `contract-violation`，tick 输出 blocked + blocked。
- tick 优先识别 resolver structured error；其他 `ValueError` 仍按原 contract violation 处理。

## 2. 非目标

- 不改变 resolver 的 missing refs 语义：缺 gate / projection 仍进入 `missing_refs`，不抛异常。
- 不改变 service / runner / planner 的业务行为。
- 不新增 artifact / event / registry id。
- 不接 LaunchAgent、cron、heartbeat 或真实 scheduler。
- 不改 CLI 默认路径。
- 不读 DB、不读网络、不调用 LLM、不读取当前时间。
- 不发布 runtime。
- 不改 API / SPA。

## 3. Owned Files

默认只允许修改：

- `src/ashare_evidence/autonomous_flow_resolver.py`
- `src/ashare_evidence/autonomous_flow_tick.py`
- `tests/test_autonomous_flow_resolver.py`
- `tests/test_autonomous_flow_tick.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_R_EVALUATION_CN.md`

如确需修改 CLI、service、runner、planner、status projection、artifact model、registry、API 或前端，必须说明原因；默认不改。

## 4. Registry IDs

本轮不新增事件或 artifact id。只允许引用：

- `phase5_cycle_ledger`
- `phase5_gate_readout`
- `phase5_recovery_ticket`
- `frontend_projection_manifest`
- `runtime.publish.verified.v1`
- `iface.scheduler.phase5-cycle-ledger.v1`
- `iface.projection.api-spa.v1`

## 5. Structured Error 要求

建议字段：

- `failure_class`: `artifact-missing` 或 `contract-violation`
- `recommended_recovery_action`: `open_recovery_ticket` 或 `block_cycle`
- `summary_status`: `degraded` 或 `blocked`
- `recommended_next_action`: `retry_failed_step` 或 `blocked`

映射要求：

- 缺必需 cycle ledger：`artifact-missing`、`open_recovery_ticket`、`degraded`、`retry_failed_step`。
- artifact cycle mismatch：`contract-violation`、`block_cycle`、`blocked`、`blocked`。
- tick 捕获 `Phase5RunnerInputResolutionError` 时使用结构化字段输出 envelope。
- tick 捕获普通 `ValueError` 时保持 Trial P 行为：contract violation + blocked。
- tick 捕获 `FileNotFoundError` 和其他异常的行为保持 Trial P 语义。

约束：

- 不解析错误消息字符串来判断分类。
- 不把 traceback、input bundle、artifact payload、release manifest ref 或 digest 放进 tick error。
- 保持 `Phase5RunnerInputResolutionError` 是 `ValueError` 的子类，避免破坏现有 service tests。

## 6. Tests

至少覆盖：

- missing cycle error 仍是 `Phase5RunnerInputResolutionError` 且也是 `ValueError`。
- missing cycle error 结构化字段为 degraded artifact-missing recovery。
- cycle mismatch error 结构化字段为 blocked contract violation。
- resolver 缺 gate / projection 仍返回 `missing_refs`，不抛异常。
- tick 对 missing cycle structured resolver error 输出 degraded artifact-missing。
- tick 对 mismatch structured resolver error 输出 blocked contract-violation。
- tick 对普通 `ValueError` 仍输出 blocked contract-violation。
- focused tests 与 registry check 通过。

## 7. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_resolver.py tests/test_autonomous_flow_tick.py -q`
- `ruff check src/ashare_evidence/autonomous_flow_resolver.py src/ashare_evidence/autonomous_flow_tick.py tests/test_autonomous_flow_resolver.py tests/test_autonomous_flow_tick.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_R_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_R_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
