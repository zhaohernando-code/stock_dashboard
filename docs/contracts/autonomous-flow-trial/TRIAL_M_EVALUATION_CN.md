# Trial M 评估记录：Phase 5 本地 Cycle Service CLI

状态：已完成  
输入：`TRIAL_M_CONTEXT_PACK_CN.md`  
目标：评估 CLI 门面是否足以作为后续真实 scheduler 的手动/脚本调用入口。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| M1 | `cli_autonomous_flow.py`、`cli.py`、`test_cli_autonomous_flow.py`、本评估文件 | 实现本地 cycle service CLI |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| CLI 合同符合度 | 35 |
| DB / 调度副作用隔离 | 25 |
| 测试覆盖 | 25 |
| 错误输出与可运维性 | 15 |

自动重跑阈值：

- 总分低于 85。
- CLI 触发 DB 初始化。
- CLI 直接读写 artifact store，绕过 service。
- dry run 写 closeout。
- 缺 `--finished-at` 自动读取当前时间。
- focused tests 失败。

## 3. M1 结果

- 新增 `phase5-local-cycle-step` CLI 门面，参数覆盖 `--cycle-id`、`--artifact-root`、`--gate-id`、`--recovery-ticket-id`、`--projection-id`、`--finished-at`、`--apply-closeout`、`--require-publish-verification`。
- `cli_autonomous_flow.py` 承担参数 handler 与 JSON 输出；handler 仅调用 `run_phase5_local_cycle_service(...)`，不直接读写 artifact store，不读取当前时间。
- `cli.py` 仅 import、parser 注册和 command dispatch；`phase5-local-cycle-step` 在 `_should_initialize_database(...)` 与 `init_database(...)` 之前返回，避免 artifact-only 命令触发 DB 初始化。
- 默认 dry run 传递 `apply_closeout=False` 与 `finished_at=None`；显式 `--apply-closeout` 时仍由 service 对缺失 `--finished-at` fail-closed。
- 错误路径返回非零并输出结构化 JSON：`status`、`command`、`error_type`、`message`。

## 4. 主进程验证

主进程复核结论：通过。

跑偏检查：

- `cli.py` 只增加 import、parser 注册和 command dispatch，没有塞业务逻辑。
- `phase5-local-cycle-step` 在 `_should_initialize_database(...)` / `init_database(...)` 之前 dispatch，artifact-only 命令不会触发 DB 初始化。
- handler 只调用 `run_phase5_local_cycle_service(...)`，不直接读写 artifact store。
- 默认 dry run；`--apply-closeout` 缺 `--finished-at` 不自动取当前时间，错误由 service fail-closed。
- 没有接入 LaunchAgent、cron、heartbeat、DB、网络、LLM、API、前端或 runtime 发布。

主进程门禁：

| 命令 | 结果 |
| --- | --- |
| `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow.py -q` | 6 passed |
| `ruff check src/ashare_evidence/cli_autonomous_flow.py src/ashare_evidence/cli.py tests/test_cli_autonomous_flow.py` | pass |
| `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_M_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_M_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated` | status=pass, issue_count=0 |
| `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage` | pass |
| `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow.py tests/test_autonomous_flow_service.py tests/test_autonomous_flow_resolver.py tests/test_autonomous_flow_runner.py tests/test_autonomous_flow_planner.py -q` | 38 passed |
| `git diff --check` | pass |
| `PYTHONPATH=src python3 -m pytest -q` | 287 passed, 147 deselected |

运行时发布验证：本轮只新增 CLI 门面和测试，不改变用户可见 Web/runtime 行为，因此不触发发布或浏览器验收。

## 5. 重跑记录

无需重跑子进程。

原因：

- M1 输出满足 Context Pack 的 owned files 和非目标边界。
- 未发现 DB 初始化误触发、绕过 service、dry run 写入、timestamp 自动读取或调度越界。
- 后续真实 scheduler、LaunchAgent、API / SPA、publish verifier 接入继续留在后续轮次。

## 6. 自评

M1 自评：93/100。

- CLI 合同符合度：33/35。命令与参数覆盖 Context Pack 要求，输出 service result JSON；`--cycle-id` 作为 service 必填参数暴露为 CLI 必填项。
- DB / 调度副作用隔离：25/25。未接 scheduler、LaunchAgent、网络或 DB；`cli.py` 早期 dispatch 已覆盖 `cli.main(...)` 不触发 `init_database` 的测试。
- 测试覆盖：24/25。覆盖 parser 注册、dry run 默认、apply closeout 参数、`artifact-root` Path 传递、错误 JSON、主入口 DB 初始化隔离。
- 错误输出与可运维性：11/15。当前输出可读结构化错误 JSON；后续如需多错误分类或 stderr/stdout 约定，可由真实 scheduler 接入时再细化。
