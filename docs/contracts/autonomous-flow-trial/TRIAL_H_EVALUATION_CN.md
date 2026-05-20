# Trial H 评估记录：Phase 5 Cycle Closeout 原语

状态：已完成  
输入：`TRIAL_H_CONTEXT_PACK_CN.md`  
目标：评估 cycle closeout 原语是否足以支撑后续 scheduler 终结周期和安排下一步动作。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| H1 | `autonomous_flow.py`、`test_autonomous_flow.py`、`test_autonomous_flow_closeout.py`、本评估文件 | 实现最小 cycle closeout 原语 |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| Closeout 合同符合度 | 35 |
| 状态/动作约束 | 25 |
| 测试覆盖 | 25 |
| 副作用控制 | 15 |

自动重跑阈值：

- 总分低于 85。
- 函数内部读取当前时间、DB、网络或 LLM。
- missing cycle 被静默创建。
- closeout 清空已有 refs 或 publish verification。
- blocked/completed/degraded 状态动作约束缺失。
- focused tests 失败。

## 3. H1 结果

实现文件：

- `src/ashare_evidence/autonomous_flow.py`
- `tests/test_autonomous_flow.py`
- `tests/test_autonomous_flow_closeout.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_H_EVALUATION_CN.md`

实现摘要：

- 新增 `finish_phase5_cycle(...) -> Phase5CycleLedgerArtifact`。
- closeout 前复用 `_require_cycle`，目标 cycle 不存在时抛出 `Phase5CycleNotFoundError`，不静默创建 ledger。
- closeout 只写 `status`、`finished_at`、`next_action` 三个字段。
- `finished_at` 完全由调用方传入；函数内部不读取当前时间。
- 未新增事件 id，未新增 artifact family，未读取 DB、网络或 LLM。
- 通过 `model_copy(update=...)` 保留既有 `event_refs`、`artifact_refs`、`gate_readout_refs`、`recovery_ticket_refs` 和 `publish_verification_ref`。

状态/动作约束：

- `status` 只允许 `completed`、`degraded`、`blocked`。
- `next_action` 只允许 ledger schema 既有枚举：`continue_tracking`、`rebuild_projection`、`retry_failed_step`、`redesign`、`blocked`、`none`。
- `blocked` closeout 必须使用 `next_action="blocked"`。
- `completed` closeout 拒绝 `next_action="blocked"` 和 `next_action="retry_failed_step"`。
- `degraded` closeout 拒绝 `next_action="none"`。

测试覆盖：

- running cycle finish 为 completed 后保留 artifact refs、gate refs、recovery refs、publish verification ref 和原 event refs。
- degraded closeout 支持 `rebuild_projection` 等后续动作。
- blocked closeout 支持并强制 `next_action="blocked"`。
- completed closeout 拒绝 blocked / retry next action。
- degraded closeout 拒绝 `next_action="none"`。
- missing cycle closeout fail-closed。
- closeout 前后 event refs 完全一致，确认不新增 event ref。

H1 本地验收：

| 命令 | 结果 |
| --- | --- |
| `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow.py -q` | `15 passed in 0.30s` |
| `ruff check src/ashare_evidence/autonomous_flow.py tests/test_autonomous_flow.py` | `All checks passed!` |
| `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_H_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_H_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated` | `status=pass`, `issue_count=0` |
| `git diff --check` | pass |

## 4. 主进程验证

主进程复核结论：通过。

复核重点：

- `finish_phase5_cycle(...)` 只更新 `status`、`finished_at`、`next_action`，不会改写已有 event refs、artifact refs、gate refs、recovery refs 或 publish verification ref。
- closeout 不新增事件 id；本轮不引入 scheduler plan artifact。
- 状态/动作约束在函数内执行，不依赖调用方自觉。
- missing cycle 继续 fail-closed。
- 函数没有读取当前时间、DB、网络或 LLM。

主进程门禁：

| 命令 | 结果 |
| --- | --- |
| `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow.py tests/test_autonomous_flow_closeout.py tests/test_autonomous_flow_artifacts.py -q` | 20 passed |
| `ruff check src/ashare_evidence/autonomous_flow.py tests/test_autonomous_flow.py tests/test_autonomous_flow_closeout.py` | pass |
| `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_H_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_H_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated` | status=pass, issue_count=0 |
| `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage` | pass |
| `PYTHONPATH=src python3 -m pytest -q` | 249 passed, 147 deselected |

运行时发布验证：本轮只新增本地 closeout 原语和测试，不改变用户可见 Web/runtime 行为，因此不触发发布或浏览器验收。

## 5. 重跑记录

无需重跑子进程。

原因：

- H1 输出满足 Context Pack 的 owned files 和非目标边界。
- 主进程将 closeout tests 从 `tests/test_autonomous_flow.py` 拆到 `tests/test_autonomous_flow_closeout.py`，解决 pre-commit 500 行文件大小门禁，不添加大文件豁免。
- 未发现 refs 丢失、事件新增、missing cycle 静默创建或副作用越界。
- 后续真实 scheduler / LaunchAgent / API / SPA / publish verifier 接入继续留在后续轮次。

## 6. 自评

| 维度 | 自评 |
| --- | ---: |
| Closeout 合同符合度 | 35 / 35 |
| 状态/动作约束 | 25 / 25 |
| 测试覆盖 | 25 / 25 |
| 副作用控制 | 15 / 15 |
| 总分 | 100 / 100 |

边界与后续：

- 本轮仅实现本地 closeout 原语；未接 scheduler、LaunchAgent、API、前端、数据库表或 runtime publish。
- 函数不读取 gate / recovery / projection artifact 自动决策，后续 scheduler 需要显式传入 `status`、`finished_at` 和 `next_action`。
- live-facing 完成状态仍需由主进程或后续 scheduler 结合 publish verification 事实决定，本轮不发布 runtime。
