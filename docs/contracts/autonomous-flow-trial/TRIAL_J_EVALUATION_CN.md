# Trial J 评估记录：Phase 5 本地 Runner Façade

状态：已完成  
输入：`TRIAL_J_CONTEXT_PACK_CN.md`  
目标：评估本地 runner façade 是否足以作为后续 scheduler 的稳定调用入口。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| J1 | `autonomous_flow_runner.py`、`test_autonomous_flow_runner.py`、本评估文件 | 实现本地 runner façade |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| Façade 合同符合度 | 35 |
| Closeout 应用安全性 | 25 |
| 测试覆盖 | 25 |
| 副作用控制 | 15 |

自动重跑阈值：

- 总分低于 85。
- façade 内部读取当前时间、DB、网络、文件或 LLM。
- dry run 仍写 artifact。
- apply closeout 缺 `finished_at` 时自动取当前时间。
- planner `completed + continue_tracking` 被直接非法传给 closeout。
- focused tests 失败。

## 3. J1 结果

J1 已实现 Phase 5 本地 runner façade：

- 新增 `src/ashare_evidence/autonomous_flow_runner.py`，暴露 `Phase5RunnerResult` 与 `run_phase5_local_cycle_step(...)`。
- façade 只接收调用方传入的 typed artifacts，先调用 `plan_phase5_next_step(...)` 得到并保留 planner decision。
- `apply_closeout=False` 时只返回 decision，`closeout_applied=False`，`skipped_reason="closeout_not_requested"`，不调用 closeout，也不写 artifact。
- `apply_closeout=True` 时要求调用方显式传入 `finished_at`；缺失时 fail-closed，且不调用 `finish_phase5_cycle(...)`。
- closeout 应用只使用 planner decision 的 `closeout_status` 与 `next_action`；对 planner 的 `completed + continue_tracking` 保守转换为 closeout 的 `degraded + continue_tracking`，避免向 closeout 传入非法组合，同时保留原始 planner decision 供审计。
- façade 本身不读取 DB、网络、文件、当前时间或 LLM；唯一写入路径是 `apply_closeout=True` 时调用既有 `finish_phase5_cycle(...)`。

J1 focused tests 覆盖：

- dry run 只返回 decision，不调用 closeout，不写 artifact。
- apply closeout 写回 cycle closeout，并保留 planner decision。
- apply closeout 缺 `finished_at` 失败且不写 artifact。
- blocker planner 输出 closeout 为 `blocked`。
- stale projection planner 输出 closeout 为 `degraded + rebuild_projection`。
- planner `completed + continue_tracking` 经 façade 转换为合法 closeout。
- façade 不修改输入 typed artifact 对象。

J1 本地验收：

| 命令 | 结果 |
| --- | --- |
| `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_runner.py -q` | 6 passed |
| `ruff check src/ashare_evidence/autonomous_flow_runner.py tests/test_autonomous_flow_runner.py` | pass |
| `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_J_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_J_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated` | pass, issue_count=0 |
| `git diff --check` | pass |

## 4. 主进程验证

主进程复核结论：通过。

跑偏检查：

- 没有接入 LaunchAgent、cron、heartbeat 或真实 scheduler。
- 没有读取 artifact store 自动查找输入；所有 gate/recovery/projection 仍由调用方显式传入。
- dry run 不写 artifact，并通过 monkeypatch 确认不调用 `finish_phase5_cycle(...)`。
- `apply_closeout=True` 缺 `finished_at` 时 fail-closed，不读取当前时间。
- `completed + continue_tracking` 没有被直接传给 closeout，而是保守转换为 `degraded + continue_tracking`，保留原始 planner decision 供审计。
- 未修改 planner、closeout、artifact model、store、registry、API 或前端。

主进程门禁：

| 命令 | 结果 |
| --- | --- |
| `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_runner.py -q` | 6 passed |
| `ruff check src/ashare_evidence/autonomous_flow_runner.py tests/test_autonomous_flow_runner.py` | pass |
| `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_J_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_J_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated` | status=pass, issue_count=0 |
| `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage` | pass |
| `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow.py tests/test_autonomous_flow_artifacts.py tests/test_autonomous_flow_closeout.py tests/test_autonomous_flow_planner.py tests/test_autonomous_flow_runner.py -q` | 36 passed |
| `git diff --check` | pass |
| `PYTHONPATH=src python3 -m pytest -q` | 265 passed, 147 deselected |

运行时发布验证：本轮只新增本地 runner façade 和测试，不改变用户可见 Web/runtime 行为，因此不触发发布或浏览器验收。

## 5. 重跑记录

无需重跑子进程。

原因：

- J1 输出满足 Context Pack 的 owned files 和非目标边界。
- 未发现 dry run 写入、timestamp 自动读取、非法 closeout 组合、调度越界或副作用越界。
- 后续真实 scheduler、LaunchAgent、API / SPA、publish verifier 接入继续留在后续轮次。

## 6. 自评

J1 自评：

- Façade 合同符合度：34/35。入口、输入、输出和 planner decision 保留符合 Context Pack；`skipped_reason` 使用固定字符串表达 dry run closeout 未请求。
- Closeout 应用安全性：25/25。`finished_at` 缺失 fail-closed；closeout 参数来自 planner decision；`completed + continue_tracking` 被保守转换为 `degraded + continue_tracking`。
- 测试覆盖：25/25。覆盖 dry run、apply、缺 timestamp、blocker、projection stale、非法组合规避和输入不可变。
- 副作用控制：15/15。runner 不含 artifact store 读取、DB、网络、时间或 LLM 依赖；dry run 通过 monkeypatch 防止 closeout 被调用并断言无 artifact 根目录。

总分：99/100。
