# Trial AT 上下文包：Action Output Blocked Exit Code

目标：为 `phase5-local-cycle-step --output action` 固化进程级 exit code 语义：completed action 返回 0，blocked action 返回非 0。该规则只作用于 action output，不改变 `plan`、`dry-run`、`diagnostic`、`execution` 或 `full`。

## 1. 背景

Trial AS 已把 no-op action executor 接到 CLI，但为了沿用 `plan` / `dry-run` 输出习惯，blocked action result 仍返回 exit code 0。对于无人化调度来说，`--output action` 已经是执行入口，blocked 代表当前 action 没有完成，需要上层调度器进入恢复或下一步判断；仅靠 JSON 内字段容易被 shell/cron/orchestrator 忽略。

本轮要把这个风险固化为合同：`action` output 的 JSON 仍然完整输出，但进程级 exit code 也要表达执行是否完成。

## 2. 本轮范围

必须做：

- `--output action` 中，当 action result `execution_status=="completed"` 时返回 0。
- 当 action result `execution_status=="blocked"` 时返回固定非 0 exit code，建议 4。
- blocked 时仍打印 action result JSON，不改 JSON schema。
- 不影响 `status`、`plan`、`dry-run`、`diagnostic`、`execution`、`full` 的 exit code 语义。
- 更新 existing action output 测试中的 missing cycle 断言，或新增极小测试文件；不得让 `tests/test_cli_autonomous_flow_action_output.py` 达到 warning line budget。
- 在评估中记录：这是执行入口专属语义，预览输出仍返回 0。

不得做：

- 不改变 action executor result model。
- 不新增 ledger、diagnostic、recovery ticket、projection、closeout 写入。
- 不改变 `execution` output 的 idempotency conflict exit code 3。
- 不改变 `status` output 对 tick exit code 的传递。

## 3. 建议实现

建议在 `cli_autonomous_flow_outputs.py` 增加小型 helper：

```python
_ACTION_BLOCKED_EXIT_CODE = 4

def _action_exit_code(action_result: Any) -> int:
    if getattr(action_result, "execution_status", None) == "blocked":
        return _ACTION_BLOCKED_EXIT_CODE
    return 0
```

如果 action result 在测试中是 fake object 且没有属性，可用 payload 或 object attribute，但实现不要解析 JSON 字符串。

## 4. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| AT1 | CLI action output exit code、测试、本评估文件 | 固化 blocked action 非 0 exit code |

子进程注意：这是调度合同修正，不是重新设计 CLI。范围越小越好。

## 5. 文件规模预算

- `src/ashare_evidence/cli_autonomous_flow_outputs.py`：hard 240，warning 220。
- `tests/test_cli_autonomous_flow_action_output.py`：hard 220，warning 190。当前约 189 行，不得增加体量；如果必须新增覆盖，请拆到新测试文件。
- `tests/test_cli_autonomous_flow_action_exit_code.py`：hard 140，warning 120，可选。

如果任何目标文件达到 warning，必须在本轮处理。

## 6. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_action_output.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/cli_autonomous_flow_outputs.py tests/test_cli_autonomous_flow_action_output.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_AT_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/cli_autonomous_flow_outputs.py:240:220 \
  --line-budget tests/test_cli_autonomous_flow_action_output.py:220:190 \
  --required-evidence tests/test_cli_autonomous_flow_action_output.py:test_phase5_local_cycle_step_action_smoke_missing_cycle_blocks_without_writes
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_AT_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_AT_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
