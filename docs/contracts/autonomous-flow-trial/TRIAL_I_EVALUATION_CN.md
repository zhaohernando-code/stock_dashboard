# Trial I 评估记录：Phase 5 本地 Planner 决策原语

状态：已完成  
输入：`TRIAL_I_CONTEXT_PACK_CN.md`  
目标：评估本地 planner 是否足以作为后续 scheduler 的决策前置层。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| I1 | `autonomous_flow_planner.py`、`test_autonomous_flow_planner.py`、本评估文件 | 实现纯本地 planner 决策原语 |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| Planner 合同符合度 | 35 |
| 保守优先级与 claim ceiling | 25 |
| 测试覆盖 | 25 |
| 副作用控制 | 15 |

自动重跑阈值：

- 总分低于 85。
- planner 内部读取当前时间、DB、网络、文件或 LLM。
- gate missing、projection stale、publish pending 仍输出 completed。
- blocker 场景没有输出 `next_action="blocked"`。
- 输出 claim ceiling 高于输入 gate 或缺 gate 默认值。
- focused tests 失败。

## 3. I1 结果

I1 已实现 Phase 5 本地 planner 决策原语：

- 新增 `src/ashare_evidence/autonomous_flow_planner.py`，暴露 `Phase5PlannerDecision` 与 `plan_phase5_next_step(...)`。
- planner 只接收调用方传入的 typed artifacts，不读取 DB / 网络 / 文件 / 当前时间，不调用 LLM，也不调用 `finish_phase5_cycle`。
- 按 Context Pack 优先级处理 cycle blocked、recovery blocked、gate blocked、缺 gate、projection missing/stale/degraded、publish verification pending、gate requested next action、completed fallback。
- blocker 与缺 gate 场景保守降低 claim ceiling；非 blocker 场景不提升 gate readout 已给出的 claim ceiling。
- `source_refs` 只由输入 artifact id 组成：`cycle_id`、`gate_id`、`ticket_id`、`projection_id`。

I1 focused tests 覆盖：

- cycle 已 blocked 直接输出 `blocked` / `next_action="blocked"`。
- recovery blocked 优先于 passed gate。
- gate blocked 优先于 fresh projection。
- 缺 gate 降级 `retry_failed_step` 且 claim ceiling 为 `research_observation`。
- 缺 projection 降级 `rebuild_projection`。
- stale/degraded projection 降级 `rebuild_projection`。
- required publish verification 缺 ref 时降级 `retry_failed_step`。
- gate requested `redesign` / `retry_failed_step` / `rebuild_projection` / `continue_tracking` 被保留。
- 输出 `source_refs` 可追溯到输入 artifact id。
- planner 不修改输入对象。

## 4. 主进程验证

主进程复核结论：通过。

复核重点：

- planner 只接收调用方传入的 typed artifacts，不读 artifact store、DB、网络、文件或当前时间。
- blocker 优先级符合 Context Pack：cycle blocked > recovery blocked > gate blocked > gate missing > projection missing/stale/degraded > publish pending > gate next action。
- 缺 gate 时 claim ceiling 保守降到 `research_observation`；blocked 场景降到 `blocked`。
- projection stale / publish pending 场景不提升 gate readout 的 claim ceiling。是否进一步压低 claim ceiling 留给后续 gate evaluator，不在 planner 内重复定义策略。
- `source_refs` 来自输入 artifact ids，测试覆盖了输入对象不可变。
- 当前 typed gate model 没有 `next_action="none"`，因此 fresh + gate `continue_tracking` 会按 Context Pack 保留 `continue_tracking`；真正 `completed + none` closeout 可由后续 scheduler 在确认无需继续跟踪时显式调用 `finish_phase5_cycle(...)`。

主进程门禁：

| 命令 | 结果 |
| --- | --- |
| `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_planner.py -q` | 10 passed |
| `ruff check src/ashare_evidence/autonomous_flow_planner.py tests/test_autonomous_flow_planner.py` | pass |
| `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_I_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_I_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated` | status=pass, issue_count=0 |
| `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage` | pass |
| `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow.py tests/test_autonomous_flow_artifacts.py tests/test_autonomous_flow_closeout.py tests/test_autonomous_flow_planner.py -q` | 30 passed |
| `git diff --check` | pass |
| `PYTHONPATH=src python3 -m pytest -q` | 259 passed, 147 deselected |

运行时发布验证：本轮只新增纯本地 planner 和测试，不改变用户可见 Web/runtime 行为，因此不触发发布或浏览器验收。

## 5. 重跑记录

无需重跑子进程。

原因：

- I1 输出满足 Context Pack 的 owned files 和非目标边界。
- 未发现副作用越界、claim ceiling 提升、blocker 优先级错误或输入对象 mutation。
- 后续真实 scheduler、LaunchAgent、API / SPA、publish verifier 接入继续留在后续轮次。

## 6. 自评

I1 自评：

- Planner 合同符合度：34/35。命名、输入、输出、typed decision 和纯函数边界均符合；`completed + none` 分支保留为未来 typed gate action 扩展兜底，当前模型下 gate readout 的 `continue_tracking` 会按要求被保留。
- 保守优先级与 claim ceiling：24/25。blocker 降到 `blocked`，缺 gate 降到 `research_observation`，其他 degraded 场景不提升 gate ceiling；projection stale/publish pending 是否还应进一步压低 ceiling 交由后续 gate evaluator 策略决定。
- 测试覆盖：25/25。覆盖 Context Pack 要求的核心分支、source refs 和不可变输入。
- 副作用控制：15/15。planner 模块没有 artifact store、DB、网络、文件、时间或 LLM 依赖。

总分：98/100。
