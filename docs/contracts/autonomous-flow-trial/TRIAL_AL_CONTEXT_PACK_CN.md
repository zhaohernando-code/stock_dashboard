# Trial AL Context Pack：CLI Output Tests Split

状态：active input  
上游：Trial AK  
目标：拆分 `tests/test_cli_autonomous_flow_outputs.py`，消除 output 测试文件 284 行 warning，避免后续 output 行为变更继续堆叠。

## 1. 背景

Trial AK 已拆分 CLI output handler，但 process hardening 仍提示：

- `tests/test_cli_autonomous_flow_outputs.py`：284 行，达到 warning 线 280。

本轮只做测试结构拆分，不修改生产代码行为。

## 2. 本轮目标

- 将 plan、dry-run、full output 测试拆成更小主题文件。
- 保留既有断言和行为覆盖。
- 不新增 CLI output。
- 不修改 production code，除非测试导入路径拆分确实需要。

## 3. Owned Files

默认允许修改：

- `tests/test_cli_autonomous_flow_outputs.py`
- `tests/test_cli_autonomous_flow_plan_output.py`
- `tests/test_cli_autonomous_flow_dry_run_output.py`
- `tests/test_cli_autonomous_flow_full_output.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_AL_EVALUATION_CN.md`

## 4. 文件规模要求

- 原 `test_cli_autonomous_flow_outputs.py` 应降到 120 行以下，或只保留轻量兼容/导入说明。
- 新测试文件各低于 180 行。
- 不修改 `tests/helpers_cli_autonomous_flow.py`，除非必须。

## 5. Tests

至少覆盖拆分前已有场景：

- plan output 调用 tick + follow-up planner，不调用 service。
- plan output 参数透传。
- error tick 仍输出 plan。
- dry-run output 调用 tick + plan + dry-run executor，不调用 service。
- dry-run error tick 返回 0。
- full output 调 service，不调用 tick/plan。
- full service error 输出 error JSON。

## 6. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_outputs.py tests/test_cli_autonomous_flow_plan_output.py tests/test_cli_autonomous_flow_dry_run_output.py tests/test_cli_autonomous_flow_full_output.py -q`
- `ruff check tests/test_cli_autonomous_flow_outputs.py tests/test_cli_autonomous_flow_plan_output.py tests/test_cli_autonomous_flow_dry_run_output.py tests/test_cli_autonomous_flow_full_output.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_AL_EVALUATION_CN.md --line-budget tests/test_cli_autonomous_flow_outputs.py:140:120 --line-budget tests/test_cli_autonomous_flow_plan_output.py:180:150 --line-budget tests/test_cli_autonomous_flow_dry_run_output.py:180:150 --line-budget tests/test_cli_autonomous_flow_full_output.py:180:150 --required-evidence tests/test_autonomous_flow_scheduler_execution_idempotency.py:legacy_ledger_conflict`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_AL_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_AL_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
- `PYTHONPATH=src python3 -m pytest -q`
