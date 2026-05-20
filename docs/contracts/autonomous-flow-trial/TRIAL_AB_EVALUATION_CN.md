# Trial AB 评估记录：CLI Diagnostic Output

状态：完成  
输入：`TRIAL_AB_CONTEXT_PACK_CN.md`  
目标：评估 CLI 是否能触发 scheduler diagnostic 记录路径，同时保持既有 output 语义稳定。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| AB1 | CLI、CLI diagnostic tests、本评估文件 | 增加 `--output diagnostic` |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| CLI diagnostic 合同符合度 | 35 |
| 兼容性 | 25 |
| 硬存储与 cycle 缺失容错 | 20 |
| 输出泄露保护 | 10 |
| 测试规模治理 | 10 |

自动重跑阈值：

- 总分低于 85。
- `status`、`plan`、`dry-run` 或 `full` 语义改变。
- diagnostic 路径调用 service 或 dry-run executor。
- diagnostic 参数缺失仍执行 tick。
- cycle 缺失时 diagnostic 路径抛错或不写 artifact。
- 新增或修改的 CLI 测试文件超过 300 行。
- focused tests 失败。

## 3. AB1 结果

实现完成：

- `phase5-local-cycle-step --output diagnostic` 已接入。
- parser 新增 `--diagnostic-id` 与 `--observed-at`，仅 diagnostic output 强制要求。
- diagnostic 路径为 `tick -> plan_phase5_scheduler_followup -> record_phase5_scheduler_plan_diagnostic`。
- diagnostic 路径返回 `0`，输出 `Phase5SchedulerDiagnosticRecordResult` 小 JSON。
- 缺少 `--diagnostic-id` 或 `--observed-at` 时返回 `2`，输出小错误 JSON，并在执行 tick 前短路。
- `status`、`plan`、`dry-run`、`full` 语义保持不变。
- diagnostic 路径单测显式禁止调用 service 与 dry-run executor。
- 新增 `tests/test_cli_autonomous_flow_diagnostics.py`，没有继续扩展已接近 300 行的 smoke 测试文件。
- 真实 artifact root happy path 已覆盖：写入 scheduler diagnostic artifact，并向 cycle event refs 追加 diagnostic event。
- 真实 artifact root missing cycle 已覆盖：仍写入 diagnostic artifact，`cycle_event_recorded=false`，exit code 为 `0`。

## 4. 主进程验证

已通过：

- `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_outputs.py tests/test_cli_autonomous_flow_diagnostics.py tests/test_autonomous_flow_scheduler_diagnostics.py -q`
  - `34 passed`
- `ruff check src/ashare_evidence/cli_autonomous_flow.py tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_outputs.py tests/test_cli_autonomous_flow_diagnostics.py tests/helpers_cli_autonomous_flow.py`
  - 通过
- `wc -l tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_outputs.py tests/test_cli_autonomous_flow_diagnostics.py tests/test_cli_autonomous_flow_smoke.py tests/helpers_cli_autonomous_flow.py`
  - `205 tests/test_cli_autonomous_flow.py`
  - `284 tests/test_cli_autonomous_flow_outputs.py`
  - `291 tests/test_cli_autonomous_flow_diagnostics.py`
  - `298 tests/test_cli_autonomous_flow_smoke.py`
  - `241 tests/helpers_cli_autonomous_flow.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_AB_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_AB_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
  - `status=pass, issue_count=0`
- `git diff --check`
  - 通过
- 补充 policy audit：
  - `status=pass`
- 补充全量 pytest：
  - `366 passed, 147 deselected`

## 5. 重跑记录

本轮没有因行为失败重跑。

过程修正：

- 第一次 diagnostics 测试文件达到 `356` 行，违反 `<300` 行测试规模约束。
- 修正方式：复用既有 CLI smoke fixture，不复制大块 artifact fixture。
- 修正后 diagnostics 测试文件为 `291` 行，focused tests 仍通过。

## 6. 自评

评分：`95 / 100`

- CLI diagnostic 合同符合度：35 / 35。
- 兼容性：25 / 25。
- 硬存储与 cycle 缺失容错：20 / 20。
- 输出泄露保护：10 / 10。
- 测试规模治理：5 / 10。

残余风险：

- `tests/test_cli_autonomous_flow_smoke.py` 为 `298` 行，后续不得再追加。
- `tests/test_cli_autonomous_flow_diagnostics.py` 为 `291` 行，后续 CLI diagnostic 扩展应拆新文件或抽公共 fixture，不能继续堆叠。
- 本轮只记录 diagnostic fact，不执行 scheduler action、不写 recovery ticket、不创建 follow-up cycle，符合 Trial AB 非目标。
