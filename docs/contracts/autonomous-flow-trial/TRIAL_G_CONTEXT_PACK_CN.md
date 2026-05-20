# Trial G Context Pack：Phase 5 Projection Manifest 原语

状态：active input  
上游：Trial C / D / E / F  
目标：在已有 cycle 原语和 artifact store 基础上，实现 `frontend_projection_manifest` 的最小 durable 原语，让后续 scheduler / projection builder / publish verifier 能通过统一函数记录 projection 刷新事实。

## 1. 本轮目标

实现一个纯本地、可测试、无 runtime 副作用的 projection manifest 层：

- 新增 `frontend_projection_manifest` artifact model。
- 在 `research_artifact_store` 中新增该 artifact 的 write/read/read_if_exists 路径。
- 新增或扩展 orchestration 函数，写入 projection manifest 后，把 projection ref 追加到 `phase5_cycle_ledger`。
- 记录 `phase5.projection.refreshed.v1` 到 cycle event refs。
- projection manifest 只保存轻量只读元数据，不保存页面完整 payload 或运行时发布明细。

## 2. 非目标

- 不构建真实前端 projection payload。
- 不改 API / SPA。
- 不启动 scheduler、LaunchAgent 或后台服务。
- 不调用 release verifier。
- 不发布 runtime。
- 不新增数据库表。
- 不改变当前 Phase 5 研究结果。

## 3. Owned Files

- `src/ashare_evidence/autonomous_flow_artifacts.py`
- `src/ashare_evidence/research_artifact_store.py`
- `src/ashare_evidence/autonomous_flow.py`
- `tests/test_autonomous_flow_artifacts.py`
- `tests/test_autonomous_flow.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_G_EVALUATION_CN.md`

如确需修改 registry、CLI、API 或前端，必须说明原因；默认不改。

## 4. Registry IDs

只允许新增引用：

- `frontend_projection_manifest`
- `phase5.projection.refreshed.v1`
- `frontend.projection.updated.v1`
- `iface.projection.publish-verifier.v1`
- `iface.projection.api-spa.v1`

可继续引用 Trial F 已使用 id：

- `phase5_cycle_ledger`
- `phase5.cycle.started.v1`
- `phase5.artifact.produced.v1`
- `phase5.gate.evaluated.v1`
- `phase5.recovery.recorded.v1`
- `runtime.publish.verified.v1`

## 5. Artifact Model 要求

建议模型名：

- `FrontendProjectionManifestArtifact`

字段建议：

- `artifact_family = "frontend_projection_manifest"`
- `schema_version = "v1"`
- `projection_id`
- `cycle_id`
- `projection_name`
- `projection_family`
- `version`
- `generated_at`
- `freshness_at`
- `source_artifact_ids`
- `row_count`
- `staleness_status`
- `fallback_reason`
- `event_refs`

约束：

- `staleness_status` 至少支持 `fresh`、`stale`、`degraded`。
- `row_count` 不得为负数。
- `source_artifact_ids` 和 `event_refs` 需要稳定去重。
- 不允许塞完整 frontend payload、release manifest 明细、浏览器截图或 DB 查询结果。

## 6. Orchestration 函数要求

建议函数，不强制命名完全一致：

- `record_phase5_projection_refreshed(...) -> tuple[Phase5CycleLedgerArtifact, FrontendProjectionManifestArtifact]`

约束：

- 目标 cycle 必须已存在；缺失时复用 Trial F 的明确错误。
- 函数必须是确定性本地文件操作，不读 DB、不读网络、不调用 LLM。
- 时间戳由调用方传入，不在函数内部读取当前时间。
- 写入 projection manifest 后，cycle 必须追加 projection ref 和 `phase5.projection.refreshed.v1`。
- 追加 refs 时必须去重。
- 不要自动把 cycle 标记为 completed；cycle 终结等 scheduler / publish verifier 后续轮次处理。

## 7. Tests

至少覆盖：

- projection manifest artifact round trip。
- `source_artifact_ids` / `event_refs` 去重。
- `row_count < 0` 被拒绝。
- record projection 写入 manifest，并把 ref 和 `phase5.projection.refreshed.v1` 追加到 cycle。
- 重复 record 同一 projection 不重复追加 ref/event。
- missing cycle 时 projection 记录失败。
- manifest 不包含完整 payload 或 publish 明细。

## 8. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow.py tests/test_autonomous_flow_artifacts.py -q`
- `ruff check src/ashare_evidence/autonomous_flow_artifacts.py src/ashare_evidence/research_artifact_store.py src/ashare_evidence/autonomous_flow.py tests/test_autonomous_flow_artifacts.py tests/test_autonomous_flow.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_G_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_G_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
