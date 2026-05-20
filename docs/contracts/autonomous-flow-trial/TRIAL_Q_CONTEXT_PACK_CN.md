# Trial Q Context Pack：Phase 5 CLI Tick Envelope

状态：active input  
上游：Trial O / P  
目标：让 `phase5-local-cycle-step` 默认 CLI 路径复用 Trial P 的 tick envelope，使 CLI 成为后续 scheduler 的真实烟测入口：成功输出 status envelope，失败输出结构化 tick error，不再由 CLI 手写异常 JSON。

## 1. 本轮目标

收敛 CLI 默认执行路径：

- `--output status` 继续作为默认值。
- 默认路径调用 `run_phase5_local_cycle_tick(...)`。
- 默认路径输出 tick envelope JSON，而不是裸 status projection，也不是完整 service result。
- 默认路径退出码使用 tick result 的 `exit_code`。
- `--output full` 保留 Trial O 的完整 service result 调试能力，并继续由异常返回非零结构化 JSON。

## 2. 非目标

- 不改 `run_phase5_local_cycle_tick(...)`。
- 不改 service / resolver / runner / planner / status projection。
- 不新增 artifact / event / registry id。
- 不接 LaunchAgent、cron、heartbeat 或真实 scheduler。
- 不读 DB、不读网络、不调用 LLM。
- 不发布 runtime。
- 不改 API / SPA。

## 3. Owned Files

默认只允许修改：

- `src/ashare_evidence/cli_autonomous_flow.py`
- `tests/test_cli_autonomous_flow.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_Q_EVALUATION_CN.md`

如确需修改 tick、service、resolver、runner、planner、status projection、artifact model、registry、API 或前端，必须说明原因；默认不改。

## 4. Registry IDs

本轮不新增事件或 artifact id。只允许引用：

- `phase5_cycle_ledger`
- `phase5_gate_readout`
- `phase5_recovery_ticket`
- `frontend_projection_manifest`
- `runtime.publish.verified.v1`
- `iface.scheduler.phase5-cycle-ledger.v1`
- `iface.projection.api-spa.v1`

## 5. CLI 合同要求

默认路径：

- `phase5-local-cycle-step --cycle-id ...` 等同 `--output status`。
- 调用 `run_phase5_local_cycle_tick(...)`，参数完整透传。
- 输出 `Phase5LocalCycleTickResult.model_dump(mode="json")`。
- 返回 `tick_result.exit_code`。
- 成功 JSON 顶层应包含 `tick_status`、`exit_code`、`status`、`error`、`recommended_next_action`、`summary_status`。
- 失败 JSON 应由 tick envelope 负责，不应由 CLI 的 `except` 手写错误路径负责。

调试路径：

- `--output full` 调用 `run_phase5_local_cycle_service(...)` 并输出完整 service result。
- `--output full` 可以继续使用 CLI 手写异常 JSON，因为它是调试模式。
- `--output full` 不应调用 tick。

边界：

- 默认路径不应直接调用 service 或 status projection。
- 默认成功输出不应包含完整 `input_bundle`、`runner_result`、release manifest ref、digest 或截图。
- CLI handler 不直接读写 artifact store、不读 DB、不读网络、不读取当前时间。

## 6. Tests

至少覆盖：

- parser 默认 `output == "status"`。
- 默认路径调用 tick，不调用 service 或 status projection。
- 默认路径参数完整透传给 tick。
- 默认路径返回 tick exit_code。
- 默认成功输出为 tick envelope，小 payload 不泄露 `input_bundle` / `runner_result` / release manifest ref / digest。
- 默认失败输出来自 tick envelope，不走 CLI 手写异常 JSON。
- `--output full` 保留完整 service result 输出，且不调用 tick。
- `--output full` service 异常仍返回 CLI 手写错误 JSON。
- `cli.main(["phase5-local-cycle-step", ...])` 仍不触发 DB 初始化。

## 7. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow.py tests/test_autonomous_flow_tick.py -q`
- `ruff check src/ashare_evidence/cli_autonomous_flow.py tests/test_cli_autonomous_flow.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_Q_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_Q_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
