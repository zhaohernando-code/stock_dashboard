# Trial AJ Context Pack：Scheduler Safe Execution Entry

状态：active input  
上游：Trial AD / AE / AF / X / Y / AH / AI  
目标：为 `phase5-local-cycle-step` 增加安全 execution ledger 入口，把 tick -> follow-up plan -> execution ledger record 串起来，但仍不执行真实 scheduler action。

## 1. 背景

当前链路已有：

- `--output dry-run`：生成无副作用 scheduler intent，但不落硬状态。
- `--output diagnostic`：写 scheduler diagnostic artifact。
- execution ledger / reservation：已具备 idempotency、crash replay、legacy migration 保护，但尚未接入 CLI 调度入口。

本轮目标是把 execution ledger 接成显式安全入口，作为真实 action 前的最后一层持久化边界。

## 2. 本轮目标

新增 CLI output，建议命名为 `execution`：

- 调用 tick。
- 调用 follow-up planner。
- 调用 scheduler executor 新函数记录 execution ledger。
- 输出结构化 execution record result。
- 返回 0 表示 execution intent 已被安全记录。
- 不执行 retry、projection rebuild、redesign、block closeout、recovery ticket 或真实 scheduler action。

## 3. CLI 参数

`--output execution` 必须要求：

- `--execution-id`
- `--idempotency-key`
- `--created-at`

可选：

- `--diagnostic-id`：作为 diagnostic ref 写入 execution ledger，不要求 diagnostic artifact 已存在。

缺少必需参数时，必须在 tick 前返回 error JSON 和 exit code 2。

## 4. Result 合同

新增 executor result 至少包含：

- cycle id
- execution id
- idempotency key
- execution mode
- execution status
- action
- would execute
- ledger recorded
- cycle event recorded
- reason
- blocking reasons
- diagnostic refs

建议语义：

- plan blocked 或 action `block_cycle` -> execution status `blocked`
- action `none` -> execution status `skipped`
- 其他 action -> execution status `planned`
- 本轮不执行真实 action，因此 `would_execute` 为 false

输出不得包含 tick nested status/error、plan payload、input bundle、runner result、release manifest ref、digest 或 traceback。

## 5. 非目标

- 不执行真实 scheduler action。
- 不写 recovery ticket。
- 不修改 cycle status、next action、finished_at。
- 不改 registry/schema。
- 不改 API / SPA。
- 不接 LaunchAgent、cron、heartbeat。

## 6. Owned Files

默认允许修改：

- `src/ashare_evidence/autonomous_flow_scheduler_executor.py`
- `src/ashare_evidence/cli_autonomous_flow.py`
- `tests/test_autonomous_flow_scheduler_executor.py`
- `tests/test_autonomous_flow_scheduler_execution_executor.py`
- `tests/test_cli_autonomous_flow_execution.py`
- `tests/test_cli_autonomous_flow_smoke_execution.py`
- `tests/helpers_cli_autonomous_flow.py`
- `tests/helpers_cli_autonomous_flow_execution.py`
- `tests/helpers_cli_autonomous_flow_smoke.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_AJ_EVALUATION_CN.md`

文件规模规则：

- 不向 `tests/test_cli_autonomous_flow_outputs.py` 追加新 execution 场景，该文件已 284 行。
- 新增 CLI execution 测试文件应低于 220 行。
- executor 模块如超过 220 行，必须说明拆分计划。

## 7. Tests

至少覆盖：

- executor 函数记录 execution ledger，并只追加 cycle event。
- blocked / skipped / planned 三种 status 映射。
- idempotency conflict 通过 typed error 传播，且无 requested ledger 副作用。
- CLI execution 缺少参数时在 tick 前失败。
- CLI execution 调用 tick、plan、execution recorder，不调用 service、dry-run、diagnostic recorder。
- CLI execution error tick 仍可记录 execution ledger。
- smoke：真实 artifact root happy path 写 execution ledger。
- smoke：missing cycle 写 execution ledger 但不记录 cycle event。
- 输出不泄露 nested payload 或敏感 refs。
- `process-hardening-check` 验证本轮评估文档、文件预算、legacy evidence。

## 8. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_scheduler_executor.py tests/test_autonomous_flow_scheduler_execution_executor.py tests/test_cli_autonomous_flow_execution.py tests/test_cli_autonomous_flow_smoke_execution.py -q`
- `ruff check src/ashare_evidence/autonomous_flow_scheduler_executor.py src/ashare_evidence/autonomous_flow_scheduler_execution_executor.py src/ashare_evidence/cli_autonomous_flow.py tests/test_autonomous_flow_scheduler_executor.py tests/test_autonomous_flow_scheduler_execution_executor.py tests/test_cli_autonomous_flow_execution.py tests/test_cli_autonomous_flow_smoke_execution.py tests/helpers_cli_autonomous_flow.py tests/helpers_cli_autonomous_flow_execution.py tests/helpers_cli_autonomous_flow_smoke.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_AJ_EVALUATION_CN.md --line-budget src/ashare_evidence/autonomous_flow_scheduler_executor.py:240:220 --line-budget src/ashare_evidence/autonomous_flow_scheduler_execution_executor.py:160:130 --line-budget src/ashare_evidence/cli_autonomous_flow.py:190:170 --line-budget tests/helpers_cli_autonomous_flow.py:280:260 --line-budget tests/helpers_cli_autonomous_flow_execution.py:100:80 --line-budget tests/test_cli_autonomous_flow_execution.py:220:190 --line-budget tests/test_cli_autonomous_flow_smoke_execution.py:220:190 --required-evidence tests/test_autonomous_flow_scheduler_execution_idempotency.py:legacy_ledger_conflict`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_AJ_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_AJ_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
- `PYTHONPATH=src python3 -m pytest -q`
