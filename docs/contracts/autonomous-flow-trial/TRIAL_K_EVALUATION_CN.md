# Trial K 评估记录：Phase 5 Runner Input Resolver

状态：已完成  
输入：`TRIAL_K_CONTEXT_PACK_CN.md`  
目标：评估 resolver 是否足以为后续 scheduler / runner façade 提供稳定的 typed input bundle。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| K1 | `autonomous_flow_resolver.py`、`test_autonomous_flow_resolver.py`、本评估文件 | 实现只读 runner input resolver |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| Resolver 合同符合度 | 35 |
| Missing ref / fail-closed 语义 | 25 |
| 测试覆盖 | 25 |
| 副作用控制 | 15 |

自动重跑阈值：

- 总分低于 85。
- resolver 写 artifact、读 DB、读网络、调用 LLM 或读取当前时间。
- 缺 cycle 不 fail-closed。
- ref 指向缺失 artifact 时被静默忽略。
- projection ref 解析不稳定。
- focused tests 失败。

## 3. K1 结果

完成。

- 新增 `Phase5RunnerInputBundle` 和 `resolve_phase5_runner_inputs(...)`。
- resolver 只通过 artifact store 的 read-if-exists 函数读取 `phase5_cycle_ledger`、`phase5_gate_readout`、`phase5_recovery_ticket`、`frontend_projection_manifest`。
- 缺 `phase5_cycle_ledger` 时抛出 `Phase5RunnerInputResolutionError`，不返回空 bundle。
- 默认选择最新 gate readout ref、最新 recovery ticket ref、`artifact_refs` 中倒序最新的 `frontend_projection_manifest:<projection_id>`。
- 显式 gate/recovery/projection id 优先于 cycle refs；同时兼容传入 `artifact_family:id` 形式。
- 缺 gate / projection artifact 返回 `None` 并记录 stable deduped `missing_refs`；无 recovery ref 返回 `None` 且不记 missing；存在 recovery ref 但 artifact 缺失时记录 missing。
- resolver 不写 artifact、不读 DB、不读网络、不调用 LLM、不读取当前时间。
- 主进程补强：resolver 读到的 gate / recovery / projection artifact 如果 `cycle_id` 与请求 cycle 不一致，必须 fail-closed，避免后续 scheduler 混用跨 cycle 事实。

K1 本地验收：

- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_resolver.py -q`：9 passed
- `ruff check src/ashare_evidence/autonomous_flow_resolver.py tests/test_autonomous_flow_resolver.py`：passed
- `git diff --check`：passed

## 4. 主进程验证

主进程复核结论：通过。

跑偏检查：

- resolver 只读 artifact store 的 typed read-if-exists 函数，没有写 artifact。
- 没有接入 runner、planner、closeout、LaunchAgent、DB、网络、LLM、API 或前端。
- 缺 cycle fail-closed；缺 gate/projection 保留为 `None` 并进入 `missing_refs`，交由 planner 保守降级。
- projection ref 使用倒序选择最新 `frontend_projection_manifest:<id>`，显式 id 优先。
- 主进程发现并修正一个基座风险：ref 解析出的 gate / recovery / projection artifact 如果属于另一个 cycle，现在会 fail-closed，避免 scheduler 混用跨 cycle 事实。

主进程门禁：

| 命令 | 结果 |
| --- | --- |
| `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_resolver.py -q` | 9 passed |
| `ruff check src/ashare_evidence/autonomous_flow_resolver.py tests/test_autonomous_flow_resolver.py` | pass |
| `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_K_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_K_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated` | status=pass, issue_count=0 |
| `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage` | pass |
| `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow.py tests/test_autonomous_flow_artifacts.py tests/test_autonomous_flow_closeout.py tests/test_autonomous_flow_planner.py tests/test_autonomous_flow_runner.py tests/test_autonomous_flow_resolver.py -q` | 45 passed |
| `git diff --check` | pass |
| `PYTHONPATH=src python3 -m pytest -q` | 274 passed, 147 deselected |

运行时发布验证：本轮只新增只读 resolver 和测试，不改变用户可见 Web/runtime 行为，因此不触发发布或浏览器验收。

## 5. 重跑记录

无需重跑子进程。

主进程做了一次小范围补强：

- 增加 gate / recovery / projection artifact 的 `cycle_id` 一致性检查。
- 增加跨 cycle artifact fail-closed 测试。
- 同步更新 Context Pack 和本评估记录。

原因：

- K1 输出总体满足 Context Pack 的 owned files 和非目标边界。
- 补强属于同一 resolver 设计边界内的 fail-closed 语义，不需要重跑子进程。

## 6. 自评

K1 自评：94 / 100。

- Resolver 合同符合度：34 / 35。已覆盖默认选择、显式覆盖、typed bundle 和只读 store 读取；未接入 runner façade，符合本轮非目标。
- Missing ref / fail-closed 语义：25 / 25。缺 cycle fail-closed；缺 gate/projection 进入 `missing_refs`；recovery 无 ref 不误报；已对缺失 artifact 去重。
- 测试覆盖：23 / 25。focused tests 覆盖 Context Pack 要求的主要路径和无写入断言；后续可由主进程追加跨 runner façade 的集成测试，但本轮边界不要求。
- 副作用控制：12 / 15。resolver 代码路径无写入、无 DB、无网络、无 LLM、无时间读取；测试通过 before/after 文件集确认 resolver 调用不新增 artifact。

风险 / 后续边界：

- `missing_refs` 对没有可用 id 的 gate/projection 使用 `<missing>` 占位，后续 scheduler 如需机器可解析的 structured missing reason，可在 planner/runner 合同层另行扩展。
- 主进程已补齐跨 artifact `cycle_id` 一致性 fail-closed 校验，该风险不再留到后续 scheduler。
