# Trial O Context Pack：Phase 5 CLI Status Output

状态：active input  
上游：Trial M / N  
目标：让 `phase5-local-cycle-step` CLI 默认输出 Trial N 的稳定小状态 payload，避免脚本、未来 scheduler 或中台入口依赖 `Phase5LocalCycleServiceResult` 的内部嵌套结构。

## 1. 本轮目标

收敛 CLI 输出边界：

- `phase5-local-cycle-step` 成功路径默认输出 `Phase5LocalCycleStatusProjection` 的 JSON。
- 输出字段应是状态 projection 小 payload，而不是完整 service result。
- 保留可诊断能力：允许显式请求完整 service result，用于本地调试。
- 错误路径继续输出结构化 JSON，且不改变退出码语义。
- 不改变 service / resolver / runner / planner 的业务行为。

## 2. 非目标

- 不改 artifact store。
- 不新增事件 id 或 artifact id。
- 不接 LaunchAgent、cron、heartbeat 或真实 scheduler。
- 不读 DB、不读网络、不调用 LLM。
- 不调用 release verifier。
- 不发布 runtime。
- 不改 API / SPA。
- 不新增数据库表。

## 3. Owned Files

默认只允许修改：

- `src/ashare_evidence/cli_autonomous_flow.py`
- `tests/test_cli_autonomous_flow.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_O_EVALUATION_CN.md`

如确需修改 `cli.py`、service、resolver、runner、planner、status projection、artifact model、registry、API 或前端，必须说明原因；默认不改。

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

建议实现：

- `phase5-local-cycle-step` 默认 `--output status`。
- 增加 `--output status|full`，其中：
  - `status`：输出 `project_phase5_local_cycle_status(result).model_dump(mode="json")`。
  - `full`：保留 Trial M 的完整 service result JSON，用于本地调试。
- 不改变既有输入参数含义。
- `--apply-closeout`、`--finished-at`、`--require-publish-verification` 等参数仍只传给 service，由 service fail-closed。
- handler 不直接读写 artifact store，不读 DB，不读网络，不读取当前时间。
- 错误输出仍包含 `status`、`command`、`error_type`、`message`。

边界：

- 默认成功输出不应包含 `input_bundle`、`runner_result`、artifact payload、release manifest ref、digest 或截图。
- `--output full` 可以包含完整 service result，但必须是显式调试模式。
- 不允许为了做 projection 修改 service 返回对象。

## 6. Tests

至少覆盖：

- parser 默认 `output == "status"`。
- 成功路径默认输出 status projection 小 payload。
- 默认输出不包含 `input_bundle` / `runner_result` / release manifest details。
- `--output full` 保留完整 service result 输出。
- service 调用参数不因 output mode 改变。
- 错误路径仍返回非零结构化 JSON。
- `cli.main(["phase5-local-cycle-step", ...])` 仍不触发 `init_database`。

## 7. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow.py tests/test_autonomous_flow_status.py -q`
- `ruff check src/ashare_evidence/cli_autonomous_flow.py tests/test_cli_autonomous_flow.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_O_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_O_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
