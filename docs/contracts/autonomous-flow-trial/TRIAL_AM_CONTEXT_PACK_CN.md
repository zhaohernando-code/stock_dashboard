# Trial AM Context Pack：CLI Execution Conflict Output

状态：active input
上游：Trial AJ、AK、AL
目标：让 `phase5-local-cycle-step --output execution` 在 scheduler execution idempotency conflict 时输出 typed JSON，而不是让异常冒泡导致无人流程卡死。

## 1. 背景

当前 scheduler execution 已具备 ledger、reservation、legacy migration 与 CLI execution 输出。但 CLI output handler 对 execution recorder 的冲突异常没有结构化收口：

- 缺参会在 tick 前返回 typed JSON，exit code 为 2。
- 幂等冲突由 recorder 抛出 typed exception。
- CLI execution output 当前没有捕获该冲突并返回可调度系统消费的错误 envelope。

本轮只补“冲突可观测和可继续”的出口，不执行真实 scheduler action。

## 2. 本轮目标

- 捕获 scheduler execution idempotency conflict。
- 输出稳定 JSON：包含 `status=error`、`command`、`error_type`、`message`、`idempotency_key`、`existing_execution_id`、`requested_execution_id`、`recommended_next_action`。
- exit code 使用非 0，且与缺参错误区分；建议用 3 表示 execution conflict。
- 保证 conflict 分支不泄露 nested tick、plan、service payload。
- 保证 conflict 分支不调用 full service、dry-run executor、diagnostic recorder。
- 保持既有 successful execution 输出不变。

## 3. 非目标

- 不新增真实 scheduler action。
- 不修改 reservation / ledger 原子语义。
- 不修改 full output 行为。
- 不新增 artifact family 或 registry id，除非实现确实需要。
- 不把 handler 文件推回规模风险区。

## 4. Owned Files

默认允许修改：

- `src/ashare_evidence/cli_autonomous_flow_outputs.py`
- `tests/test_cli_autonomous_flow_execution.py`
- `tests/test_cli_autonomous_flow_smoke_execution.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_AM_EVALUATION_CN.md`

如需共享 helper，允许修改：

- `tests/helpers_cli_autonomous_flow_execution.py`
- `tests/helpers_cli_autonomous_flow_smoke.py`

禁止修改：

- scheduler execution ledger / reservation store 语义文件。
- production action 执行路径。
- unrelated frontend、stock research、runtime config 文件。

## 5. 文件规模要求

- `src/ashare_evidence/cli_autonomous_flow_outputs.py` 当前约 168 行，hard limit 220，warning 200。
- `tests/test_cli_autonomous_flow_execution.py` 当前约 175 行，hard limit 230，warning 210。
- `tests/test_cli_autonomous_flow_smoke_execution.py` 当前约 81 行，hard limit 180，warning 150。
- 如果测试文件接近 warning，必须拆分或复用 helper，不允许把规模风险留给下一轮。

## 6. 必测场景

- unit：execution recorder 抛出 idempotency conflict 时，CLI 返回 exit code 3 和 typed JSON。
- unit：typed JSON 包含 existing / requested execution id 与 recommended next action。
- unit：conflict 分支不调用 service、dry-run executor、diagnostic recorder。
- smoke：真实 artifact root 下预置 existing reservation 或 ledger 后，再次执行不同 execution id，CLI 返回 conflict JSON，requested ledger 不写入。
- regression：既有 successful execution、error tick execution、missing args 行为保持。

## 7. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_execution.py tests/test_cli_autonomous_flow_smoke_execution.py tests/test_autonomous_flow_scheduler_execution_idempotency.py -q`
- `ruff check src/ashare_evidence/cli_autonomous_flow_outputs.py tests/test_cli_autonomous_flow_execution.py tests/test_cli_autonomous_flow_smoke_execution.py tests/helpers_cli_autonomous_flow_execution.py tests/helpers_cli_autonomous_flow_smoke.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_AM_EVALUATION_CN.md --line-budget src/ashare_evidence/cli_autonomous_flow_outputs.py:220:200 --line-budget tests/test_cli_autonomous_flow_execution.py:230:210 --line-budget tests/test_cli_autonomous_flow_smoke_execution.py:180:150 --line-budget tests/helpers_cli_autonomous_flow_execution.py:120:100 --line-budget tests/helpers_cli_autonomous_flow_smoke.py:260:240 --required-evidence tests/test_autonomous_flow_scheduler_execution_idempotency.py:legacy_ledger_conflict`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_AM_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_AM_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
- `PYTHONPATH=src python3 -m pytest -q`
