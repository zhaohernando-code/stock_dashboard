# Trial V Context Pack：Split CLI Autonomous Flow Tests

状态：active input  
上游：Trial U  
目标：把接近 500 行的 `tests/test_cli_autonomous_flow.py` 拆分，降低后续 pre-commit 文件规模风险。只做测试结构重构，不改变生产行为和测试语义。

## 1. 本轮目标

测试维护性重构：

- 将共享 fake result / helper 提取到测试 helper 模块。
- 将 `--output plan` 和 `--output full` 相关单元测试拆到独立测试文件。
- 保留 parser/default status/main DB 初始化等基础测试在原文件，或按清晰职责拆分。
- 每个测试文件保持明显低于 500 行。
- 覆盖数量和关键断言不减少。

## 2. 非目标

- 不改生产代码。
- 不改 CLI 行为。
- 不新增输出模式。
- 不接 scheduler / LaunchAgent / cron / heartbeat。
- 不改 API / SPA。
- 不新增 artifact / event / registry id。

## 3. Owned Files

默认只允许修改：

- `tests/test_cli_autonomous_flow.py`
- `tests/test_cli_autonomous_flow_outputs.py`
- `tests/helpers_cli_autonomous_flow.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_V_EVALUATION_CN.md`

如确需修改生产代码或 smoke tests，必须说明原因；默认不改。

## 4. Registry IDs

本轮不新增事件或 artifact id。只允许引用：

- `phase5_cycle_ledger`
- `phase5_gate_readout`
- `phase5_recovery_ticket`
- `frontend_projection_manifest`
- `runtime.publish.verified.v1`
- `iface.scheduler.phase5-cycle-ledger.v1`
- `iface.projection.api-spa.v1`

## 5. 重构要求

- 新 helper 文件只放测试 fake 类和 helper 函数，不放生产逻辑。
- 测试命名保持语义清晰。
- `tests/test_cli_autonomous_flow.py` 行数应低于 300。
- 新增测试文件也应低于 300。
- 不能删除以下覆盖：
  - parser 默认 status。
  - parser 支持 plan。
  - default status 调 tick、不调 service。
  - default status 参数透传。
  - default error tick 返回 tick exit code。
  - plan 调 tick + follow-up planner，不调 service。
  - plan 参数透传。
  - plan error tick 返回 0 和 plan。
  - full 输出完整 service result，不调 tick/plan。
  - full service error 返回 CLI error JSON。
  - `cli.main(...)` 不触发 DB 初始化。

## 6. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_outputs.py tests/test_cli_autonomous_flow_smoke.py -q`
- `ruff check tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_outputs.py tests/helpers_cli_autonomous_flow.py`
- `wc -l tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_outputs.py tests/helpers_cli_autonomous_flow.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_V_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_V_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
