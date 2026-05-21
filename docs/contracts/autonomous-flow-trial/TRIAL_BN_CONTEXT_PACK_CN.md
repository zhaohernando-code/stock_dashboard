# Trial BN 上下文包：Process Hardening Warning Margin Gate

目标：把 BM 暴露出的“文件接近 warning 线时不能继续堆叠”的流程经验转成机器门禁。新增可选 warning margin 检查，让主进程能要求某些文件距离 warning line budget 至少保留 N 行余量。

## 1. 背景

BM 后 `tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py` 为 178 行，warning 180；`cli_autonomous_flow_outputs.py` 为 150 行，warning 160。它们未达到 warning，因此现有 `--fail-on-warning` 不会阻断，但工程上已经不适合继续扩写。后续流程需要能表达“该文件虽然未到 warning，但剩余余量不足，必须拆分”。

既有 `process_hardening.py` 已接近自身预算，本轮不得继续扩写核心模块；应新增小模块，在 CLI governance 层组合。

## 2. 本轮范围

必须做：

- 新增独立模块，例如 `src/ashare_evidence/process_hardening_line_margin.py`。
- 提供 parser，例如 `parse_line_budget_warning_margin("path:minimum_remaining")`。
- 提供 checker，例如 `check_line_budget_warning_margins(checked_line_budgets, margin_specs)`。
- CLI `process-hardening-check` 新增可重复参数，例如 `--line-budget-warning-margin path:minimum_remaining`。
- 检查基于现有 line budget 结果：只有已配置 warning limit 的文件可检查 margin。
- 若 `warning_limit - line_count < minimum_remaining`，产生 warning issue；配合现有 `--fail-on-warning` 可 fail。
- 若 margin 指向未在 `--line-budget` 中出现的文件，fail closed 为 error。
- 若目标 line budget 没有 warning limit，fail closed 为 error。
- 不修改 `process_hardening.py`，避免核心模块继续膨胀。
- 不改变现有 `--line-budget`、`--fail-on-warning`、`--require-clean-git-status` 行为。

不得做：

- 不把 margin 逻辑塞进 `process_hardening.py`。
- 不用字符串解析 JSON 输出。
- 不新增运行时 DB 或 artifact 写入。
- 不改变 existing line budget warning reached 的语义。

## 3. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| BN1 | warning margin 模块、CLI 组合、测试、本评估文件 | 新增 line budget warning margin 门禁 |

## 4. 文件规模预算

- `src/ashare_evidence/process_hardening.py`：hard 240，warning 230，不允许修改。
- `src/ashare_evidence/cli_governance.py`：hard 190，warning 170。
- `src/ashare_evidence/process_hardening_line_margin.py`：hard 140，warning 110。
- `tests/test_process_hardening_line_margin.py`：hard 220，warning 180。
- `docs/contracts/autonomous-flow-trial/TRIAL_BN_EVALUATION_CN.md`：hard 150，warning 120。

如果达到 warning，必须拆分或压缩。

## 5. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_process_hardening_line_margin.py tests/test_process_hardening.py tests/test_process_hardening_source.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/cli_governance.py src/ashare_evidence/process_hardening_line_margin.py tests/test_process_hardening_line_margin.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_BN_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/process_hardening.py:240:230 \
  --line-budget src/ashare_evidence/cli_governance.py:190:170 \
  --line-budget src/ashare_evidence/process_hardening_line_margin.py:140:110 \
  --line-budget tests/test_process_hardening_line_margin.py:220:180 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_BN_EVALUATION_CN.md:150:120 \
  --required-evidence tests/test_process_hardening_line_margin.py:test_cli_fails_on_warning_margin_when_fail_on_warning_is_set \
  --line-budget-warning-margin tests/test_process_hardening_line_margin.py:5
```

Self-check margin gate：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_BN_EVALUATION_CN.md \
  --line-budget tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py:220:180 \
  --line-budget-warning-margin tests/test_cli_autonomous_flow_attempt_route_auto_apply_output.py:5 \
  --fail-on-warning
# expected: fail
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BN_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BN_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
