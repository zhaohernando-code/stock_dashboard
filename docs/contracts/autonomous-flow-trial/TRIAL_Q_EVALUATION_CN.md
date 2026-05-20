# Trial Q 评估记录：Phase 5 CLI Tick Envelope

状态：进行中  
输入：`TRIAL_Q_CONTEXT_PACK_CN.md`  
目标：评估 CLI 默认路径是否已复用 tick envelope，并保留 `--output full` 的完整 service result 调试能力。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| Q1 | `cli_autonomous_flow.py`、`test_cli_autonomous_flow.py`、本评估文件 | 将 CLI 默认路径切到 tick envelope |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| CLI 默认 tick 合同符合度 | 35 |
| 调试兼容与异常边界 | 25 |
| 副作用隔离 | 20 |
| 测试覆盖 | 20 |

自动重跑阈值：

- 总分低于 85。
- 默认路径仍直接调用 service 或 status projection。
- 默认失败路径仍由 CLI 手写异常 JSON 输出。
- 默认输出泄露完整 input bundle、runner result、release manifest ref 或 digest。
- `--output full` 丢失完整 service result 调试能力。
- CLI 触发 DB 初始化。
- focused tests 失败。

## 3. Q1 结果

完成。

改动文件：

- `src/ashare_evidence/cli_autonomous_flow.py`
- `tests/test_cli_autonomous_flow.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_Q_EVALUATION_CN.md`

实现结果：

- `phase5-local-cycle-step` 默认 `--output status` 路径改为调用 `run_phase5_local_cycle_tick(...)`。
- 默认路径输出 `Phase5LocalCycleTickResult.model_dump(mode="json")`，并返回 `tick_result.exit_code`。
- 默认路径不再直接调用 `run_phase5_local_cycle_service(...)` 或 `project_phase5_local_cycle_status(...)`。
- 默认失败输出由 tick envelope 提供，不走 CLI 手写异常 JSON。
- `--output full` 保留完整 service result 调试输出，并且不调用 tick。
- `--output full` 的 service 异常仍保留 CLI 手写错误 JSON，限定在调试路径。

验证结果：

- `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow.py tests/test_autonomous_flow_tick.py -q`：13 passed
- `ruff check src/ashare_evidence/cli_autonomous_flow.py tests/test_cli_autonomous_flow.py`：passed
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_Q_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_Q_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`：passed，`issue_count=0`
- `git diff --check`：passed

## 4. 主进程验证

主进程复核结论：通过。

已验证：

- 默认 `--output status` 路径只调用 `run_phase5_local_cycle_tick(...)`，不直接调用 service 或 status projection。
- 默认路径参数完整透传给 tick，并使用 `tick_result.exit_code` 作为 CLI 返回码。
- 默认成功输出为 tick envelope，顶层包含 `tick_status`、`exit_code`、`status`、`error`、`recommended_next_action`、`summary_status`。
- 默认失败输出来自 tick envelope；CLI 手写异常 JSON 只保留在 `--output full` 调试路径。
- `--output full` 保留完整 service result 输出，并且不调用 tick。
- `cli.main(["phase5-local-cycle-step", ...])` 仍不触发 DB 初始化。

跑偏检查：

- 本轮只修改 CLI 默认入口和对应测试；未修改 tick、service、resolver、runner、planner、status projection、artifact model、registry、API 或 frontend。
- 没有接入 LaunchAgent、cron、heartbeat 或真实 scheduler。
- 没有把 `--output full` 伪装成生产路径；默认路径已经以 tick contract 为准。
- 修正了 CLI help 文案，使其表达 tick status envelope，而不是旧的 status projection。

主进程门禁：

| 命令 | 结果 |
| --- | --- |
| `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow.py tests/test_autonomous_flow_tick.py -q` | 13 passed |
| `ruff check src/ashare_evidence/cli_autonomous_flow.py tests/test_cli_autonomous_flow.py` | pass |
| `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_Q_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_Q_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated` | status=pass, issue_count=0 |
| `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow.py tests/test_autonomous_flow_service.py tests/test_autonomous_flow_resolver.py tests/test_autonomous_flow_runner.py tests/test_autonomous_flow_planner.py tests/test_autonomous_flow_status.py tests/test_autonomous_flow_tick.py -q` | 54 passed |
| `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage` | pass |
| `git diff --check` | pass |
| `PYTHONPATH=src python3 -m pytest -q` | 303 passed, 147 deselected |

运行时发布验证：本轮只改变本地 CLI 默认输出路径，不改变用户可见 Web/runtime 行为，因此不触发发布或浏览器验收。

## 5. 重跑记录

无需重跑子进程。

原因：

- Q1 输出满足 Context Pack 的 owned files 与非目标边界。
- 未发现默认路径旁路 tick、调试模式丢失、DB 初始化误触发或输出泄露问题。
- 主进程只补了 CLI help 文案，使默认输出说明与 tick envelope 现实一致。

## 6. 自评

评分：94 / 100。

- CLI 默认 tick 合同符合度：35 / 35。默认路径只调用 tick，输出 tick envelope，退出码来自 tick result。
- 调试兼容与异常边界：24 / 25。`--output full` 保留完整 service result 与 CLI 调试错误 JSON；默认路径 tick 自身若发生未捕获框架级异常仍可能冒泡，但 Trial P tick 已覆盖主要失败类型。
- 副作用隔离：20 / 20。handler 只做参数透传与 JSON 输出，不直接读写 artifact store、不读 DB、不读网络、不调用 LLM、不读取当前时间。
- 测试覆盖：15 / 20。覆盖默认 parser、tick/service 分流、参数透传、tick exit_code、默认错误 envelope、full 调试输出、full 异常和 DB 初始化保护；未跑全量回归，交由主进程门禁补充。

剩余风险：

- CLI focused tests 使用 monkeypatch 隔离 tick，真实 tick envelope 字段完整性由 `tests/test_autonomous_flow_tick.py` 负责。
- 后续若 tick result 字段发生合同变化，CLI 默认输出会自然跟随 tick，但脚本消费者需要以 tick contract 为准。
