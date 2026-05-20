# Trial T 评估记录：Phase 5 Scheduler Follow-up Plan

状态：进行中  
输入：`TRIAL_T_CONTEXT_PACK_CN.md`  
目标：评估 tick envelope 到 scheduler follow-up plan 的纯函数合同是否稳定，为后续真实 scheduler 执行层做准备。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| T1 | scheduler plan 模块、测试、本评估文件 | 实现 tick 到 follow-up plan 的纯函数 |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| Plan 合同符合度 | 35 |
| 行为映射完整性 | 30 |
| 副作用隔离 | 20 |
| 测试覆盖 | 15 |

自动重跑阈值：

- 总分低于 85。
- planner 读写文件、读 DB、读网络、调用 LLM 或读取当前时间。
- planner 执行 retry、写 recovery ticket 或修改 cycle。
- 输出包含完整 nested tick status/error payload。
- tick error 分类靠解析错误消息字符串。
- focused tests 失败。

## 3. T1 结果

完成。

改动文件：

- `src/ashare_evidence/autonomous_flow_scheduler_plan.py`
- `tests/test_autonomous_flow_scheduler_plan.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_T_EVALUATION_CN.md`

实现内容：

- 新增 `Phase5SchedulerFollowupPlan` 与 `plan_phase5_scheduler_followup(...)`。
- 输入只依赖 `Phase5LocalCycleTickResult` 的 typed 字段。
- 成功 tick 按 `summary_status` / `recommended_next_action` 生成 `ready` 或 `blocked` 计划。
- 失败 tick 按 `error.recommended_recovery_action` 生成 `open_recovery_ticket`、`retry_failed_step` 或 `block_cycle`。
- 输出为小 payload：`cycle_id`、`plan_status`、`action`、`reason`、`source_tick_status`、`summary_status`、`claim_ceiling`、`blocking_reasons`。
- 不输出完整 nested `status` / `error` payload，不输出 input bundle、artifact payload、release manifest ref、digest 或 traceback。
- error 路径不读取或解析 `error.message` 参与计划；计划 reason 只使用 typed `failure_class` / `recommended_recovery_action`。
- blocking reasons 稳定去重；missing refs 只映射为泛化阻塞原因，避免把 artifact ref 继续传播到 scheduler 计划层。
- 对 ok tick 中可能携带的 release manifest ref / digest 做输出脱敏；脱敏只用于输出，不参与控制流判断。

覆盖测试：

- completed + continue tracking。
- degraded + rebuild projection。
- degraded + retry failed step。
- degraded + redesign。
- blocked ok tick -> block cycle。
- missing cycle / artifact missing -> open recovery ticket。
- unexpected error / retry_with_backoff -> retry failed step。
- contract violation / block_cycle -> blocked。
- payload 不泄露 nested status/error、release manifest ref、digest、traceback。
- blocking reasons 稳定去重，missing refs 泛化。
- planner 不修改输入对象。

## 4. 主进程验证

主进程复核结论：通过。

已验证：

- `plan_phase5_scheduler_followup(...)` 是纯函数，只读取 `Phase5LocalCycleTickResult` typed 字段。
- 输出为小型 `Phase5SchedulerFollowupPlan`，不包含完整 nested `status` / `error` payload。
- 成功 tick 映射覆盖 continue tracking、rebuild projection、retry failed step、redesign、blocked。
- 失败 tick 映射覆盖 open recovery ticket、retry with backoff、block cycle。
- error 路径不解析 `error.message` 参与控制流，只使用 `failure_class` 和 `recommended_recovery_action`。
- blocking reasons 稳定去重，missing refs 被泛化为 scheduler 可消费原因，不传播具体 artifact ref。
- 输出对 release manifest ref / digest 做脱敏，且不包含 traceback。
- 不修改输入对象。

跑偏检查：

- 本轮未修改 CLI、tick、resolver、service、runner、planner、status projection、artifact model、registry、API 或 frontend。
- 没有执行 retry/backoff，没有写 recovery ticket，没有修改 cycle closeout。
- 没有接入 LaunchAgent、cron、heartbeat 或真实 scheduler。
- 错误诊断详情没有进入 follow-up plan；后续如需可观测诊断，应设计独立 diagnostic artifact，而不是扩大 scheduler plan。

主进程门禁：

| 命令 | 结果 |
| --- | --- |
| `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_scheduler_plan.py tests/test_autonomous_flow_tick.py -q` | 21 passed |
| `ruff check src/ashare_evidence/autonomous_flow_scheduler_plan.py tests/test_autonomous_flow_scheduler_plan.py` | pass |
| `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_T_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_T_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated` | status=pass, issue_count=0 |
| `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_smoke.py tests/test_autonomous_flow_service.py tests/test_autonomous_flow_resolver.py tests/test_autonomous_flow_runner.py tests/test_autonomous_flow_planner.py tests/test_autonomous_flow_status.py tests/test_autonomous_flow_tick.py tests/test_autonomous_flow_scheduler_plan.py -q` | 71 passed |
| `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage` | pass |
| `git diff --check` | pass |
| `PYTHONPATH=src python3 -m pytest -q` | 320 passed, 147 deselected |

运行时发布验证：本轮只新增本地 scheduler plan 纯函数，不改变用户可见 Web/runtime 行为，因此不触发发布或浏览器验收。

## 5. 重跑记录

无需重跑子进程。

原因：

- T1 输出满足 Context Pack 的 owned files 与非目标边界。
- 未发现执行层越界、输出泄露、字符串解析分类或副作用问题。

## 6. 自评

T1 自评分：92 / 100。

- Plan 合同符合度：33 / 35。字段保持小而稳定，未扩展到真实 scheduler 执行层。
- 行为映射完整性：28 / 30。覆盖 Context Pack 要求的主要映射；对不一致 envelope 采用 fail-closed 小计划。
- 副作用隔离：20 / 20。纯函数，无文件、DB、网络、LLM、当前时间读取，也不执行 retry/backoff。
- 测试覆盖：11 / 15。focused tests 覆盖核心合同；未接入端到端 scheduler，因为本轮明确非目标。

剩余风险：

- 当前 follow-up plan 尚未接真实 scheduler / LaunchAgent，只能作为后续执行层输入。
- error 计划不传播原始错误 message，这是刻意的安全边界；如果后续运维需要详情，应通过独立、受控的 diagnostic artifact，而不是 scheduler plan。
