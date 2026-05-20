# Trial AD Context Pack：Scheduler Execution Ledger

状态：active input  
上游：Trial AA / AB / AC  
目标：新增 scheduler execution ledger，用于在真实 scheduler action 执行前记录幂等执行意图、执行状态和恢复边界。本轮只记录 execution ledger，不执行真实动作。

## 1. 背景

当前链路已经具备：

- dry-run output：能看到 scheduler would-do intent。
- diagnostic output：能把 scheduler 诊断事实写入硬存储。

下一步进入真实执行前，必须先有一个幂等 execution ledger。否则 retry、crash recovery、重复调度、并发调度都无法判断某个 action 是否已经被计划、跳过、阻塞或准备执行。

## 2. 本轮目标

新增 Phase 5 scheduler execution ledger：

- 注册新的事件与 artifact family。
- 新增 Pydantic artifact model。
- 新增 artifact store 读写函数，避免继续膨胀既有 autonomous-flow artifact store。
- 新增 record 函数：只写 ledger，不执行真实 action。
- cycle 存在时只追加 execution recorded event。
- cycle 缺失时仍写 execution ledger，但不抛错。
- 记录幂等键、plan action、execution status、would execute 标记、blocking reasons、diagnostic refs。

## 3. 非目标

- 不执行 retry、projection rebuild、redesign、block closeout 或 recovery ticket 写入。
- 不修改 CLI。
- 不修改 tick / plan / dry-run / diagnostic recorder 行为。
- 不接 LaunchAgent、cron、heartbeat。
- 不改 API / SPA。

## 4. Registered IDs

本轮新增并注册：

- `phase5.scheduler.execution.recorded.v1`
- `phase5_scheduler_execution_ledger`

可继续引用：

- `phase5_cycle_ledger`
- `phase5_scheduler_diagnostic`
- `iface.scheduler.phase5-cycle-ledger.v1`

## 5. Artifact Contract

Phase 5 scheduler execution ledger 最小字段：

- artifact family: `phase5_scheduler_execution_ledger`
- schema version: `v1`
- execution id: 非空字符串
- idempotency key: 非空字符串，由调用方传入，不在函数内部读时间或随机数
- cycle id: 字符串或 null
- source: `phase5_scheduler`
- created at: 字符串，由调用方传入
- plan action: `continue_tracking | rebuild_projection | retry_failed_step | open_recovery_ticket | block_cycle | redesign | none`
- execution status: `planned | skipped | blocked`
- would execute: bool
- diagnostic refs: 去重字符串数组
- blocking reasons: 去重字符串数组
- notes: 字符串
- event refs: 至少包含 `phase5.scheduler.execution.recorded.v1`

## 6. Record 函数合同

新增 record 函数，参数由调用方显式传入：

- execution id
- idempotency key
- created at
- plan action
- execution status
- would execute
- optional cycle id
- optional diagnostic refs
- optional blocking reasons
- notes
- root

要求：

- 无论 cycle 是否存在，都写 execution ledger。
- cycle 存在时只追加 `phase5.scheduler.execution.recorded.v1` 到 event refs。
- cycle 缺失时返回 cycle 为 None，不抛错。
- 不修改 cycle status、next action、finished at。
- 不写 recovery ticket，不执行 action。
- 不读取 DB、网络、当前时间或 LLM。
- 输出和存储不泄露 input bundle、runner result、release manifest ref、digest、traceback。

## 7. 文件规模约束

- 不继续向 `src/ashare_evidence/autonomous_flow_artifact_store.py` 追加大段代码；该文件已经接近 300 行。
- 新增 scheduler execution store 模块应低于 180 行。
- 新增测试文件应低于 260 行。

## 8. Tests

至少覆盖：

- artifact model 校验、去重、默认 event refs。
- artifact store write/read/read-if-exists 路径。
- record 函数在 cycle 存在时写 ledger 并只追加 event ref。
- record 函数在 cycle 缺失时仍写 ledger。
- record 函数不改变 cycle status、next action、finished at。
- 敏感内容不进入 ledger payload。
- registry check 通过。

## 9. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_scheduler_execution_ledger.py tests/test_autonomous_flow.py -q`
- `ruff check src/ashare_evidence/autonomous_flow_artifacts.py src/ashare_evidence/scheduler_execution_artifact_store.py src/ashare_evidence/autonomous_flow.py tests/test_autonomous_flow_scheduler_execution_ledger.py`
- `wc -l src/ashare_evidence/scheduler_execution_artifact_store.py tests/test_autonomous_flow_scheduler_execution_ledger.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_AD_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_AD_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
