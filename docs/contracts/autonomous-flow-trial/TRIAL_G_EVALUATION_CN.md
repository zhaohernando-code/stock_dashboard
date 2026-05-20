# Trial G 评估记录：Phase 5 Projection Manifest 原语

状态：已完成  
输入：`TRIAL_G_CONTEXT_PACK_CN.md`  
目标：评估 projection manifest 原语是否足以支撑后续 scheduler / projection builder / publish verifier 接入。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| G1 | `autonomous_flow_artifacts.py`、`research_artifact_store.py`、`autonomous_flow.py`、相关测试、本评估文件 | 实现最小 projection manifest 原语 |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| Projection 合同符合度 | 30 |
| Artifact store 使用一致性 | 25 |
| 测试覆盖 | 25 |
| 副作用控制 | 20 |

自动重跑阈值：

- 总分低于 85。
- 函数内部读取当前时间、DB、网络或 LLM。
- projection manifest 存入完整前端 payload、release manifest 明细或浏览器截图。
- append refs 不去重。
- missing cycle 被静默创建。
- focused tests 失败。

## 3. G1 结果

状态：完成  
子进程：G1  
工作区：`/Users/hernando_zhao/codex/projects/stock_dashboard`  
分支：`task/stock_dashboard/20260520-autonomous-projection-manifest`

### 3.1 修改文件

- `src/ashare_evidence/autonomous_flow_artifacts.py`
- `src/ashare_evidence/research_artifact_store.py`
- `src/ashare_evidence/autonomous_flow.py`
- `tests/test_autonomous_flow_artifacts.py`
- `tests/test_autonomous_flow.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_G_EVALUATION_CN.md`

### 3.2 实现摘要

- 新增 `FrontendProjectionManifestArtifact`，artifact family 为 `frontend_projection_manifest`，schema version 为 `v1`。
- manifest 字段覆盖 `projection_id`、`cycle_id`、`projection_name`、`projection_family`、`version`、`generated_at`、`freshness_at`、`source_artifact_ids`、`row_count`、`staleness_status`、`fallback_reason`、`event_refs`。
- `staleness_status` 限定为 `fresh`、`stale`、`degraded`；`row_count` 使用非负约束；`source_artifact_ids` 和 `event_refs` 在模型层稳定去重。
- manifest 使用 `extra="forbid"`，拒绝完整 frontend payload、release manifest 明细、截图等额外字段。
- artifact store 新增 `write_frontend_projection_manifest_artifact`、`read_frontend_projection_manifest_artifact`、`read_frontend_projection_manifest_artifact_if_exists`，路径为 `autonomous_flow/frontend_projection_manifest/<projection_id>.json`。
- 新增 `record_phase5_projection_refreshed(...)`，先要求目标 `phase5_cycle_ledger` 已存在，再写 manifest，并把 `frontend_projection_manifest:<projection_id>` 和 `phase5.projection.refreshed.v1` 去重追加到 cycle。
- orchestration 不读取当前时间、不读 DB、不读网络、不调用 LLM，不自动将 cycle 标记为 completed。

### 3.3 G1 验证

| 命令 | 结果 |
| --- | --- |
| `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow.py tests/test_autonomous_flow_artifacts.py -q` | 14 passed |
| `ruff check src/ashare_evidence/autonomous_flow_artifacts.py src/ashare_evidence/research_artifact_store.py src/ashare_evidence/autonomous_flow.py tests/test_autonomous_flow_artifacts.py tests/test_autonomous_flow.py` | passed |

## 4. 主进程验证

主进程复核结论：通过。

复核重点：

- `FrontendProjectionManifestArtifact` 使用 `extra="forbid"`，测试覆盖额外 `payload` 被拒绝，能够阻止完整前端 payload、release manifest 明细或截图夹带。
- `record_phase5_projection_refreshed(...)` 先读取既有 cycle，缺失时复用 Trial F 的 fail-closed 错误，不会静默创建隐藏 cycle。
- projection manifest 与 cycle event refs 都做去重。
- 函数没有读取当前时间、DB、网络或 LLM。
- projection ref 当前复用 `phase5_cycle_ledger.artifact_refs`，这是本轮最小原语边界；后续若需要在查询层区分 research artifact 与 projection artifact，再升级 ledger schema，而不是在本轮引入额外字段。

主进程门禁：

| 命令 | 结果 |
| --- | --- |
| `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow.py tests/test_autonomous_flow_artifacts.py -q` | 14 passed |
| `ruff check src/ashare_evidence/autonomous_flow_artifacts.py src/ashare_evidence/research_artifact_store.py src/ashare_evidence/autonomous_flow.py tests/test_autonomous_flow_artifacts.py tests/test_autonomous_flow.py` | pass |
| `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_G_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_G_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated` | status=pass, issue_count=0 |
| `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage` | pass |
| `git diff --check` | pass |
| `PYTHONPATH=src python3 -m pytest -q` | 243 passed, 147 deselected |

运行时发布验证：本轮只新增本地 projection manifest 原语和测试，不改变用户可见 Web/runtime 行为，因此不触发发布或浏览器验收。

## 5. 重跑记录

无需重跑子进程。

原因：

- G1 输出满足 Context Pack 的 owned files 和非目标边界。
- 未发现 payload 夹带、missing cycle 静默创建、事件/引用重复追加或副作用越界。
- 剩余能力属于 scheduler、真实 projection builder、API / SPA 读取和 publish verifier 后续轮次。

## 6. 自评

G1 自评分：96 / 100

| 维度 | 得分 | 说明 |
| --- | ---: | --- |
| Projection 合同符合度 | 29 / 30 | 覆盖 manifest 模型、projection refreshed 事件和 cycle ref 追加；未实现真实 projection builder，符合本轮非目标。 |
| Artifact store 使用一致性 | 25 / 25 | 所有读写复用 typed artifact store，路径隔离到 `autonomous_flow/frontend_projection_manifest`。 |
| 测试覆盖 | 24 / 25 | 覆盖 round trip、去重、负 row_count、extra payload 拒绝、missing cycle、重复 record 去重和轻量 manifest 内容；未覆盖损坏 JSON 读入异常。 |
| 副作用控制 | 18 / 20 | 实现为纯本地文件操作，无时间/DB/网络/LLM；未接 publish verifier 与 live runtime，按边界保留。 |

风险 / 后续边界：

- `phase5_cycle_ledger` 仍使用既有 `artifact_refs` 保存 projection manifest ref，没有新增 registry/schema 字段。
- `frontend.projection.updated.v1` 仅允许作为 manifest `event_refs` 的调用方输入，本轮不把它解释为 API / SPA 已发布事实。
- publish verifier、scheduler cycle 终结、API / SPA 读取路径和真实 projection payload 构建均留给后续轮次。
