# Trial BV 上下文包：Attempt Run Operations Readout

目标：基于 `phase5_scheduler_attempt_run` 查询层生成一个轻量 operations readout，供后续中台 SPA、reviewer 和 scheduler 查看最近运行状态。本轮只做纯 readout builder，不新增 artifact family，不改 CLI。

## 1. 背景

BS 已能 opt-in 写入 attempt/run artifact，BT/BU 已提供稳定查询层。现在缺少面向看板和调度器的汇总视图：调用方仍需要自己判断 latest、blocked 数量、最近 successful/applied run、最近 blocked run 等。

本轮先做纯函数 readout：从 query 返回的 artifact 列表构建结构化状态摘要。字段稳定后，再决定是否注册为 frontend projection 或正式 artifact。

## 2. 本轮范围

必须做：

- 新增独立模块，例如 `scheduler_attempt_run_readout.py`。
- 提供 Pydantic readout model，字段至少包含：`cycle_id`、`runner_id`、`total_runs`、`latest_run_id`、`latest_apply_status`、`latest_attempt_status`、`latest_issued_at`、`applied_count`、`blocked_count`、`skipped_count`、`latest_blocked_run_id`、`latest_applied_run_id`、`staleness_status`、`run_refs`。
- 提供 builder：从 iterable artifacts 生成 readout，不做 IO。
- 提供 convenience function：通过 query layer 按可选 cycle/runner 读取后生成 readout。
- 空输入要返回 degraded readout，不崩溃。
- 不解析 reason，不读取 CLI 输出。
- 新增 focused tests 覆盖空输入、混合状态汇总、cycle/runner query convenience。

不得做：

- 不新增 registry artifact/event。
- 不改 CLI。
- 不改 artifact schema。
- 不修改 `process_hardening.py`。

## 3. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| BV1 | readout module、focused tests、本评估文件 | 生成可供看板读取的 attempt/run 状态摘要 |

## 4. 文件规模预算

- `src/ashare_evidence/scheduler_attempt_run_readout.py`：hard 180，warning 140。
- `tests/test_scheduler_attempt_run_readout.py`：hard 240，warning 190。
- `docs/contracts/autonomous-flow-trial/TRIAL_BV_EVALUATION_CN.md`：hard 150，warning 120。

## 5. 验证命令

Focused tests：

```bash
PYTHONPATH=src python3 -m pytest tests/test_scheduler_attempt_run_readout.py -q
```

Ruff：

```bash
ruff check src/ashare_evidence/scheduler_attempt_run_readout.py tests/test_scheduler_attempt_run_readout.py
```

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_BV_EVALUATION_CN.md \
  --line-budget src/ashare_evidence/scheduler_attempt_run_readout.py:180:140 \
  --line-budget tests/test_scheduler_attempt_run_readout.py:240:190 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_BV_EVALUATION_CN.md:150:120 \
  --required-evidence tests/test_scheduler_attempt_run_readout.py:test_build_attempt_run_readout_handles_empty_input \
  --required-evidence tests/test_scheduler_attempt_run_readout.py:test_build_attempt_run_readout_summarizes_mixed_runs \
  --forbidden-source-token src/ashare_evidence/scheduler_attempt_run_readout.py:"reason ==" \
  --forbidden-source-token src/ashare_evidence/scheduler_attempt_run_readout.py:datetime.now \
  --forbidden-source-token src/ashare_evidence/scheduler_attempt_run_readout.py:uuid \
  --forbidden-source-token src/ashare_evidence/scheduler_attempt_run_readout.py:random
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BV_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BV_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
