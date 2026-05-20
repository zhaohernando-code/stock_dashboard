# Trial AK Context Pack：Autonomous Flow CLI Handler Split

状态：active input  
上游：Trial AJ  
目标：在接入真实 scheduler action 前，拆分 `cli_autonomous_flow.py` 的 output handler，降低 CLI 主文件规模和后续扩展风险。

## 1. 背景

Trial AJ 新增 `--output execution` 后，`src/ashare_evidence/cli_autonomous_flow.py` 达到 181 行，超过 warning 线 170，虽然低于 hard limit 190，但继续扩展真实 action 会马上进入不可维护区间。

本轮只做结构拆分，不改变 CLI 行为。

当前规模：

- `src/ashare_evidence/cli_autonomous_flow.py`：181 行
- `tests/test_cli_autonomous_flow_outputs.py`：284 行，不得继续追加
- `tests/test_cli_autonomous_flow_execution.py`：175 行
- `tests/test_cli_autonomous_flow_diagnostics.py`：243 行

## 2. 本轮目标

- 新增独立 CLI output handler 模块，建议 `src/ashare_evidence/cli_autonomous_flow_outputs.py`。
- 将 status / plan / dry-run / diagnostic / execution / full 的执行分支移出 `cli_autonomous_flow.py`。
- `cli_autonomous_flow.py` 保留 parser 定义和 dispatch glue。
- 行为完全兼容现有测试。
- 不新增 CLI output，不新增 artifact，不改 registry。

## 3. 非目标

- 不执行真实 scheduler action。
- 不改 scheduler executor 语义。
- 不改 artifact model / registry / schema。
- 不改 API / SPA。
- 不接 LaunchAgent、cron、heartbeat。

## 4. Owned Files

默认允许修改：

- `src/ashare_evidence/cli_autonomous_flow.py`
- `src/ashare_evidence/cli_autonomous_flow_outputs.py`
- `tests/test_cli_autonomous_flow_execution.py`
- `tests/test_cli_autonomous_flow_diagnostics.py`
- `tests/test_cli_autonomous_flow_outputs.py`
- `tests/test_cli_autonomous_flow_smoke.py`
- `tests/test_cli_autonomous_flow_smoke_execution.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_AK_EVALUATION_CN.md`

文件规模要求：

- `cli_autonomous_flow.py` 必须降到 140 行以下。
- 新 output handler 模块应低于 180 行。
- 不向 `tests/test_cli_autonomous_flow_outputs.py` 追加新场景。

## 5. Tests

至少覆盖：

- 现有 CLI output tests 全部通过。
- 现有 diagnostic / execution / smoke tests 全部通过。
- `phase5-local-cycle-step` 仍在 DB 初始化前 dispatch。
- process hardening 检查 CLI 主文件和新 output handler 文件预算。

## 6. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_outputs.py tests/test_cli_autonomous_flow_diagnostics.py tests/test_cli_autonomous_flow_execution.py tests/test_cli_autonomous_flow_smoke.py tests/test_cli_autonomous_flow_smoke_execution.py -q`
- `ruff check src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli_autonomous_flow_outputs.py tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_outputs.py tests/test_cli_autonomous_flow_diagnostics.py tests/test_cli_autonomous_flow_execution.py tests/test_cli_autonomous_flow_smoke.py tests/test_cli_autonomous_flow_smoke_execution.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_AK_EVALUATION_CN.md --line-budget src/ashare_evidence/cli_autonomous_flow.py:160:140 --line-budget src/ashare_evidence/cli_autonomous_flow_outputs.py:200:180 --line-budget tests/test_cli_autonomous_flow_outputs.py:300:280 --required-evidence tests/test_autonomous_flow_scheduler_execution_idempotency.py:legacy_ledger_conflict`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_AK_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_AK_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
- `PYTHONPATH=src python3 -m pytest -q`
