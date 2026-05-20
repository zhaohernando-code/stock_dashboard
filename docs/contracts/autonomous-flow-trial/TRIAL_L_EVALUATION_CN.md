# Trial L 评估记录：Phase 5 本地 Cycle Service

状态：已完成  
输入：`TRIAL_L_CONTEXT_PACK_CN.md`  
目标：评估本地 cycle service 是否足以作为后续真实 scheduler 的单一调用入口。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| L1 | `autonomous_flow_service.py`、`test_autonomous_flow_service.py`、本评估文件 | 实现本地 cycle service |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| Service 合同符合度 | 35 |
| 组合路径安全性 | 25 |
| 测试覆盖 | 25 |
| 副作用控制 | 15 |

自动重跑阈值：

- 总分低于 85。
- service 直接读写 artifact store，绕过 resolver / runner。
- dry run 写 artifact。
- closeout 缺 `finished_at` 自动取当前时间。
- resolver fail-closed 错误被吞掉。
- service 读 DB、网络、调用 LLM 或读取当前时间。
- focused tests 失败。

## 3. L1 结果

实现状态：完成本地 `run_phase5_local_cycle_service(...)` 薄组合入口。

- 新增 `Phase5LocalCycleServiceResult` typed result，返回 `cycle_id`、resolver 的 `input_bundle`、runner façade 的 `runner_result` 与 `missing_refs`。
- service 只调用 `resolve_phase5_runner_inputs(...)` 读取 typed input bundle，不直接读写 artifact store。
- service 只调用 `run_phase5_local_cycle_step(...)` 执行 planner/可选 closeout，不绕过 runner façade。
- `apply_closeout=False` 为默认 dry run；focused test 覆盖 dry run 不写 closeout。
- `apply_closeout=True` 且 `finished_at` 缺失在 service 层 fail-closed，不解析输入、不写 closeout、不读取当前时间。
- explicit `gate_id` / `recovery_ticket_id` / `projection_id` 会传递给 resolver 覆盖 cycle refs。
- resolver 的 missing cycle / cycle mismatch 等错误不捕获、不吞掉，原样透出。

本轮未修改 resolver、runner、planner、closeout、artifact store、artifact model、registry、API、前端、scheduler、LaunchAgent 或数据库表。

## 4. 主进程验证

主进程复核结论：通过。

跑偏检查：

- service 模块没有直接 import artifact store，也没有直接调用 planner / closeout。
- 调用路径固定为 resolver -> runner façade，测试通过 monkeypatch 验证。
- dry run 不写 closeout，`apply_closeout=True` 缺 `finished_at` 在 resolver 之前 fail-closed。
- resolver 的 missing cycle / cycle mismatch 错误不吞掉。
- 没有接入 LaunchAgent、cron、heartbeat、DB、网络、LLM、API、前端或 runtime 发布。

主进程门禁：

| 命令 | 结果 |
| --- | --- |
| `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_service.py -q` | 7 passed |
| `ruff check src/ashare_evidence/autonomous_flow_service.py tests/test_autonomous_flow_service.py` | pass |
| `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_L_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_L_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated` | status=pass, issue_count=0 |
| `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage` | pass |
| `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow.py tests/test_autonomous_flow_artifacts.py tests/test_autonomous_flow_closeout.py tests/test_autonomous_flow_planner.py tests/test_autonomous_flow_runner.py tests/test_autonomous_flow_resolver.py tests/test_autonomous_flow_service.py -q` | 52 passed |
| `git diff --check` | pass |
| `PYTHONPATH=src python3 -m pytest -q` | 281 passed, 147 deselected |

运行时发布验证：本轮只新增本地 cycle service 和测试，不改变用户可见 Web/runtime 行为，因此不触发发布或浏览器验收。

## 5. 重跑记录

无需重跑子进程。

原因：

- L1 输出满足 Context Pack 的 owned files 和非目标边界。
- 未发现绕过 resolver/runner、dry run 写入、timestamp 自动读取、错误吞掉或副作用越界。
- 后续真实 scheduler、LaunchAgent、API / SPA、publish verifier 接入继续留在后续轮次。

## 6. 自评

L1 自评分：95 / 100。

- Service 合同符合度：34 / 35。入口参数、typed result、missing refs、dry run 和 closeout 显式时间要求均覆盖；未新增 scheduler/runtime 语义。
- 组合路径安全性：25 / 25。service 不直接 import artifact store，不直接调用 planner/closeout，调用路径由测试 monkeypatch 验证为 resolver -> runner。
- 测试覆盖：24 / 25。覆盖 dry run、apply closeout、missing cycle、missing refs 降级、explicit ids、缺 `finished_at` fail-closed、resolver/runner 调用路径；剩余风险是未在 service focused tests 中重复覆盖 resolver 的 cycle mismatch 细节，交由 resolver tests 覆盖。
- 副作用控制：12 / 15。dry run 与缺 `finished_at` 均无写入；apply closeout 仅经 runner façade 写 cycle closeout。按任务边界未启动服务、未发布 runtime、未访问 DB/网络/LLM/当前时间。
