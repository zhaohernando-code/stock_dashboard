# Trial R 评估记录：Phase 5 Structured Resolution Errors

状态：进行中  
输入：`TRIAL_R_CONTEXT_PACK_CN.md`  
目标：评估 resolver fail-closed 错误是否已经带结构化分类，并被 tick envelope 正确消费。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| R1 | resolver、tick、resolver/tick tests、本评估文件 | 增加 structured resolution error 并接入 tick |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| Structured error 合同符合度 | 35 |
| Tick 分类准确性 | 30 |
| 兼容性与副作用隔离 | 20 |
| 测试覆盖 | 15 |

自动重跑阈值：

- 总分低于 85。
- `Phase5RunnerInputResolutionError` 不再兼容 `ValueError`。
- tick 通过解析错误消息字符串判断分类。
- 缺 gate / projection 从 missing refs 变成抛异常。
- missing cycle 仍被 tick 映射成 blocked contract violation。
- cycle mismatch 没有映射成 blocked contract violation。
- focused tests 失败。

## 3. R1 结果

完成。

- resolver：`Phase5RunnerInputResolutionError` 继续继承 `ValueError`，新增 `failure_class`、`recommended_recovery_action`、`summary_status`、`recommended_next_action` 结构化字段。
- resolver：缺失必需 cycle ledger 映射为 `artifact-missing` / `open_recovery_ticket` / `degraded` / `retry_failed_step`。
- resolver：artifact cycle mismatch 保持 fail-closed，并通过默认字段映射为 `contract-violation` / `block_cycle` / `blocked` / `blocked`。
- tick：新增 `Phase5RunnerInputResolutionError` 专用捕获分支，直接读取结构化字段生成 envelope；普通 `ValueError` 仍保持 Trial P 的 blocked contract-violation 行为。
- tick：未解析错误消息字符串；错误输出仍走既有脱敏逻辑，不包含 traceback、input bundle、runner result、release manifest ref 或 digest。
- missing gate / projection 语义未改变，仍通过 `missing_refs` 返回，不抛异常。

已运行：

- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_resolver.py tests/test_autonomous_flow_tick.py -q`：18 passed
- `ruff check src/ashare_evidence/autonomous_flow_resolver.py src/ashare_evidence/autonomous_flow_tick.py tests/test_autonomous_flow_resolver.py tests/test_autonomous_flow_tick.py`：passed
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_R_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_R_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`：passed，`issue_count=0`
- `git diff --check`：passed

## 4. 主进程验证

主进程复核结论：通过。

已验证：

- `Phase5RunnerInputResolutionError` 仍继承 `ValueError`，service 现有 fail-closed 兼容性不破坏。
- resolver 缺失必需 cycle ledger 时输出结构化字段：`artifact-missing`、`open_recovery_ticket`、`degraded`、`retry_failed_step`。
- resolver artifact cycle mismatch 仍 fail-closed，并输出结构化字段：`contract-violation`、`block_cycle`、`blocked`、`blocked`。
- 缺 gate / projection / recovery artifact 的可降级路径仍返回 `missing_refs`，不改成抛异常。
- tick 捕获 `Phase5RunnerInputResolutionError` 时读取结构化字段，不解析错误消息字符串；测试里使用了误导性 message 来覆盖这一点。
- 普通 `ValueError` 仍保持 Trial P 行为：blocked contract-violation。
- tick 错误输出仍走脱敏逻辑，不包含 traceback、input bundle、runner result、release manifest ref 或 digest。

跑偏检查：

- 本轮未修改 CLI、service、runner、planner、status projection、artifact model、registry、API 或 frontend。
- 没有新增 artifact/event id，也没有引入隐藏持久化。
- 没有接入 LaunchAgent、cron、heartbeat 或真实 scheduler。
- 结构化字段目前是异常属性，不是独立模型；这对当前两类 resolver fail-closed 足够小。若后续 fail-closed 类型继续增长，应升级为显式错误模型，避免异常属性语义扩散。

主进程门禁：

| 命令 | 结果 |
| --- | --- |
| `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_resolver.py tests/test_autonomous_flow_tick.py -q` | 18 passed |
| `ruff check src/ashare_evidence/autonomous_flow_resolver.py src/ashare_evidence/autonomous_flow_tick.py tests/test_autonomous_flow_resolver.py tests/test_autonomous_flow_tick.py` | pass |
| `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_R_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_R_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated` | status=pass, issue_count=0 |
| `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow.py tests/test_autonomous_flow_service.py tests/test_autonomous_flow_resolver.py tests/test_autonomous_flow_runner.py tests/test_autonomous_flow_planner.py tests/test_autonomous_flow_status.py tests/test_autonomous_flow_tick.py -q` | 57 passed |
| `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage` | pass |
| `git diff --check` | pass |
| `PYTHONPATH=src python3 -m pytest -q` | 306 passed, 147 deselected |

运行时发布验证：本轮只改变本地 resolver/tick 错误分类，不改变用户可见 Web/runtime 行为，因此不触发发布或浏览器验收。

## 5. 重跑记录

无需重跑子进程。

原因：

- R1 输出满足 Context Pack 的 owned files 与非目标边界。
- 未发现字符串解析分类、missing refs 语义改变、兼容性破坏或副作用越界。

## 6. 自评

评分：94 / 100。

- Structured error 合同符合度：34 / 35。字段覆盖 Context Pack 要求，并保留 `ValueError` 兼容；当前字段作为异常属性而非独立模型，足够小，但后续如错误类型增多可再提升为显式模型。
- Tick 分类准确性：30 / 30。tick 对 resolver structured error 只读字段，不解析字符串；测试用误导性错误文本覆盖该约束。
- 兼容性与副作用隔离：20 / 20。未改 CLI、service、runner、planner、status projection、artifact model、registry、API、frontend；未新增 DB/网络/LLM/时间读取。
- 测试覆盖：10 / 15。覆盖 missing cycle、cycle mismatch、missing refs、真实 missing cycle tick、structured tick、普通 ValueError；未用真实 artifact mismatch 跑完整 tick 路径，原因是 resolver 层已覆盖 mismatch 字段，tick 层用 structured error 隔离验证分流合同。

剩余风险：

- `Phase5RunnerInputResolutionError` 的结构化字段目前由构造参数保证，未做运行时枚举校验；类型检查与测试覆盖当前使用点。
- 如果后续引入更多 resolver fail-closed 类型，应集中枚举并同步 tick failure class 合同，避免在异常属性上继续扩散字段含义。
