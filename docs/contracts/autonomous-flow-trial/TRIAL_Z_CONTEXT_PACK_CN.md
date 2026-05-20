# Trial Z Context Pack：Artifact Store 模块拆分

状态：active input  
上游：Trial Y  
目标：拆分 `research_artifact_store.py`，把通用 artifact IO 基座与 autonomous-flow artifact IO 从单一大文件中分离出来，避免后续基座功能继续以“补丁式追加”挤压 500 行门禁。

## 1. 背景

Trial Y 新增 `phase5_scheduler_diagnostic` 后，`src/ashare_evidence/research_artifact_store.py` 已达到 495 行。提交前曾触发文件规模门禁风险，说明当前 artifact store 已不适合作为所有 artifact family 的唯一增长点。

这属于流程验证中暴露出的基座设计问题：后续如果继续追加 scheduler/recovery/projection artifact，不能再向同一个文件堆函数。

## 2. 本轮目标

做一次行为保持的结构拆分：

- 新增通用 artifact store core 模块，承载：
  - artifact root 解析
  - repo artifact 写入保护
  - artifact path resolution
  - `_write_model`
  - `_read_model`
  - `_read_model_if_exists`
  - artifact folder map
- 新增 autonomous-flow artifact store 模块，承载：
  - `phase5_cycle_ledger`
  - `phase5_recovery_ticket`
  - `phase5_scheduler_diagnostic`
  - `phase5_gate_readout`
  - `frontend_projection_manifest`
- `research_artifact_store.py` 继续保留既有公开导入路径，作为兼容 façade re-export autonomous-flow store 函数。
- 不改变任何 artifact 的落盘路径、payload、读写语义。

## 3. 非目标

- 不新增 artifact family。
- 不修改 registry。
- 不修改 artifact schema。
- 不修改 autonomous-flow runtime 行为。
- 不改 CLI / API / SPA。
- 不改业务 policy 或 planner。
- 不发布 runtime。

## 4. Owned Files

默认只允许修改：

- `src/ashare_evidence/artifact_store_core.py`
- `src/ashare_evidence/autonomous_flow_artifact_store.py`
- `src/ashare_evidence/research_artifact_store.py`
- `tests/test_research_artifact_store.py`
- `tests/test_autonomous_flow_artifacts.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_Z_EVALUATION_CN.md`

如确需批量改 import，必须说明原因，并保持兼容导入路径仍可用。

## 5. 合同要求

- `from ashare_evidence.research_artifact_store import read_phase5_cycle_ledger_artifact` 继续可用。
- 新路径 `from ashare_evidence.autonomous_flow_artifact_store import read_phase5_cycle_ledger_artifact` 可用。
- database-url to artifact-root 解析行为不变。
- `PROJECT_ROOT`、`DEFAULT_ARTIFACT_ROOT` 兼容导出不破坏现有测试 patch。
- repo artifact 写入保护行为不变。
- 所有 autonomous-flow artifact 路径完全不变。
- 拆分后 `research_artifact_store.py` 明显低于 500 行；目标低于 430 行。
- 新增模块不要超过 300 行。

## 6. Tests

至少覆盖：

- 既有 `tests/test_research_artifact_store.py` 通过。
- 既有 `tests/test_autonomous_flow_artifacts.py` 通过。
- 新增断言：autonomous-flow artifact store 新模块路径可直接读写。
- 新增断言：`research_artifact_store` 兼容 re-export 路径仍可直接读写。
- 文件行数门禁记录到评估文档。

## 7. 验收

- `PYTHONPATH=src python3 -m pytest tests/test_research_artifact_store.py tests/test_autonomous_flow_artifacts.py tests/test_autonomous_flow.py tests/test_autonomous_flow_resolver.py tests/test_autonomous_flow_service.py tests/test_cli_autonomous_flow_smoke.py -q`
- `ruff check src/ashare_evidence/artifact_store_core.py src/ashare_evidence/autonomous_flow_artifact_store.py src/ashare_evidence/research_artifact_store.py tests/test_research_artifact_store.py tests/test_autonomous_flow_artifacts.py`
- `wc -l src/ashare_evidence/research_artifact_store.py src/ashare_evidence/artifact_store_core.py src/ashare_evidence/autonomous_flow_artifact_store.py`
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_Z_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_Z_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
