# Trial F Context Pack：Phase 5 自运行 Cycle 原语

状态：active input  
上游：Trial C / D / E  
目标：在已有 artifact store 基础上，实现最小 cycle 原语，让后续 scheduler / projection / publish verifier 能通过统一函数创建 cycle、追加 refs、记录 gate/recovery/publish。

## 1. 本轮目标

实现一个纯本地、可测试、无 runtime 副作用的模块：

- 创建 `phase5_cycle_ledger`。
- 追加 `phase5.artifact.produced.v1` 对应的 artifact ref。
- 写入 `phase5_gate_readout` 并把 ref 追加到 cycle。
- 写入 `phase5_recovery_ticket` 并把 ref 追加到 cycle。
- 读取 release manifest 文件，计算 digest，生成 `PublishVerificationRef`，挂到 cycle。
- 所有写入继续走 `research_artifact_store`，复用 repo artifact 写保护。

## 2. 非目标

- 不接 LaunchAgent 或真实 scheduler。
- 不接 API / frontend / projection builder。
- 不调用 release verifier。
- 不发布 runtime。
- 不新增数据库表。
- 不改变当前 Phase 5 研究结果。

## 3. Owned Files

- `src/ashare_evidence/autonomous_flow.py`
- `tests/test_autonomous_flow.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_F_EVALUATION_CN.md`

如确需修改 artifact model / store，必须说明原因；默认不改。

## 4. Registry IDs

只允许引用：

- `phase5_cycle_ledger`
- `phase5_recovery_ticket`
- `phase5_gate_readout`
- `phase5.cycle.started.v1`
- `phase5.artifact.produced.v1`
- `phase5.gate.evaluated.v1`
- `phase5.recovery.recorded.v1`
- `runtime.publish.verified.v1`

## 5. 函数要求

建议函数，不强制命名完全一致：

- `start_phase5_cycle(...) -> Phase5CycleLedgerArtifact`
- `record_phase5_artifact(...) -> Phase5CycleLedgerArtifact`
- `record_phase5_gate_readout(...) -> tuple[Phase5CycleLedgerArtifact, Phase5GateReadoutArtifact]`
- `record_phase5_recovery_ticket(...) -> tuple[Phase5CycleLedgerArtifact, Phase5RecoveryTicketArtifact]`
- `attach_publish_verification(...) -> Phase5CycleLedgerArtifact`

约束：

- 函数必须是确定性本地文件操作，不读 DB、不读网络、不调用 LLM。
- 时间戳由调用方传入，不在函数内部读取当前时间。
- `attach_publish_verification` 可以读取 manifest 文件内容计算 digest，这是本轮允许的唯一文件读取输入。
- 追加 refs 时必须去重，不能反复追加同一 ref。
- 如果目标 cycle 不存在，应明确报错，不自动创建隐藏 cycle。

## 6. Tests

至少覆盖：

- start cycle 写入 ledger，包含 `phase5.cycle.started.v1`。
- record artifact 去重追加 ref，并记录 `phase5.artifact.produced.v1`。
- record gate readout 写入 readout artifact，并追加 gate ref。
- record recovery ticket 写入 ticket artifact，并追加 recovery ref。
- attach publish verification 计算 manifest digest，ledger 只保存 ref/digest/event ref，不保存 manifest 明细。
- missing cycle 时追加动作失败。

## 7. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow.py`
- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow.py tests/test_autonomous_flow_artifacts.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_F_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_F_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
