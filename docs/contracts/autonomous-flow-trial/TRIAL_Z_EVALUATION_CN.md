# Trial Z 评估记录：Artifact Store 模块拆分

状态：主进程复核通过  
输入：`TRIAL_Z_CONTEXT_PACK_CN.md`  
目标：评估 artifact store 拆分是否在保持行为兼容的前提下，解决 `research_artifact_store.py` 继续膨胀的问题。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| Z1 | artifact store core、autonomous-flow artifact store、兼容 façade、测试、本评估文件 | 完成行为保持的模块拆分 |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 行为兼容性 | 35 |
| 模块边界 | 25 |
| 文件规模治理 | 20 |
| 测试覆盖 | 15 |
| 最小侵入 | 5 |

自动重跑阈值：

- 总分低于 85。
- 任一既有 artifact 读写路径改变。
- `research_artifact_store` 公开导入路径失效。
- repo artifact 写入保护行为改变。
- `research_artifact_store.py` 仍高于 430 行。
- focused tests 失败。

## 3. Z1 结果

子进程产出 core / autonomous-flow store 草稿，但未完成全部门禁收敛；主进程接管后完成行为保持拆分。

最终实现：

- 新增 `src/ashare_evidence/artifact_store_core.py`，承载 artifact root 解析、路径解析、repo 写入保护、Pydantic model 读写。
- 新增 `src/ashare_evidence/autonomous_flow_artifact_store.py`，承载 Phase 5 cycle / recovery / scheduler diagnostic / gate / projection artifact 的读写函数。
- `src/ashare_evidence/research_artifact_store.py` 保留原公开导入路径，作为兼容 façade，同时继续承载非 autonomous-flow research artifact 的读写函数。
- `tests/test_autonomous_flow_artifacts.py` 增加 direct import path 与兼容 façade 互操作断言。
- `tests/test_research_artifact_store.py` 继续覆盖 `PROJECT_ROOT` patch、repo artifact 写入保护和既有 research artifact layout。

## 4. 主进程验证

指定门禁：

- `PYTHONPATH=src python3 -m pytest tests/test_research_artifact_store.py tests/test_autonomous_flow_artifacts.py tests/test_autonomous_flow.py tests/test_autonomous_flow_resolver.py tests/test_autonomous_flow_service.py tests/test_cli_autonomous_flow_smoke.py -q`：通过，47 passed。
- `ruff check src/ashare_evidence/artifact_store_core.py src/ashare_evidence/autonomous_flow_artifact_store.py src/ashare_evidence/research_artifact_store.py tests/test_research_artifact_store.py tests/test_autonomous_flow_artifacts.py`：通过。
- `wc -l src/ashare_evidence/research_artifact_store.py src/ashare_evidence/artifact_store_core.py src/ashare_evidence/autonomous_flow_artifact_store.py`：334 / 149 / 253，均低于本轮阈值。
- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_Z_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_Z_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`：通过，issue_count=0。
- `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage`：通过，status=pass。
- `git diff --check`：通过。
- `PYTHONPATH=src python3 -m pytest -q`：通过，346 passed，147 deselected。

## 5. 重跑记录

第一次门禁失败：

- ruff 检出兼容层 re-export 被当作 unused import；改为模块导入后显式赋值 re-export。
- ruff 对测试 import 和 `timezone.utc` 提出修正；使用 `ruff --fix` 做机械整理。
- registry checker 将文档中的函数名代码 span 识别为 registry-like id；改为普通文字描述。

修正后 focused gates、registry gate、policy audit、full regression 均通过。

## 6. 自评

评分：93 / 100。

扣分与残余风险：

- `research_artifact_store.py` 仍是兼容 façade 与 non-autonomous research artifact store 的混合体；本轮先止住 autonomous-flow 继续膨胀，后续如其他 artifact family 继续增长，应按领域继续拆分。
- `autonomous_flow_artifact_store.py` 已经 253 行，后续新增 Phase 5 artifact family 时需要优先考虑再按 read/write family 分层，不能把该文件推到 300 行以上。
- 本轮没有批量改调用方 import，避免大范围 churn；新代码应优先直接导入 autonomous-flow artifact store 模块。
