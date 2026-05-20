# Trial Y Context Pack：Phase 5 Scheduler Diagnostic Artifact

状态：active input  
上游：Trial R / T / W / X  
目标：引入可持久化的 scheduler diagnostic artifact，用于记录 scheduler 无法安全执行后续动作时的诊断事实。该 artifact 必须允许 `cycle_id` 缺失或 cycle ledger 不存在，避免真实 scheduler 在 `open_recovery_ticket` 前置条件不满足时只能等待人工判断。

## 1. 背景

Trial X 已让 CLI 能输出 `dry-run` intent，但暴露出一个关键边界：

- `open_recovery_ticket` 在 scheduler plan 层是合理动作。
- 现有 `phase5_recovery_ticket` 写入要求目标 cycle ledger 已存在。
- 当失败原因正是 cycle ledger 缺失时，直接写 recovery ticket 会失败。

因此真实执行层需要一个独立、低风险、可审计的诊断落点，先把失败事实硬存储下来，再由后续轮次决定是否创建 follow-up cycle、重试或阻断。

## 2. 本轮目标

新增 `phase5_scheduler_diagnostic` artifact family：

- 可在没有 cycle ledger 的情况下写入。
- 记录 scheduler action、failure class、recommended recovery action、blocking reasons、evidence refs。
- 输出和存储都必须避免泄露完整 tick payload、runner result、input bundle、release manifest ref、digest、traceback。
- 提供 artifact store 的 write/read/read-if-exists 函数。
- 提供一个最小 record 函数，不要求 cycle 存在；如果 cycle 存在，可保守追加 diagnostic event ref 到 cycle ledger。
- 更新 registry 与 schema，让后续文档和代码引用可被机器门禁检查。

## 3. 非目标

- 不把 diagnostic 接入 CLI。
- 不执行 scheduler action。
- 不写 recovery ticket。
- 不创建 follow-up cycle。
- 不修改 tick / plan / dry-run executor 的既有合同。
- 不接 LaunchAgent、cron、heartbeat。
- 不改 API / SPA。
- 不发布 runtime。

## 4. Registered IDs

本轮新增并注册：

- `phase5.scheduler.diagnostic.recorded.v1`
- `phase5_scheduler_diagnostic`

可继续引用：

- `phase5_cycle_ledger`
- `phase5_recovery_ticket`
- `phase5_gate_readout`
- `frontend_projection_manifest`
- `runtime.publish.verified.v1`
- `iface.scheduler.phase5-cycle-ledger.v1`
- `iface.recovery.scheduler-reviewer.v1`

## 5. Artifact Contract

`phase5_scheduler_diagnostic` 最小字段：

- `artifact_family`: `phase5_scheduler_diagnostic`
- `schema_version`: `v1`
- `diagnostic_id`: 非空字符串
- `cycle_id`: 字符串或 null
- `source`: `phase5_scheduler`
- `observed_at`: 字符串，由调用方传入，不在函数内部读当前时间
- `severity`: `info | warning | error | blocked`
- `scheduler_action`: `continue_tracking | rebuild_projection | retry_failed_step | open_recovery_ticket | block_cycle | redesign | none`
- `failure_class`: `artifact-missing | contract-violation | unexpected-error | blocked-plan | execution-precondition-failed | none`
- `recommended_recovery_action`: `open_recovery_ticket | retry_with_backoff | block_cycle | none`
- `blocking_reasons`: 去重后的字符串数组
- `evidence_refs`: 去重后的字符串数组
- `notes`: 字符串
- `event_refs`: 至少包含 `phase5.scheduler.diagnostic.recorded.v1`

## 6. Record 函数合同

建议新增：

```python
record_phase5_scheduler_diagnostic(
    *,
    diagnostic_id: str,
    observed_at: str,
    scheduler_action: str,
    severity: str,
    failure_class: str,
    recommended_recovery_action: str,
    cycle_id: str | None = None,
    blocking_reasons: list[str] | None = None,
    evidence_refs: list[str] | None = None,
    notes: str = "",
    root: Path | None = None,
) -> tuple[Phase5CycleLedgerArtifact | None, Phase5SchedulerDiagnosticArtifact]
```

要求：

- 无论 cycle 是否存在，都写 diagnostic artifact。
- cycle 存在时，可向 `event_refs` 追加 `phase5.scheduler.diagnostic.recorded.v1`。
- cycle 缺失时，返回 `(None, diagnostic)`，不抛 `Phase5CycleNotFoundError`。
- 不能修改 cycle status、next_action、finished_at。
- 不能写 recovery ticket。
- 不能读取 DB、网络或 LLM。

## 7. Tests

至少覆盖：

- Pydantic model 接受完整 payload，去重 `blocking_reasons`、`evidence_refs`、`event_refs`。
- artifact store write/read/read-if-exists 使用 `autonomous_flow/phase5_scheduler_diagnostic/<diagnostic_id>.json`。
- record 函数在 cycle 存在时写 diagnostic 并追加 event ref，但不改变 cycle status / next_action。
- record 函数在 cycle 缺失时仍写 diagnostic，并返回 `cycle is None`。
- 输出不泄露 `input_bundle`、`runner_result`、`release-manifest:`、`sha256:`、`Traceback`。
- registry 结构和本轮文档检查通过。

## 8. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_artifacts.py tests/test_autonomous_flow.py -q`
- `ruff check src/ashare_evidence/autonomous_flow_artifacts.py src/ashare_evidence/research_artifact_store.py src/ashare_evidence/autonomous_flow.py tests/test_autonomous_flow_artifacts.py tests/test_autonomous_flow.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_Y_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_Y_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
