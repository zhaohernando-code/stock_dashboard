# Trial U 评估记录：Phase 5 CLI Follow-up Plan Output

状态：进行中  
输入：`TRIAL_U_CONTEXT_PACK_CN.md`  
目标：评估 CLI 是否能显式输出 scheduler follow-up plan，同时保持默认 tick envelope 与 full 调试路径稳定。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| U1 | CLI、CLI tests、smoke tests、本评估文件 | 增加 `--output plan` |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| CLI plan 合同符合度 | 35 |
| 兼容性 | 25 |
| 输出泄露保护 | 20 |
| 测试覆盖 | 20 |

自动重跑阈值：

- 总分低于 85。
- 默认 `status` 行为或 exit code 语义被改变。
- `--output plan` 直接调用 service 或 status projection。
- `--output plan` 返回 tick error code，而不是计划生成成功的 0。
- `--output full` 丢失完整 service result 调试能力。
- plan 输出泄露 nested tick payload、release manifest ref 或 digest。
- focused tests 失败。

## 3. U1 结果

结论：通过。

改动范围：

- `src/ashare_evidence/cli_autonomous_flow.py`
- `tests/test_cli_autonomous_flow.py`
- `tests/test_cli_autonomous_flow_smoke.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_U_EVALUATION_CN.md`

实现结果：

- `phase5-local-cycle-step --output` 扩展为 `status|plan|full`。
- 默认 `status` 行为不变：调用 `run_phase5_local_cycle_tick(...)`，输出 tick envelope，返回 tick exit code。
- 新增 `plan` 输出：调用 `run_phase5_local_cycle_tick(...)` 后调用 `plan_phase5_scheduler_followup(...)`，输出 scheduler follow-up plan JSON，返回 `0` 表示计划生成成功。
- `full` 行为不变：直接调用 `run_phase5_local_cycle_service(...)`，不调用 tick 或 follow-up planner。
- `plan` 输出不包含完整 tick `status` / `error`、`input_bundle`、`runner_result`、`release-manifest:`、`sha256:` 或 traceback。

验证结果：

- `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_smoke.py tests/test_autonomous_flow_scheduler_plan.py -q`：27 passed
- `ruff check src/ashare_evidence/cli_autonomous_flow.py tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_smoke.py`：passed
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_U_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_U_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`：passed，`issue_count=0`
- `git diff --check`：passed

## 4. 主进程验证

主进程复核结论：通过。

已验证：

- parser 支持 `--output status|plan|full`，默认仍是 `status`。
- `status` 路径行为不变：调用 tick，输出 tick envelope，返回 tick exit code。
- `plan` 路径只调用 tick 和 `plan_phase5_scheduler_followup(...)`，不直接调用 service 或 status projection。
- `plan` 路径对 error tick 仍返回 0，表示计划生成成功；后续语义由 `plan_status` 和 `action` 表达。
- `full` 路径行为不变：直接调用 service，输出完整 service result，并且不调用 tick/plan。
- 真实 artifact root smoke test 覆盖 `--output plan` happy path 和 missing cycle path。
- plan 输出不包含完整 tick `status` / `error`、`input_bundle`、`runner_result`、release manifest ref、digest 或 traceback。

跑偏检查：

- 本轮只扩展 CLI 输出形态和测试；未修改 tick、scheduler plan、service、resolver、runner、planner、status projection、artifact model、registry、API 或 frontend。
- 没有执行 scheduler plan，没有写 recovery ticket，没有修改 cycle closeout。
- 没有接入 LaunchAgent、cron、heartbeat 或真实 scheduler。
- `tests/test_cli_autonomous_flow.py` 已到 475 行，接近 500 行 pre-commit 风险线；后续 CLI 测试扩展应拆到新文件，不再继续堆在该文件中。

主进程门禁：

| 命令 | 结果 |
| --- | --- |
| `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_smoke.py tests/test_autonomous_flow_scheduler_plan.py -q` | 27 passed |
| `ruff check src/ashare_evidence/cli_autonomous_flow.py tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_smoke.py` | pass |
| `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_U_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_U_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated` | status=pass, issue_count=0 |
| `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow.py tests/test_cli_autonomous_flow_smoke.py tests/test_autonomous_flow_service.py tests/test_autonomous_flow_resolver.py tests/test_autonomous_flow_runner.py tests/test_autonomous_flow_planner.py tests/test_autonomous_flow_status.py tests/test_autonomous_flow_tick.py tests/test_autonomous_flow_scheduler_plan.py -q` | 77 passed |
| `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage` | pass |
| `git diff --check` | pass |
| `PYTHONPATH=src python3 -m pytest -q` | 326 passed, 147 deselected |

运行时发布验证：本轮只改变本地 CLI 输出形态，不改变用户可见 Web/runtime 行为，因此不触发发布或浏览器验收。

## 5. 重跑记录

无需重跑子进程。

原因：

- U1 输出满足 Context Pack 的 owned files 与非目标边界。
- 未发现三条输出路径串线、默认 exit code 语义改变、full 调试能力丢失或 plan 输出泄露问题。

## 6. 自评

评分：94/100。

- CLI plan 合同符合度：34/35。`plan` 明确经 tick 入口生成，不直接触达 service/status projection；返回码为 `0`。扣 1 分是因为 CLI 本身仍只负责生成 plan，不执行真实 scheduler，这符合本轮非目标但仍需后续闭环。
- 兼容性：25/25。默认 `status` 与 `full` 调试路径保持原语义。
- 输出泄露保护：19/20。单元测试与真实 artifact root 烟测覆盖了敏感字段 denylist；后续如果引入新的敏感 ref 类型，需要同步扩展检查。
- 测试覆盖：16/20。覆盖 parser、分流、参数透传、error tick、真实 artifact root happy/missing cycle；未覆盖 help 文案快照，当前风险较低。

剩余风险：本轮只增加 CLI plan 输出入口，不接 LaunchAgent/cron/heartbeat，不执行 follow-up plan；后续调度器接入时仍需要单独验证 retry/backoff、recovery ticket 写入和人工介入边界。
