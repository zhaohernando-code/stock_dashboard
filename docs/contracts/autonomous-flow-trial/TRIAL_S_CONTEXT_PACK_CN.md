# Trial S Context Pack：Phase 5 CLI Tick Smoke Tests

状态：active input  
上游：Trial Q / R  
目标：补齐 `phase5-local-cycle-step` 默认 tick envelope 的真实 artifact root 集成烟测，验证 CLI 默认路径在文件系统输入下输出稳定 envelope，而不只依赖 monkeypatch 单元测试。

## 1. 本轮目标

新增测试，不改生产行为：

- 使用临时 artifact root 写入真实 cycle / gate / projection fixture。
- 通过 `cli.main(["phase5-local-cycle-step", ...])` 调用默认路径。
- 成功场景输出 tick envelope：`tick_status=ok`、`exit_code=0`、`status.summary_status` 等。
- 缺失 cycle 场景输出 tick envelope：`tick_status=error`、`exit_code=1`、`error.failure_class=artifact-missing`、`summary_status=degraded`。
- 验证默认输出不泄露 `input_bundle`、`runner_result`、release manifest ref、digest。
- 保持 `--output full` 的已有单元测试，不在本轮扩大调试路径。

## 2. 非目标

- 不改 CLI / tick / resolver / service / runner / planner / status projection 生产代码，除非发现真实 bug。
- 不新增 artifact / event / registry id。
- 不接 LaunchAgent、cron、heartbeat 或真实 scheduler。
- 不读 DB、不读网络、不调用 LLM。
- 不发布 runtime。
- 不改 API / SPA。

## 3. Owned Files

默认只允许修改：

- `tests/test_cli_autonomous_flow_smoke.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_S_EVALUATION_CN.md`

如确需修改生产代码或既有测试文件，必须说明原因；默认不改。

## 4. Registry IDs

本轮不新增事件或 artifact id。只允许引用：

- `phase5_cycle_ledger`
- `phase5_gate_readout`
- `phase5_recovery_ticket`
- `frontend_projection_manifest`
- `runtime.publish.verified.v1`
- `iface.scheduler.phase5-cycle-ledger.v1`
- `iface.projection.api-spa.v1`

## 5. Tests 要求

至少覆盖：

- 真实 artifact root happy path：
  - 写入 cycle ledger、gate readout、frontend projection manifest。
  - 通过 `cli.main(...)` 调用默认 CLI。
  - 断言 exit code 为 0。
  - 断言 JSON 顶层是 tick envelope。
  - 断言 `status.summary_status` 为 completed 或 degraded，取决于 fixture。
  - 断言 payload 不含 `input_bundle`、`runner_result`、release manifest ref、digest。
- 缺失 cycle path：
  - 不写 cycle ledger。
  - 通过 `cli.main(...)` 调用默认 CLI。
  - 断言 exit code 为 1。
  - 断言 JSON 顶层是 tick envelope error。
  - 断言 `error.failure_class == "artifact-missing"`。
  - 断言 `summary_status == "degraded"`。
- `cli.main(...)` 仍不触发 DB 初始化。

## 6. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_smoke.py tests/test_autonomous_flow_tick.py -q`
- `ruff check tests/test_cli_autonomous_flow_smoke.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_S_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_S_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
