# Trial AT 评估记录：Action Output Blocked Exit Code

状态：completed, main verification passed
输入：`TRIAL_AT_CONTEXT_PACK_CN.md`
目标：评估 `phase5-local-cycle-step --output action` 是否在 blocked action result 时返回非 0 exit code，同时保持 JSON 输出和其他 output 模式不变。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| AT1 | CLI action output exit code、测试、本评估文件 | 固化 blocked action 非 0 exit code | completed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| action exit code 语义 | 35 |
| 其他 output 模式不回归 | 25 |
| 副作用边界 | 20 |
| 文件规模与门禁 | 20 |

自动重跑阈值：

- completed action 不返回 0。
- blocked action 不返回固定非 0 exit code。
- blocked action 不再打印 typed JSON。
- 修改 action executor result model。
- 影响 `execution` idempotency conflict exit code 3 或 `status` tick exit code 语义。
- focused tests、ruff、process hardening、registry 或 full regression 失败。

## 3. AT1 结果

实现结果：

- `--output action` 在 typed action result `execution_status=="completed"` 时返回 exit code `0`。
- `--output action` 在 typed action result `execution_status=="blocked"` 时返回固定 exit code `4`。
- blocked action 仍先打印完整 typed action result JSON；未改变 JSON schema。
- 未修改 action executor、ledger/reservation、artifact store、`autonomous_flow.py`、diagnostic/recovery/projection/closeout 逻辑。
- 未改变 `plan`、`dry-run`、`diagnostic`、`execution`、`full`、`status` output 语义；该 exit code 规则仅适用于 action 执行入口。

AT1 验证：

- `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_action_output.py -q`：通过，`3 passed in 0.47s`。
- `ruff check src/ashare_evidence/cli_autonomous_flow_outputs.py tests/test_cli_autonomous_flow_action_output.py`：通过，`All checks passed!`。
- `wc -l src/ashare_evidence/cli_autonomous_flow_outputs.py tests/test_cli_autonomous_flow_action_output.py`：输出模块 `209` 行，action output 测试 `189` 行，均低于 hard limit，测试文件未超过 warning line budget。
- `PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_AT_EVALUATION_CN.md --line-budget src/ashare_evidence/cli_autonomous_flow_outputs.py:240:220 --line-budget tests/test_cli_autonomous_flow_action_output.py:220:190 --required-evidence tests/test_cli_autonomous_flow_action_output.py:test_phase5_local_cycle_step_action_smoke_missing_cycle_blocks_without_writes`：通过，`status: pass`，`issue_count: 0`。
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_AT_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_AT_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`：通过，`status: pass`，`issue_count: 0`。
- `PYTHONPATH=src python3 -m pytest -q`：通过，`438 passed, 147 deselected in 20.61s`。

## 4. 主进程验证

主进程语义审查：

- action output 仍然先打印 `action_result.model_dump(mode="json")`，再根据 typed result 决定 exit code。
- completed action 返回 0，blocked action 返回固定 exit code 4。
- helper 使用 result attribute；测试 fake object 只通过 payload fallback 支持，不解析 JSON 字符串。
- 本轮没有修改 action executor、ledger/reservation、artifact store、diagnostic/recovery/projection/closeout 或 `autonomous_flow.py`。
- 主进程补跑 action/status/execution 相关 focused regression：15 passed，确认 `status` tick exit code 和 `execution` idempotency conflict exit code 语义未被本轮修改。

主进程门禁：

- focused pytest：15 passed。
- ruff：passed。
- process hardening：passed，0 issues。
- contract registry：passed，0 issues。
- diff check：passed。
- full regression：438 passed，147 deselected。

## 5. 重跑记录

- 首次 focused test 因测试断言位置误改失败：completed action 断言被改为 `4`，blocked smoke 仍断言 `0`。
- 修正断言后 focused test 通过。

## 6. 自评

AT1 自评：满足本轮合同目标。focused tests、process hardening、registry 和 full regression 均已通过；残余风险较低，主要在后续合入时需确认其他子进程没有同时改动 action output exit code 语义。
