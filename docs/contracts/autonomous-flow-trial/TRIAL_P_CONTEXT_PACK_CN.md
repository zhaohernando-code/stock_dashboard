# Trial P Context Pack：Phase 5 Local Tick Envelope

状态：active input  
上游：Trial L / N / O  
目标：为后续真实 scheduler 增加一个可复用的本地 tick envelope。它把一次 local cycle service 调用包装成稳定结果：成功时输出 status projection，失败时输出结构化错误，避免调度入口因为异常直接卡死或只能靠人工判断。

## 1. 本轮目标

实现一个本地 tick wrapper：

- 输入与 `run_phase5_local_cycle_service(...)` 对齐。
- 成功时调用 service，再调用 `project_phase5_local_cycle_status(...)`，返回 typed tick result。
- 失败时捕获异常并返回 typed error result，不把异常继续抛给 scheduler 调用方。
- result 可 JSON 序列化，适合后续 CLI、scheduler log、heartbeat 或中台 API 使用。
- 不写 artifact、不写日志文件、不读 DB、不读网络、不调用 LLM、不读取当前时间。

## 2. 非目标

- 不接 LaunchAgent、cron、heartbeat 或真实 scheduler。
- 不做真实 retry / backoff。
- 不新增 recovery ticket。
- 不写 cycle closeout 之外的任何状态；本轮默认不触发写入。
- 不新增事件 id 或 artifact id。
- 不发布 runtime。
- 不改 API / SPA。
- 不新增数据库表。

## 3. Owned Files

默认只允许修改：

- `src/ashare_evidence/autonomous_flow_tick.py`
- `tests/test_autonomous_flow_tick.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_P_EVALUATION_CN.md`

如确需修改 CLI、service、resolver、runner、planner、status projection、artifact model、registry、API 或前端，必须说明原因；默认不改。

## 4. Registry IDs

本轮不新增事件或 artifact id。只允许引用：

- `phase5_cycle_ledger`
- `phase5_gate_readout`
- `phase5_recovery_ticket`
- `frontend_projection_manifest`
- `runtime.publish.verified.v1`
- `iface.scheduler.phase5-cycle-ledger.v1`
- `iface.projection.api-spa.v1`

## 5. Tick Envelope 要求

建议对象和函数，不强制命名完全一致：

- `Phase5LocalCycleTickResult`
- `Phase5LocalCycleTickError`
- `run_phase5_local_cycle_tick(...) -> Phase5LocalCycleTickResult`

建议成功字段：

- `cycle_id`
- `tick_status`: `ok`
- `exit_code`: `0`
- `status`: `Phase5LocalCycleStatusProjection`
- `error`: `None`
- `recommended_next_action`: 直接来自 status projection 的 `next_action`
- `summary_status`: 直接来自 status projection 的 `summary_status`

建议失败字段：

- `cycle_id`
- `tick_status`: `error`
- `exit_code`: `1`
- `status`: `None`
- `error`: 小错误对象，包含 `error_type`、`message`、`failure_class`、`recommended_recovery_action`
- `recommended_next_action`: `retry_failed_step` 或 `blocked`
- `summary_status`: `degraded` 或 `blocked`

失败分类建议：

- `ValueError`：failure class 为 `contract-violation`，`recommended_recovery_action=block_cycle`，`summary_status=blocked`。
- `FileNotFoundError`：failure class 为 `artifact-missing`，`recommended_recovery_action=open_recovery_ticket`，`summary_status=degraded`。
- 其他异常：failure class 为 `unexpected-error`，`recommended_recovery_action=retry_with_backoff`，`summary_status=degraded`。

约束：

- wrapper 不读取当前时间；如果调用方要求 closeout，仍必须显式传入 `finished_at`，由 service fail-closed。
- wrapper 不直接读写 artifact store；只能调用 service 与 status projection。
- wrapper 不吞掉错误细节，但输出必须是小 payload，不能带 traceback、完整 input bundle 或 artifact payload。
- 不允许为了 tick 修改 service 返回对象。

## 6. Tests

至少覆盖：

- 成功路径调用 service 与 projection，返回 `tick_status=ok`、`exit_code=0`。
- 成功结果 JSON 不包含 `input_bundle`、`runner_result`、release manifest ref 或 digest。
- `ValueError` 映射为 blocked contract violation，不抛异常。
- `FileNotFoundError` 映射为 degraded artifact missing，不抛异常。
- 其他异常映射为 degraded unexpected error，不抛异常。
- apply closeout 缺 `finished_at` 通过 service 抛出的 `ValueError` 映射为 blocked。
- service 调用参数完整透传，包含 `root`。

## 7. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_tick.py tests/test_autonomous_flow_status.py -q`
- `ruff check src/ashare_evidence/autonomous_flow_tick.py tests/test_autonomous_flow_tick.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_P_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_P_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
