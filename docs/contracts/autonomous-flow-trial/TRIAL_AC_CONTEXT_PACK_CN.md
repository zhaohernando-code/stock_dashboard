# Trial AC Context Pack：CLI Test Fixture Split

状态：active input  
上游：Trial AB  
目标：拆分 CLI autonomous-flow 测试中的 smoke fixtures，降低接近 300 行的测试文件风险，保持所有产品行为不变。

## 1. 背景

Trial AB 后：

- `tests/test_cli_autonomous_flow_diagnostics.py` 为 291 行。
- `tests/test_cli_autonomous_flow_smoke.py` 为 298 行。
- diagnostics 测试直接从 smoke 测试文件导入 `_write_happy_path_artifacts`，形成测试文件之间的隐式耦合。

这违反了我们在 Trial V / Z / AA 逐步固化的流程约束：基座类功能不应靠继续向接近门禁的文件追加测试来推进。

## 2. 本轮目标

纯测试结构治理：

- 新增 `tests/helpers_cli_autonomous_flow_smoke.py`。
- 将 smoke artifact fixture、CLI runner、无泄露断言、数据库初始化 guard 等公共 helper 从 smoke 测试文件迁移到 helper。
- diagnostics 测试从 helper 导入 fixture，不再从另一个测试文件导入。
- 可为 diagnostics CLI 调用增加小 helper，减少重复 argv 代码。
- 不改变任何产品代码行为。
- 不改变 CLI 合同。

## 3. 非目标

- 不修改 `src/ashare_evidence` 产品代码，除非修复 import lint 的机械必要。
- 不新增 CLI output。
- 不改 artifact model/store。
- 不改 registry/schema。
- 不改 API / SPA。

## 4. Owned Files

默认只允许修改：

- `tests/helpers_cli_autonomous_flow_smoke.py`
- `tests/test_cli_autonomous_flow_smoke.py`
- `tests/test_cli_autonomous_flow_diagnostics.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_AC_EVALUATION_CN.md`

## 5. 验收标准

- `tests/test_cli_autonomous_flow_smoke.py` 低于 230 行。
- `tests/test_cli_autonomous_flow_diagnostics.py` 低于 250 行。
- 新 helper 低于 180 行。
- 不再出现 `from tests.test_cli_autonomous_flow_smoke import ...`。
- focused tests 通过。
- full regression 通过。

## 6. 验收命令

- `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_smoke.py tests/test_cli_autonomous_flow_diagnostics.py -q`
- `ruff check tests/helpers_cli_autonomous_flow_smoke.py tests/test_cli_autonomous_flow_smoke.py tests/test_cli_autonomous_flow_diagnostics.py`
- `wc -l tests/helpers_cli_autonomous_flow_smoke.py tests/test_cli_autonomous_flow_smoke.py tests/test_cli_autonomous_flow_diagnostics.py`
- `rg -n "from tests\\.test_cli_autonomous_flow_smoke import" tests`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_AC_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_AC_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
