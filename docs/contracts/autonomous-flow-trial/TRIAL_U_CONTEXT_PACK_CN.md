# Trial U Context Pack：Phase 5 CLI Follow-up Plan Output

状态：active input  
上游：Trial Q / S / T  
目标：给 `phase5-local-cycle-step` 增加显式 `--output plan`，输出 Trial T 的 scheduler follow-up plan。默认 `--output status` 不变，`--output full` 调试模式不变。

## 1. 本轮目标

扩展 CLI 输出形态：

- `--output status` 仍为默认值，输出 tick envelope，并返回 tick exit code。
- 新增 `--output plan`，内部调用 tick，再调用 `plan_phase5_scheduler_followup(...)`，输出 follow-up plan JSON。
- `--output plan` 命令返回 0，表示计划已生成；计划内容通过 `plan_status` 和 `action` 表示后续执行语义。
- `--output full` 继续输出完整 service result，用于本地调试。
- `--output plan` 不应调用 service 或 status projection；只通过 tick 入口。

## 2. 非目标

- 不改变 tick / scheduler plan 行为。
- 不执行 scheduler plan。
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
- `tests/test_cli_autonomous_flow_smoke.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_U_EVALUATION_CN.md`

如确需修改 tick、scheduler plan、service、resolver、runner、planner、status projection、artifact model、registry、API 或前端，必须说明原因；默认不改。

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

- `--output` choices 扩展为 `status|plan|full`。
- help 文案明确：默认 tick envelope，plan 为 follow-up plan，full 为完整 service result 调试。

Status 路径：

- 行为不变，返回 tick exit code。

Plan 路径：

- 调用 `run_phase5_local_cycle_tick(...)`，参数完整透传。
- 调用 `plan_phase5_scheduler_followup(tick_result)`。
- 输出 plan JSON。
- 返回 0，只表示计划生成成功。
- plan 输出不应包含完整 tick `status` / `error`、input bundle、runner result、release manifest ref、digest 或 traceback。

Full 路径：

- 行为不变，仍直接调用 service。
- 不调用 tick 或 follow-up planner。

## 6. Tests

至少覆盖：

- parser 支持 `--output plan`，默认仍为 `status`。
- `--output plan` 调用 tick 和 follow-up planner，不调用 service。
- `--output plan` 参数完整透传给 tick。
- `--output plan` 对 error tick 仍返回 0 并输出 plan。
- `--output status` 行为不变，返回 tick exit code。
- `--output full` 行为不变，不调用 tick/plan。
- smoke test：真实 artifact root happy path 的 `--output plan` 输出 ready continue_tracking plan。
- smoke test：missing cycle 的 `--output plan` 输出 ready open_recovery_ticket plan，exit code 为 0。
- plan 输出不泄露 nested tick payload 或敏感 refs。

## 7. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_smoke.py tests/test_autonomous_flow_scheduler_plan.py -q`
- `ruff check src/ashare_evidence/cli_autonomous_flow.py tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_smoke.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_U_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_U_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
