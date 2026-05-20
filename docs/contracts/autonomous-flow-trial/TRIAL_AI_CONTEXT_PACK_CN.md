# Trial AI Context Pack：Legacy Migration Evidence Check

状态：active input  
上游：Trial AH  
目标：把 Trial AG/AH 的 legacy migration 验收要求升级为机器可执行的显式 evidence 检查。

## 1. 背景

Trial AH 已新增 `process-hardening-check`，覆盖 evaluation doc 完整性和 line budget。当前残余风险是 legacy migration 测试存在性仍只靠主进程人工审查。本轮做最小机器门禁：显式传入需要存在的测试证据，由 CLI 验证文件存在且包含指定 token。

当前规模信号：

- `src/ashare_evidence/process_hardening.py` 191 行，接近 200 warning 线。
- `tests/test_process_hardening.py` 154 行，低于 180 warning 线。

因此本轮不得继续把大量逻辑堆进 `process_hardening.py`；如果实现需要超过约 200 行，应拆出独立 helper/module。

## 2. 本轮目标

为 `process-hardening-check` 增加显式 required evidence 检查。

建议 CLI：

- `--required-evidence path:token`

行为：

- 文件不存在 -> failure。
- 文件存在但不包含 token -> failure。
- 文件存在且包含 token -> pass。
- 输出 JSON 增加 `required_evidence` 检查结果。
- 不初始化数据库，不读网络，不写文件。

## 3. 非目标

- 不做全仓扫描。
- 不做 AST 级测试语义证明。
- 不接 GitHub Actions。
- 不修改业务代码。
- 不修改 registry。

## 4. Owned Files

默认允许修改：

- `src/ashare_evidence/cli_governance.py`
- `src/ashare_evidence/process_hardening.py`
- 可新增 `src/ashare_evidence/process_hardening_evidence.py`
- `tests/test_process_hardening.py`
- 可新增 `tests/test_process_hardening_evidence.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_AI_EVALUATION_CN.md`

如果 CLI 接线无需改 `cli.py`，不得修改 `cli.py`。

## 5. Tests

至少覆盖：

- required evidence 文件存在且包含 token 时 pass。
- required evidence 文件缺失时 fail。
- required evidence 文件存在但缺 token 时 fail。
- CLI 输出包含 `required_evidence`。
- CLI 不初始化数据库。
- line budget / evaluation doc 既有测试继续通过。

## 6. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_process_hardening.py tests/test_process_hardening_evidence.py -q`
- `ruff check src/ashare_evidence/cli_governance.py src/ashare_evidence/process_hardening.py src/ashare_evidence/process_hardening_evidence.py tests/test_process_hardening.py tests/test_process_hardening_evidence.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_AH_EVALUATION_CN.md --line-budget src/ashare_evidence/process_hardening.py:220:200 --line-budget tests/test_process_hardening.py:220:180 --required-evidence tests/test_autonomous_flow_scheduler_execution_idempotency.py:legacy_ledger_conflict`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_AI_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_AI_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
- `PYTHONPATH=src python3 -m pytest -q`
