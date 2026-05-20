# Trial N 评估记录：Phase 5 本地 Status Projection

状态：进行中  
输入：`TRIAL_N_CONTEXT_PACK_CN.md`  
目标：评估本地 status projection 是否能作为后续 scheduler 日志、CLI 输出收口和未来中台/API 的稳定小 payload。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| N1 | `autonomous_flow_status.py`、`test_autonomous_flow_status.py`、本评估文件 | 实现本地 status projection |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| Projection 合同符合度 | 35 |
| 保守状态汇总 | 25 |
| 测试覆盖 | 25 |
| 副作用控制 | 15 |

自动重跑阈值：

- 总分低于 85。
- projection 读写文件、读 DB、读网络、调用 LLM 或读取当前时间。
- missing refs 仍输出 completed summary。
- blocked decision 没有输出 blocked summary。
- 输出包含完整 input bundle、artifact payload 或 release manifest 明细。
- focused tests 失败。

## 3. N1 结果

实现完成：

- 新增 `Phase5LocalCycleStatusProjection` 与 `project_phase5_local_cycle_status(...)`。
- 输入仅接受已构造的 `Phase5LocalCycleServiceResult`，投影逻辑不读写文件、不读 DB、不读网络、不调用 LLM、不读取当前时间。
- 输出字段覆盖 cycle id/status、planner decision status、next action、claim ceiling、decision reason、missing refs、blocking reasons、source refs、closeout applied、finished_at、publish verification status、projection staleness status、summary status。
- `summary_status` 采用保守汇总：blocked 优先，其次 degraded，最后 completed；missing refs 非空、publish verification missing、projection missing/stale/degraded 均至少 degraded。
- `publish_verification_status` 只输出 `present` / `missing` / `not_required`，不输出 release manifest ref、digest 或 verification 明细。
- focused tests 覆盖 dry-run completed、degraded decision、blocked decision、missing refs、publish verification missing、closeout finished_at、小 JSON payload、输入不变性。

## 4. 主进程验证

主进程复核结论：通过。

已验证：

- `project_phase5_local_cycle_status(...)` 是纯内存 projection，不读写文件、不读 DB、不读网络、不调用 LLM、不读取当前时间。
- 输出为小 payload；JSON 中未包含 `input_bundle`、`runner_result`、projection artifact 明细、release manifest ref 或 digest。
- `summary_status` 保持保守汇总：blocked 优先，其次 degraded，最后 completed。
- `missing_refs` 非空、projection manifest missing/stale/degraded、publish verification missing 均不会输出 completed summary。
- `source_refs`、`missing_refs`、`blocking_reasons` 稳定去重，且不会修改输入对象。
- 本轮未接入 CLI/API/scheduler/frontend，符合 Context Pack 非目标。

跑偏检查：

- 未把状态 projection 做成新的 artifact family。
- 未新增 registry id。
- 未把 service/resolver/runner/planner 的内部嵌套结构暴露给未来 UI。
- 当前 `publish_verification_status=missing` 仍基于 planner blocking reason 的稳定短语判断；这是本轮可接受的最小实现，但后续如果 planner 输出结构化 publish gate，应替换为结构化字段判断。

主进程已执行：

- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_status.py -q`
- `ruff check src/ashare_evidence/autonomous_flow_status.py tests/test_autonomous_flow_status.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_N_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_N_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
- `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow.py tests/test_autonomous_flow_service.py tests/test_autonomous_flow_resolver.py tests/test_autonomous_flow_runner.py tests/test_autonomous_flow_planner.py tests/test_autonomous_flow_status.py -q`
- `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage`
- `PYTHONPATH=src python3 -m pytest -q`

结果：

- Focused status tests：9 passed。
- 自治流程组合测试：47 passed。
- Contract registry check：pass，issue_count=0。
- Policy audit：pass。
- Full regression：296 passed，147 deselected。
- Diff whitespace check：pass。

## 5. 重跑记录

无需重跑。N1 首轮输出达到阈值。

## 6. 自评

N1 自评：

| 维度 | 分数 | 说明 |
| --- | ---: | --- |
| Projection 合同符合度 | 34/35 | 字段和小 payload 边界满足 Context Pack；未接入 CLI/API，符合本轮非目标。 |
| 保守状态汇总 | 25/25 | blocked > degraded > completed；missing refs 不会输出 completed summary。 |
| 测试覆盖 | 25/25 | 覆盖 Context Pack 要求的核心分支和非变异约束。 |
| 副作用控制 | 15/15 | projection 纯内存计算，无外部 IO、DB、网络、LLM 或时间读取。 |

合计：99/100。剩余风险：后续若 service/runner/planner 字段命名变化，需要同步 projection typed aliases 和测试 fixture。
