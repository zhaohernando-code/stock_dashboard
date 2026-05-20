# Trial BG 评估记录：Action Route Auto Apply CLI Smoke

状态：verified
输入：`TRIAL_BG_CONTEXT_PACK_CN.md`
目标：评估 auto apply CLI 在真实 artifact root 下是否稳定 skipped、写入 route-selected durable output，并在缺参时 fail closed。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| BG1 | auto apply smoke 测试、本评估文件 | 固化真实 CLI artifact root 烟测 | rejected |
| BG2 | auto apply smoke 测试、本评估文件 | 按真实 route contract 重跑 smoke | pass |
| BG3 | auto apply smoke 测试、本评估文件 | 解耦 deterministic ID digest 细节 | pass |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 真实 CLI artifact root 覆盖 | 35 |
| skipped/write/fail-closed 三路径语义 | 35 |
| 无数据库初始化与无嵌套 payload 泄漏 | 15 |
| 文件规模与门禁 | 15 |

自动重跑阈值：

- smoke 测试只 mock handler，没有调用真实 `cli.main([...])`。
- 缺参路径写 artifact 或返回 0。
- missing cycle recovery path 没有真实写入 route-selected durable output。
- happy path 新增不应有的 diagnostic/execution artifact。
- 修改生产代码但没有在评估文档说明真实缺陷。
- 解析或匹配 `reason` 自然语言文案来改变 route type。
- focused tests、ruff、process hardening、registry 或 full regression 失败。

## 3. BG1 结果

BG1 功能上跑通，但主进程审查后不合入：

- 优点：新增真实 `cli.main([...])` smoke，覆盖 happy/fail-closed，并证明真实 artifact root 可以触发 durable write。
- 问题：为了让 missing cycle recovery path 写 execution ledger，BG1 修改生产代码，在 auto apply core 中匹配 `route.reason == "scheduler action preflight blocked by missing inputs"` 后强行把 diagnostic route 改为 execution route。
- 结论：该做法违反“不解析自然语言 reason”和“不为了测试预设改写 route contract”的流程约束。已撤回生产改动，重跑 BG2；BG2 必须尊重真实 route contract，missing cycle 当前应验证 scheduler diagnostic 写入。

## 4. 主进程验证

BG1 子进程自报验证通过，但因设计评价未达标，不作为可合入结果。

BG2 子进程验证通过，未修改 production code：

- Focused tests：`PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_action_route_auto_apply_smoke.py tests/test_cli_autonomous_flow_action_route_auto_apply_output.py tests/test_autonomous_flow_scheduler_action_route_auto_apply.py -q` -> 15 passed。
- Ruff：`ruff check tests/test_cli_autonomous_flow_action_route_auto_apply_smoke.py` -> All checks passed。
- Process hardening：`PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check ...` -> pass，`test_cli_autonomous_flow_action_route_auto_apply_smoke.py` 160 行，低于 190 warning / 220 hard。
- Registry：`PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check ...` -> pass，issue_count=0。
- Full regression：`PYTHONPATH=src python3 -m pytest -q` -> 490 passed，147 deselected。

BG3 子进程修正通过，未修改 production code：

- Recovery path 不再断言 `diagnostic_id` 的完整 digest，只断言稳定语义前缀 `diagnostic-cycle-missing-auto-apply-smoke-open_recovery_ticket-attempt-recovery-smoke-`。
- Recovery path 继续使用 payload 返回的 `diagnostic_id` 读取 scheduler diagnostic artifact，并验证 artifact 内容。
- Missing cycle route contract 保持不变：仍验证 `diagnostic_output` 与 scheduler diagnostic durable write，不写 execution ledger。
- Focused tests：`PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow_action_route_auto_apply_smoke.py tests/test_cli_autonomous_flow_action_route_auto_apply_output.py tests/test_autonomous_flow_scheduler_action_route_auto_apply.py -q` -> 15 passed。
- Ruff：`ruff check tests/test_cli_autonomous_flow_action_route_auto_apply_smoke.py` -> All checks passed。
- Process hardening：`PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check ...` -> pass，`test_cli_autonomous_flow_action_route_auto_apply_smoke.py` 160 行，低于 190 warning / 220 hard。
- Registry：`PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check ...` -> pass，issue_count=0。
- Full regression：`PYTHONPATH=src python3 -m pytest -q` -> 490 passed，147 deselected。

主进程合入 BG3 产物后完成以下复验：

- focused tests：`15 passed in 0.62s`。
- ruff：`All checks passed!`。
- process hardening：`status=pass`，`issue_count=0`。
- registry check：`status=pass`，`issue_count=0`。
- full regression：`490 passed, 147 deselected in 20.85s`。

## 5. 重跑记录

- BG1 rejected：通过匹配 `route.reason` 自然语言改写 route type，设计收敛不足且脆弱。
- BG2 rerun：重写 `tests/test_cli_autonomous_flow_action_route_auto_apply_smoke.py` 的 missing cycle path，按真实 route contract 断言 `diagnostic_output`、确定性 `diagnostic_id`、`applied_output=diagnostic`、`cycle_event_recorded=false`，并确认不写 execution ledger。
- BG3 rerun：将 missing cycle path 的 `diagnostic_id` 断言从完整 digest 改为语义前缀，保留 payload ID 读取 artifact 的端到端验证，避免 smoke 绑定 ID 算法实现细节。

## 6. 自评

BG3 后本轮已证明：真实 CLI smoke 尊重 route contract，不改生产代码，不解析 reason，并覆盖 skipped/diagnostic-write/fail-closed 三路径，同时不耦合 deterministic ID 的完整 digest。

- Happy path：完整 cycle/gate/projection fixture 下，`continue_tracking` 真实链路返回 skipped/no-op，不新增 scheduler diagnostic 或 execution ledger，不触发 DB 初始化，不泄漏嵌套 payload。
- Recovery path：缺失 cycle 下，真实链路写 scheduler diagnostic，输出包含具备稳定语义前缀的 `diagnostic_id`、`applied_output=diagnostic`、`cycle_event_recorded=false`，且不写 execution ledger。
- Fail-closed path：缺 `attempt_id` 或 `issued_at` 时返回 blocked JSON，不写 artifact，不触发 DB 初始化。
- 残余风险：未发现新增残余风险；若后续正式调整 `diagnostic_id` 的语义字段组成，应同步更新 contract 或测试期望。
