# Trial AA 评估记录：Scheduler Plan Diagnostic Recorder

状态：主进程复核通过  
输入：`TRIAL_AA_CONTEXT_PACK_CN.md`  
目标：评估 scheduler plan 是否能在执行真实 action 前写入小型 diagnostic artifact，保证失败和阻塞事实进入硬存储。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| AA1 | scheduler executor、executor tests、本评估文件 | 实现 plan diagnostic recorder |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| Diagnostic record 合同符合度 | 35 |
| cycle 缺失容错 | 20 |
| 无副作用边界 | 20 |
| 输出泄露保护 | 15 |
| 测试覆盖 | 10 |

自动重跑阈值：

- 总分低于 85。
- cycle 缺失时抛错或不写 diagnostic。
- 函数写 recovery ticket、创建 follow-up cycle 或执行真实 scheduler action。
- 修改 dry-run 既有输出合同。
- focused tests 失败。

## 3. AA1 结果

已完成。

实现文件：

- `src/ashare_evidence/autonomous_flow_scheduler_executor.py`
- `tests/test_autonomous_flow_scheduler_executor.py`
- `tests/test_autonomous_flow_scheduler_diagnostics.py`
- `tests/helpers_autonomous_flow_scheduler.py`

核心实现：

- 新增 `Phase5SchedulerDiagnosticRecordResult`，只返回 scheduler 诊断记录所需的小结果。
- 新增 `record_phase5_scheduler_plan_diagnostic(...)`，把 `Phase5SchedulerFollowupPlan` 映射为 `phase5_scheduler_diagnostic` artifact。
- 复用 `record_phase5_scheduler_diagnostic(...)` 持久化 diagnostic，并在 cycle 存在时只追加 `phase5.scheduler.diagnostic.recorded.v1` event。
- cycle 缺失时仍写 diagnostic，返回 `cycle_event_recorded=false`，不抛错。
- action 映射：
  - blocked plan / `block_cycle` -> severity `blocked`，failure class `blocked-plan`。
  - `open_recovery_ticket` / `retry_failed_step` -> severity `error`。
  - `rebuild_projection` / `redesign` -> severity `warning`。
  - `continue_tracking` / `none` -> severity `info`。
- sensitive text 处理：
  - result 与 diagnostic notes/blocking reasons 不暴露完整 plan/tick/status/input_bundle/runner_result/release manifest/digest/traceback。
  - `release-manifest:*` 和 `sha256:*` 使用摘要占位符替代。
  - `input_bundle`、`runner_result`、`Traceback` 触发整段敏感诊断文本替换。

边界确认：

- 未修改 CLI、tick、scheduler plan、artifact model、artifact store、cycle primitive、registry、schema、API、SPA。
- 未写 recovery ticket。
- 未创建 follow-up cycle。
- 未执行 retry/rebuild/redesign/block closeout。
- 未改变 dry-run executor 既有字段和测试语义。
- 未修改输入 plan 对象。

## 4. 主进程验证

指定门禁均已通过：

- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_scheduler_executor.py tests/test_autonomous_flow_scheduler_diagnostics.py tests/test_autonomous_flow.py tests/test_autonomous_flow_artifacts.py -q`
  - 结果：`41 passed`
- `ruff check src/ashare_evidence/autonomous_flow_scheduler_executor.py tests/test_autonomous_flow_scheduler_executor.py tests/test_autonomous_flow_scheduler_diagnostics.py tests/helpers_autonomous_flow_scheduler.py`
  - 结果：通过
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_AA_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_AA_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
  - 结果：`status=pass, issue_count=0`
- `git diff --check`
  - 结果：通过

补充检查：

- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_scheduler_executor.py -q`
  - 结果：`22 passed`
- `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage`
  - 结果：`status=pass`
- `PYTHONPATH=src python3 -m pytest -q`
  - 结果：`358 passed, 147 deselected`
- 文件行数：
  - `src/ashare_evidence/autonomous_flow_scheduler_executor.py`：172 行
  - `tests/test_autonomous_flow_scheduler_executor.py`：152 行
  - `tests/test_autonomous_flow_scheduler_diagnostics.py`：193 行
  - `tests/helpers_autonomous_flow_scheduler.py`：23 行

## 5. 重跑记录

第一次子进程实现后的功能门禁通过，但 `tests/test_autonomous_flow_scheduler_executor.py` 增长到 361 行，违背近期形成的测试规模治理约束。

主进程修正：

- 将 shared plan fixture 下沉到 `tests/helpers_autonomous_flow_scheduler.py`。
- 将 diagnostic recorder 覆盖拆到 `tests/test_autonomous_flow_scheduler_diagnostics.py`。
- 保留 `tests/test_autonomous_flow_scheduler_executor.py` 专注 dry-run executor。

拆分后 focused tests、ruff、registry check、diff check、policy audit、full regression 均重新通过。

## 6. 自评

评分：94 / 100。

扣分项：

- 本轮子进程首次输出存在测试文件膨胀问题；主进程已在本轮内拆分修正。后续流程应把“新增 executor 子能力时优先新增测试文件而不是扩原文件”写入默认实现约束。
- 当前 diagnostic recorder 只写 artifact 与 cycle event，不提供真实 scheduler action 的幂等执行协议；这是 Trial AA 非目标，但后续进入真实 executor 前需要单独设计 action execution ledger 或 dispatch contract。

结论：

- Trial AA 满足上下文包要求，可以作为后续真实 scheduler action 前的硬存储记录入口。
