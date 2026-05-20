# Trial AC 评估记录：CLI Test Fixture Split

状态：已完成  
输入：`TRIAL_AC_CONTEXT_PACK_CN.md`  
目标：评估 CLI autonomous-flow 测试 fixture 拆分是否消除测试文件规模与测试间耦合风险。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| AC1 | CLI smoke/diagnostic tests、shared helper、本评估文件 | 拆分测试 fixture，保持行为不变 |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 行为保持 | 35 |
| 测试文件规模治理 | 30 |
| 测试耦合消除 | 20 |
| 门禁完整性 | 15 |

自动重跑阈值：

- focused tests 失败。
- full regression 失败。
- smoke 或 diagnostics 测试仍接近 300 行。
- diagnostics 测试仍从 smoke 测试文件导入 helper。
- 产品代码发生非必要改动。

## 3. AC1 结果

实现完成。

改动文件：

- `tests/helpers_cli_autonomous_flow_smoke.py`
- `tests/test_cli_autonomous_flow_smoke.py`
- `tests/test_cli_autonomous_flow_diagnostics.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_AC_EVALUATION_CN.md`

实现内容：

- 新增 smoke 专用 helper，将真实 artifact 构造、CLI smoke runner、diagnostic CLI runner、无泄露断言、数据库初始化 guard 迁出测试文件。
- `tests/test_cli_autonomous_flow_smoke.py` 只保留 status / plan / dry-run 的真实 artifact root smoke 断言。
- `tests/test_cli_autonomous_flow_diagnostics.py` 改为从 helper 导入真实 artifact fixture，不再从 smoke 测试文件导入 helper。
- diagnostic 参数校验与真实 artifact smoke 用参数化压缩，保持 diagnostic happy path 与 missing cycle smoke 覆盖。
- 未修改 `src/ashare_evidence` 产品代码，未改变 CLI 行为或断言语义。

## 4. 主进程验证

已通过门禁：

- `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_smoke.py tests/test_cli_autonomous_flow_diagnostics.py -q`：`13 passed`
- `ruff check tests/helpers_cli_autonomous_flow_smoke.py tests/test_cli_autonomous_flow_smoke.py tests/test_cli_autonomous_flow_diagnostics.py`：通过
- `wc -l tests/helpers_cli_autonomous_flow_smoke.py tests/test_cli_autonomous_flow_smoke.py tests/test_cli_autonomous_flow_diagnostics.py`：
  - `tests/helpers_cli_autonomous_flow_smoke.py`：169 行
  - `tests/test_cli_autonomous_flow_smoke.py`：180 行
  - `tests/test_cli_autonomous_flow_diagnostics.py`：243 行
- `rg -n "from tests\\.test_cli_autonomous_flow_smoke import" tests`：无匹配
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_AC_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_AC_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`：`status=pass, issue_count=0`
- `git diff --check`：通过

补充门禁：

- `PYTHONPATH=src python3 -m pytest -q`：`366 passed, 147 deselected`

## 5. 重跑记录

本轮没有触发子进程重跑。

主进程内部修正：

- 第一次拆分后 `tests/test_cli_autonomous_flow_diagnostics.py` 仍为 274 行，未满足低于 250 行目标。
- 第二次将 diagnostic 参数校验和真实 artifact smoke 参数化，并把 diagnostic smoke record 断言迁入 helper，最终降至 243 行。

## 6. 自评

评分：94 / 100。

- 行为保持：35 / 35。只做测试结构治理，focused smoke 全部通过，未改产品代码。
- 测试文件规模治理：29 / 30。三个目标文件均低于阈值；diagnostics 仍接近 250 行，后续继续扩展 CLI diagnostic output 时应拆新测试文件。
- 测试耦合消除：20 / 20。diagnostics 不再从 smoke 测试文件导入 helper。
- 门禁完整性：15 / 15。focused、ruff、行数、耦合搜索、registry check、diff check、full regression 已完成。

残余风险：

- `tests/test_cli_autonomous_flow_diagnostics.py` 当前 243 行，后续不应继续向该文件追加大段 smoke 覆盖；如果扩展 diagnostic CLI 行为，应拆出新的 `test_cli_autonomous_flow_diagnostic_*` 测试文件或继续抽共享断言。
- `tests/helpers_cli_autonomous_flow_smoke.py` 当前 169 行，距离 180 行目标仍有余量但不多；后续新增 fixture 时需要优先判断是否应拆分为 smoke fixture 与 diagnostic fixture 两个 helper。
