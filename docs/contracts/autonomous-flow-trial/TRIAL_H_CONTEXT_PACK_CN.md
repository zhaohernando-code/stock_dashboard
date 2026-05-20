# Trial H Context Pack：Phase 5 Cycle Closeout 原语

状态：active input  
上游：Trial C / D / E / F / G  
目标：在已有 cycle、gate、recovery、projection 原语基础上，实现最小 cycle closeout 原语，让后续 scheduler 可以用统一函数终结一轮 cycle 并写入下一步动作。

## 1. 本轮目标

实现一个纯本地、可测试、无 runtime 副作用的 closeout 层：

- 对已存在的 `phase5_cycle_ledger` 写入 `status`、`finished_at`、`next_action`。
- 终结函数必须 fail-closed：目标 cycle 不存在时明确报错。
- 终结函数必须保留已有 artifact refs、gate refs、recovery refs、publish verification ref 和 event refs。
- 终结函数不产生新事件 id，不新增 artifact family。
- 终结函数不自动推断当前时间；`finished_at` 由调用方传入。

## 2. 非目标

- 不接 LaunchAgent、cron、heartbeat 或真实 scheduler。
- 不新增 scheduler plan artifact。
- 不读取 gate/recovery/projection artifact 来自动决策。
- 不改 API / SPA。
- 不调用 release verifier。
- 不发布 runtime。
- 不新增数据库表。

## 3. Owned Files

- `src/ashare_evidence/autonomous_flow.py`
- `tests/test_autonomous_flow.py`
- `tests/test_autonomous_flow_closeout.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_H_EVALUATION_CN.md`

如确需修改 artifact model、store、registry、API 或前端，必须说明原因；默认不改。

## 4. Registry IDs

本轮不新增事件或 artifact id。只允许继续引用：

- `phase5_cycle_ledger`
- `phase5.cycle.started.v1`
- `phase5.artifact.produced.v1`
- `phase5.gate.evaluated.v1`
- `phase5.projection.refreshed.v1`
- `phase5.recovery.recorded.v1`
- `runtime.publish.verified.v1`

## 5. 函数要求

建议函数，不强制命名完全一致：

- `finish_phase5_cycle(...) -> Phase5CycleLedgerArtifact`

建议入参：

- `cycle_id`
- `status`
- `finished_at`
- `next_action`
- `root`

约束：

- `status` 只能是 `completed`、`degraded`、`blocked`。
- `finished_at` 必须由调用方传入，不在函数内部读取当前时间。
- `blocked` 状态必须配套 `next_action="blocked"`。
- `completed` 状态不能配套 `next_action="blocked"` 或 `next_action="retry_failed_step"`。
- `degraded` 状态不能配套 `next_action="none"`。
- 函数不得清空已有 refs 或 publish verification。
- 函数不读 DB、不读网络、不调用 LLM。

## 6. Tests

至少覆盖：

- running cycle 可以被 finish 为 completed，并保留已有 refs。
- degraded closeout 可保留 `rebuild_projection` / `continue_tracking` 等下一步动作。
- blocked closeout 强制 `next_action="blocked"`。
- completed closeout 拒绝 blocked/retry next action。
- degraded closeout 拒绝 `next_action="none"`。
- missing cycle 时 closeout 失败。
- 函数不新增 event ref。

## 7. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow.py tests/test_autonomous_flow_closeout.py -q`
- `ruff check src/ashare_evidence/autonomous_flow.py tests/test_autonomous_flow.py tests/test_autonomous_flow_closeout.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_H_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_H_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
