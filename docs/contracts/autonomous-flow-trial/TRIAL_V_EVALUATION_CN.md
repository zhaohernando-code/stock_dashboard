# Trial V 评估记录：Split CLI Autonomous Flow Tests

状态：V1 complete  
输入：`TRIAL_V_CONTEXT_PACK_CN.md`  
目标：评估 CLI autonomous-flow 单元测试是否已拆分，避免单文件接近 pre-commit 规模门禁。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| V1 | CLI 单元测试拆分、本评估文件 | 拆分测试文件并保持覆盖 |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 覆盖保持 | 35 |
| 文件规模风险降低 | 30 |
| 测试结构清晰度 | 20 |
| 副作用隔离 | 15 |

自动重跑阈值：

- 总分低于 85。
- 任一拆分后测试文件超过 300 行。
- 原有关键覆盖缺失。
- 生产代码被修改。
- focused tests 失败。

## 3. V1 结果

完成。

改动范围：

- `tests/helpers_cli_autonomous_flow.py`：提取 `_FakeServiceResult`、`_FakeTickResult`、`_FakePlanResult`、`_args(...)`、`_ok_service_result(...)`、`_ok_tick_result(...)`、`_error_tick_result(...)`、`_plan_result(...)`。
- `tests/test_cli_autonomous_flow.py`：保留 parser/default status/main DB 初始化等基础覆盖。
- `tests/test_cli_autonomous_flow_outputs.py`：承接 `--output plan` 与 `--output full` 相关覆盖。

保留覆盖：

- parser 默认 `status`。
- parser 支持 `plan`。
- default status 调 tick、不调 service。
- default status 参数透传。
- default error tick 返回 tick exit code。
- plan 调 tick + follow-up planner，不调 service。
- plan 参数透传。
- plan error tick 返回 0 和 plan。
- full 输出完整 service result，不调 tick/plan。
- full service error 返回 CLI error JSON。
- `cli.main(...)` 不触发 DB 初始化。

文件行数：

- `tests/test_cli_autonomous_flow.py`：173 行。
- `tests/test_cli_autonomous_flow_outputs.py`：202 行。
- `tests/helpers_cli_autonomous_flow.py`：129 行。

未修改生产代码，未修改 smoke tests。

验证：

- `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_outputs.py tests/test_cli_autonomous_flow_smoke.py -q`：15 passed。
- `ruff check tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_outputs.py tests/helpers_cli_autonomous_flow.py`：passed。
- `wc -l tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_outputs.py tests/helpers_cli_autonomous_flow.py`：全部低于 300 行。
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_V_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_V_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`：passed，`issue_count=0`。
- `git diff --check`：passed。

## 4. 主进程验证

主进程复核结论：通过。

已验证：

- 本轮未修改生产代码；变更范围限于 CLI 单元测试拆分、测试 helper 和 Trial V 文档。
- `tests/test_cli_autonomous_flow.py` 从 475 行降到 173 行。
- `tests/test_cli_autonomous_flow_outputs.py` 为 202 行。
- `tests/helpers_cli_autonomous_flow.py` 为 129 行。
- 三个文件均低于 300 行，明显远离 500 行 pre-commit 风险线。
- Context Pack 第 5 节列出的覆盖全部保留：
  - parser 默认 status。
  - parser 支持 plan。
  - default status 调 tick、不调 service。
  - default status 参数透传。
  - default error tick 返回 tick exit code。
  - plan 调 tick + follow-up planner，不调 service。
  - plan 参数透传。
  - plan error tick 返回 0 和 plan。
  - full 输出完整 service result，不调 tick/plan。
  - full service error 返回 CLI error JSON。
  - `cli.main(...)` 不触发 DB 初始化。

跑偏检查：

- 没有改 CLI 行为、输出合同或 smoke test。
- helper 文件只包含 fake result 与参数 helper，不包含生产逻辑。
- 这是流程质量修复：避免后续新增 CLI 测试时再次触发单文件规模门禁。

主进程门禁：

| 命令 | 结果 |
| --- | --- |
| `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_outputs.py tests/test_cli_autonomous_flow_smoke.py -q` | 15 passed |
| `ruff check tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_outputs.py tests/helpers_cli_autonomous_flow.py` | pass |
| `wc -l tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_outputs.py tests/helpers_cli_autonomous_flow.py` | 173 / 202 / 129 |
| `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_outputs.py tests/test_cli_autonomous_flow_smoke.py tests/test_autonomous_flow_scheduler_plan.py tests/test_autonomous_flow_tick.py -q` | 36 passed |
| `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage` | pass |
| `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_V_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_V_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated` | status=pass, issue_count=0 |
| `git diff --check` | pass |
| `PYTHONPATH=src python3 -m pytest -q` | 326 passed, 147 deselected |

运行时发布验证：本轮只拆分测试，不改变用户可见 Web/runtime 行为，因此不触发发布或浏览器验收。

## 5. 重跑记录

无需重跑子进程。

原因：

- V1 输出满足 Context Pack 的 owned files 与非目标边界。
- 未发现覆盖缺失、生产代码改动、文件规模超线或测试语义改变。

## 6. 自评

评分：95/100。

- 覆盖保持：35/35，Context Pack 第 5 节列出的关键覆盖均保留。
- 文件规模风险降低：30/30，拆分后三个相关文件均低于 300 行。
- 测试结构清晰度：18/20，输出模式测试已经独立，基础 CLI 测试更短；helper 仍使用下划线命名以减少对既有测试语义的扰动。
- 副作用隔离：12/15，只做测试结构重构，未改生产代码；剩余风险是后续新增 CLI 输出模式时需要同步判断归属文件，避免原文件再次膨胀。

剩余风险：

- helper 文件中的 fake payload 仍需要跟随 CLI 输出合同演进；后续如新增敏感字段 denylist，应同步扩展相关输出测试。
