# Trial X Context Pack：Phase 5 CLI Dry-run Output

状态：active input  
上游：Trial U / W  
目标：给 `phase5-local-cycle-step` 增加显式 `--output dry-run`，执行完整无副作用链路：tick -> follow-up plan -> dry-run executor。默认 `status`、`plan`、`full` 语义保持不变。

## 1. 本轮目标

扩展 CLI 输出形态：

- `--output status` 仍为默认值，输出 tick envelope，并返回 tick exit code。
- `--output plan` 行为不变，输出 follow-up plan，并返回 0。
- 新增 `--output dry-run`，内部调用 tick、follow-up plan、dry-run executor，输出 dry-run result JSON。
- `--output dry-run` 返回 0，表示 dry-run 意图生成成功。
- `--output full` 行为不变，继续输出完整 service result。

## 2. 非目标

- 不改变 tick / scheduler plan / dry-run executor 行为。
- 不执行 scheduler action。
- 不写 recovery ticket。
- 不修改 cycle closeout。
- 不新增 artifact / event / registry id。
- 不接 LaunchAgent、cron、heartbeat 或真实 scheduler。
- 不读 DB、不读网络、不调用 LLM。
- 不发布 runtime。
- 不改 API / SPA。

## 3. Owned Files

默认只允许修改：

- `src/ashare_evidence/cli_autonomous_flow.py`
- `tests/test_cli_autonomous_flow.py`
- `tests/test_cli_autonomous_flow_outputs.py`
- `tests/test_cli_autonomous_flow_smoke.py`
- `tests/helpers_cli_autonomous_flow.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_X_EVALUATION_CN.md`

如确需修改 tick、scheduler plan、dry-run executor、service、resolver、runner、planner、status projection、artifact model、registry、API 或前端，必须说明原因；默认不改。

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

Parser：

- `--output` choices 扩展为 `status|plan|dry-run|full`。
- help 文案明确 dry-run 为 no-side-effect execution intent。

Dry-run 路径：

- 调用 `run_phase5_local_cycle_tick(...)`，参数完整透传。
- 调用 `plan_phase5_scheduler_followup(tick_result)`。
- 调用 `dry_run_phase5_scheduler_plan(plan)`。
- 输出 dry-run result JSON。
- 返回 0。
- 不直接调用 service 或 status projection。
- 输出不应包含完整 tick status/error、plan payload、input bundle、runner result、release manifest ref、digest 或 traceback。

其他路径：

- `status`、`plan`、`full` 行为不变。

## 6. Tests

至少覆盖：

- parser 支持 `--output dry-run`，默认仍为 `status`。
- `--output dry-run` 调用 tick、plan、dry-run executor，不调用 service。
- `--output dry-run` 参数完整透传给 tick。
- `--output dry-run` 对 error tick 仍返回 0 并输出 dry-run result。
- `--output status`、`--output plan`、`--output full` 既有核心断言继续通过。
- smoke test：真实 artifact root happy path 的 `--output dry-run` 输出 planned continue_tracking dry-run。
- smoke test：missing cycle 的 `--output dry-run` 输出 planned open_recovery_ticket dry-run，exit code 为 0。
- dry-run 输出不泄露 nested tick/plan payload 或敏感 refs。
- 拆分后被修改的测试文件均低于 300 行。

## 7. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_outputs.py tests/test_cli_autonomous_flow_smoke.py tests/test_autonomous_flow_scheduler_executor.py -q`
- `ruff check src/ashare_evidence/cli_autonomous_flow.py tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_outputs.py tests/test_cli_autonomous_flow_smoke.py tests/helpers_cli_autonomous_flow.py`
- `wc -l tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_outputs.py tests/test_cli_autonomous_flow_smoke.py tests/helpers_cli_autonomous_flow.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_X_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_X_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
