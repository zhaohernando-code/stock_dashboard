# Trial P 评估记录：Phase 5 Local Tick Envelope

状态：进行中  
输入：`TRIAL_P_CONTEXT_PACK_CN.md`  
目标：评估本地 tick envelope 是否能把一次 autonomous-flow service 调用稳定收口成可调度结果，并在失败时返回结构化错误而不是直接卡死。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| P1 | `autonomous_flow_tick.py`、`test_autonomous_flow_tick.py`、本评估文件 | 实现 local tick envelope |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| Tick 合同符合度 | 35 |
| 失败收口与不挂死能力 | 30 |
| 副作用隔离 | 20 |
| 测试覆盖 | 15 |

自动重跑阈值：

- 总分低于 85。
- wrapper 在预期异常路径继续向外抛异常。
- 失败输出包含 traceback、完整 input bundle、artifact payload、release manifest ref 或 digest。
- wrapper 直接读写 artifact store、读 DB、读网络、调用 LLM 或读取当前时间。
- wrapper 修改 service / runner / planner / resolver 行为。
- focused tests 失败。

## 3. P1 结果

完成。

实现文件：

- `src/ashare_evidence/autonomous_flow_tick.py`
- `tests/test_autonomous_flow_tick.py`

实现摘要：

- 新增 `Phase5LocalCycleTickError`、`Phase5LocalCycleTickResult`、`run_phase5_local_cycle_tick(...)`。
- 成功路径调用 `run_phase5_local_cycle_service(...)` 后再调用 `project_phase5_local_cycle_status(...)`，返回 `tick_status=ok`、`exit_code=0` 和 status projection 小 payload。
- 失败路径捕获 `FileNotFoundError`、`ValueError` 和其他异常，返回 typed error result，不继续向 scheduler 调用方抛异常。
- 失败分类采用短横线值：`artifact-missing`、`contract-violation`、`unexpected-error`。
- 错误消息只保留短消息，并对 `release-manifest:*` 与 `sha256:*` 形态做脱敏，避免 envelope 输出 release manifest ref 或 digest。
- wrapper 未直接读写 artifact store、未读 DB、未读网络、未调用 LLM、未读取当前时间，也未修改 service / resolver / runner / planner / status projection。

验证结果：

- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_tick.py tests/test_autonomous_flow_status.py -q`：15 passed
- `ruff check src/ashare_evidence/autonomous_flow_tick.py tests/test_autonomous_flow_tick.py`：passed
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_P_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_P_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`：passed，`issue_count=0`
- `git diff --check`：passed

## 4. 主进程验证

主进程复核结论：通过。

已验证：

- `run_phase5_local_cycle_tick(...)` 成功路径只组合 `run_phase5_local_cycle_service(...)` 与 `project_phase5_local_cycle_status(...)`。
- 成功 envelope 输出 `tick_status=ok`、`exit_code=0`、status projection、`recommended_next_action` 和 `summary_status`。
- 失败路径捕获 `FileNotFoundError`、`ValueError`、其他 `Exception`，返回 typed error result，不向调用方继续抛出。
- 失败 envelope 不包含 traceback、完整 input bundle、runner result、release manifest ref 或 digest；错误消息对 `release-manifest:*` 和 `sha256:*` 做脱敏。
- wrapper 没有直接读写 artifact store、读 DB、读网络、调用 LLM 或读取当前时间。
- 本轮未修改 CLI / service / resolver / runner / planner / status projection / artifact model / registry / API / frontend。

跑偏检查：

- 没有把 tick 做成新的 artifact family 或隐藏持久化状态。
- 没有接入 LaunchAgent、cron、heartbeat 或真实 scheduler。
- 没有在 wrapper 内做 retry/backoff；当前只提供后续 scheduler 可消费的 recommended recovery action。
- 现有 resolver 对缺失 cycle 的部分场景仍可能用 `ValueError` 表达，因此 tick 会按 `contract-violation` 处理；这不是本轮要解析字符串解决的问题，后续如需精细分类，应在 resolver/service 层引入结构化异常。

主进程门禁：

| 命令 | 结果 |
| --- | --- |
| `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_tick.py tests/test_autonomous_flow_status.py -q` | 15 passed |
| `ruff check src/ashare_evidence/autonomous_flow_tick.py tests/test_autonomous_flow_tick.py` | pass |
| `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_P_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_P_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated` | status=pass, issue_count=0 |
| `PYTHONPATH=src python3 -m pytest tests/test_cli_autonomous_flow.py tests/test_autonomous_flow_service.py tests/test_autonomous_flow_resolver.py tests/test_autonomous_flow_runner.py tests/test_autonomous_flow_planner.py tests/test_autonomous_flow_status.py tests/test_autonomous_flow_tick.py -q` | 54 passed |
| `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage` | pass |
| `git diff --check` | pass |
| `PYTHONPATH=src python3 -m pytest -q` | 303 passed, 147 deselected |

运行时发布验证：本轮只新增本地 tick wrapper，不改变用户可见 Web/runtime 行为，因此不触发发布或浏览器验收。

## 5. 重跑记录

无需重跑子进程。

原因：

- P1 输出满足 Context Pack 的 owned files 和非目标边界。
- 未发现异常继续外抛、输出泄露内部嵌套结构、隐藏持久化、调度越界或副作用越界。
- 后续 CLI/scheduler 接入应复用该 wrapper，避免继续在入口层手写错误收口。

## 6. 自评

P1 自评分：92 / 100。

- Tick 合同符合度：成功与失败 envelope 字段满足 Context Pack，成功只输出 status projection。
- 失败收口：预期异常均被转换为 typed result，未向调用方抛出；`apply_closeout=True` 且缺 `finished_at` 依赖 service fail-closed 后映射为 blocked。
- 副作用隔离：本模块只组合 service 与 status projection，不直接触达存储、DB、网络、LLM 或当前时间。
- 测试覆盖：覆盖成功路径、参数透传、小 payload、三类失败映射、closeout 参数错误、失败时不调用 projection。

剩余风险：

- 当前 artifact 缺失分类仅对 `FileNotFoundError` 生效；现有 resolver 的缺失 cycle 是 `ValueError` 子类，会按 contract violation 处理，这与 Context Pack 的显式映射一致，但后续如果希望区分缺失 artifact 与合同不一致，需要引入结构化异常而不是解析消息。
- CLI 尚未接入 tick envelope；本轮按非目标未修改 CLI。后续 scheduler 或 CLI 应优先调用该 wrapper，避免继续使用 Trial O 的手写错误 JSON。
