# Trial Y 评估记录：Phase 5 Scheduler Diagnostic Artifact

状态：进行中  
输入：`TRIAL_Y_CONTEXT_PACK_CN.md`  
目标：评估 scheduler diagnostic artifact 是否能作为真实 scheduler 执行前的独立诊断落点，尤其覆盖 cycle ledger 缺失导致 recovery ticket 不能直接写入的场景。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| Y1 | registry、artifact model、artifact store、record 函数、测试、本评估文件 | 实现 `phase5_scheduler_diagnostic` 最小持久化合同 |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| Diagnostic artifact 合同符合度 | 30 |
| cycle 缺失容错 | 25 |
| registry/schema 一致性 | 20 |
| 输出泄露保护 | 15 |
| 测试覆盖与最小侵入 | 10 |

自动重跑阈值：

- 总分低于 85。
- cycle 缺失时 record 函数抛错或不写 diagnostic。
- record 函数写 recovery ticket。
- record 函数改变 cycle status、next_action 或 finished_at。
- 新增 id 未进入 registry 或文档检查失败。
- focused tests 失败。

## 3. Y1 结果

实现通过。

本轮新增：

- `Phase5SchedulerDiagnosticArtifact`，artifact family 为 `phase5_scheduler_diagnostic`。
- `phase5.scheduler.diagnostic.recorded.v1` 事件常量与 registry 注册项。
- `write/read/read_if_exists_phase5_scheduler_diagnostic_artifact` store 函数，落盘路径为 `autonomous_flow/phase5_scheduler_diagnostic/<diagnostic_id>.json`。
- `record_phase5_scheduler_diagnostic(...)` 本地 record 函数。
- `phase5_scheduler_diagnostic.schema.json`。

关键行为：

- cycle 存在时，先写 diagnostic artifact，再向 cycle ledger 的 `event_refs` 追加 `phase5.scheduler.diagnostic.recorded.v1`。
- cycle 存在时不修改 `status`、`next_action`、`finished_at`，也不追加 recovery ticket。
- cycle 缺失时，仍写 diagnostic artifact，返回 `(None, diagnostic)`，不抛 `Phase5CycleNotFoundError`。
- diagnostic model 拒绝额外字段，并对 `blocking_reasons`、`evidence_refs`、`notes` 做敏感内容保护，避免持久化 `input_bundle`、`runner_result`、`release-manifest:`、`sha256:`、`Traceback`。

## 4. 主进程验证

已通过：

- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow_artifacts.py tests/test_autonomous_flow.py -q`
  - `18 passed in 0.23s`
- `ruff check src/ashare_evidence/autonomous_flow_artifacts.py src/ashare_evidence/research_artifact_store.py src/ashare_evidence/autonomous_flow.py tests/test_autonomous_flow_artifacts.py tests/test_autonomous_flow.py`
  - `All checks passed!`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_Y_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_Y_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
  - `status=pass, issue_count=0`
- `git diff --check`
  - 通过
- `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage`
  - `status=pass`
- `PYTHONPATH=src python3 -m pytest -q`
  - `345 passed, 147 deselected in 20.39s`

## 5. 重跑记录

第一次 registry gate 失败：

- `TRIAL_Y_CONTEXT_PACK_CN.md` 第 64 行以代码标识引用了 `phase5_scheduler`，但 registry 尚未注册该 ID。

修正：

- 在 `maturity_domains` 中注册 `phase5_scheduler`，作为 scheduler source/provider 的可引用稳定 ID。

修正后 registry gate 通过。

提交前门禁第二次阻塞：

- pre-commit file-size guard 检出 `src/ashare_evidence/research_artifact_store.py` 增长到 507 行，超过 500 行限制。

修正：

- 不添加 large-file manifest 豁免；将新增 scheduler diagnostic store 函数压缩到 495 行，保留既有导出路径。
- 后续若继续扩展 artifact store，应单独拆分 `research_artifact_store.py`，不能继续向该文件追加功能。

## 6. 自评

评分：94 / 100。

扣分与残余风险：

- 本轮只建立 diagnostic artifact 和 record 原语，尚未接入真实 scheduler executor；这是 Trial Y 非目标。
- 诊断内容的敏感信息保护采用保守过滤策略：list 字段丢弃含敏感 token 的条目，`notes` 整体 redacted。后续如果需要更高可解释性，应设计结构化错误摘要，而不是把原始异常文本交给 diagnostic。
- cycle ledger 当前没有 `diagnostic_refs` 字段，本轮按上下文要求只追加 event ref；后续若 operations workbench 需要直接展示 diagnostic，需要单独设计索引或 projection。
