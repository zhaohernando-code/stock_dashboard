# Trial BV 评估记录：Attempt Run Operations Readout

状态：verified
输入：`TRIAL_BV_CONTEXT_PACK_CN.md`
目标：评估 attempt/run operations readout 是否能为中台和调度器提供稳定状态摘要。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| BV1 | readout module、focused tests、本评估文件 | 生成可供看板读取的 attempt/run 状态摘要 | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 汇总字段完整性 | 35 |
| 空输入与降级语义 | 20 |
| query convenience 隔离 | 20 |
| 禁止 reason parsing | 15 |
| 验证完整性 | 10 |

自动重跑阈值：

- 新增 registry artifact/event。
- 修改 CLI 或 artifact schema。
- 从 reason 解析状态。
- 空输入崩溃或状态不明确。
- focused tests、ruff、process hardening、registry 或 full regression 失败。

## 3. BV1 结果

- 新增 `scheduler_attempt_run_readout.py`，提供冻结 Pydantic readout model、纯 builder、query convenience function。
- 空输入返回 `staleness_status=degraded`，latest 字段为 `None`，counts 和 refs 为空。
- builder 只读取 artifact 结构化字段，不解析 `reason`，不读取 CLI 输出，不新增 artifact/event。
- focused tests 覆盖空输入、混合状态汇总、cycle/runner convenience query。
- `staleness_status` 当前表达 latest run health：latest blocked 时为 `blocked`，有 run 且 latest 未 blocked 时为 `current`，无 run 时为 `degraded`；不是按时间窗口判断 freshness。

## 4. 主进程验证

- `PYTHONPATH=src python3 -m pytest tests/test_scheduler_attempt_run_readout.py -q`：通过，3 passed。
- `ruff check src/ashare_evidence/scheduler_attempt_run_readout.py tests/test_scheduler_attempt_run_readout.py`：通过。
- `PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check ...`：通过，0 issues。
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check ...`：通过，2 docs，0 issues。
- `PYTHONPATH=src python3 -m pytest -q`：通过，537 passed，147 deselected。
- `process-hardening-check` 首次发现本文件残留未完成标记，已移除并重跑。
- 主进程语义复核：readout 是纯 builder/query convenience，不写 artifact、不改 CLI，不解析 reason。

## 5. 重跑记录

- 无功能重跑；主进程补充 full regression 后通过。

## 6. 自评

- 汇总字段完整，query convenience 与 builder 分离，未触碰 CLI、schema、registry 或 `process_hardening.py`。
