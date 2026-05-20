# Trial F 评估记录：Phase 5 自运行 Cycle 原语

状态：已完成  
输入：`TRIAL_F_CONTEXT_PACK_CN.md`  
目标：评估 cycle 原语是否足以支撑后续 scheduler / projection / publish verifier 接入。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| F1 | `autonomous_flow.py`、`test_autonomous_flow.py`、本评估文件 | 实现最小 cycle 原语 |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| Cycle 合同符合度 | 30 |
| Artifact store 使用一致性 | 25 |
| 测试覆盖 | 25 |
| 副作用控制 | 20 |

自动重跑阈值：

- 总分低于 85。
- 函数内部读取当前时间、DB、网络或 LLM。
- append refs 不去重。
- missing cycle 被静默创建。
- publish verification 存入 manifest 明细。
- focused tests 失败。

## 3. F1 结果

状态：已完成

改动文件：

- `src/ashare_evidence/autonomous_flow.py`
- `tests/test_autonomous_flow.py`
- `docs/contracts/autonomous-flow-trial/TRIAL_F_EVALUATION_CN.md`

实现内容：

- 新增最小 cycle orchestration 层，所有持久化写入复用 existing artifact store。
- `start_phase5_cycle` 创建 `phase5_cycle_ledger` 并记录 `phase5.cycle.started.v1`。
- artifact / gate / recovery / publish 四类追加动作都要求 cycle 已存在；缺失时抛出明确错误。
- refs 追加采用稳定去重，不重复写入同一 ref 或 event。
- gate readout 和 recovery ticket 写入独立 artifact 后，再把 ref 追加到 cycle ledger。
- publish verification 只读取 release manifest 文件内容计算 digest，ledger 只保存 manifest ref、digest 和 `runtime.publish.verified.v1`。

副作用边界：

- 不读 DB。
- 不读网络。
- 不调用 LLM。
- 不在函数内部读取当前时间；所有时间戳均由调用方传入。
- 不修改现有 artifact model / store。

## 4. 主进程验证

F1 本地验证：

| 命令 | 结果 |
| --- | --- |
| `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow.py` | 6 passed |
| `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow.py tests/test_autonomous_flow_artifacts.py` | 10 passed |

主进程门禁：

| 命令 | 结果 |
| --- | --- |
| `ruff check src/ashare_evidence/autonomous_flow.py tests/test_autonomous_flow.py` | pass |
| `PYTHONPATH=src python3 -m pytest tests/test_autonomous_flow.py tests/test_autonomous_flow_artifacts.py -q` | 10 passed |
| `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/autonomous-flow-trial/TRIAL_F_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_F_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated` | status=pass, issue_count=0 |
| `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage` | pass |
| `git diff --check` | pass |
| `PYTHONPATH=src python3 -m pytest -q` | 239 passed, 147 deselected |

运行时发布验证：本轮只新增本地 orchestration 原语和测试，不改变用户可见 Web/runtime 行为，因此不触发发布或浏览器验收。

## 5. 重跑记录

一次测试修正：

- 初版 publish verification 测试误用 Pydantic `model_copy(update=...)` 断言 extra forbid；该 API 不执行校验。
- 已改为断言持久化后的 publish verification payload 只有 release manifest ref、digest、event ref 三个字段。

一次主进程补强：

- 原 missing cycle 测试只覆盖 artifact append。
- 主进程补充 gate readout、recovery ticket、publish verification 三条更新路径的 missing cycle fail-closed 断言。

无需重跑子进程。

主进程评估后无需触发第二轮子进程重跑：

- 合同要求均已被 focused tests 和完整回归覆盖。
- 无 fail-closed、去重、manifest digest 或副作用边界违例。
- 剩余能力均属于 scheduler / projection / publish verifier 后续轮次边界。

流程坑点记录：

- 不要用临时 `-m "not integration"` 覆盖仓库默认 pytest marker 策略；本仓库默认门禁通过 `pyproject.toml` 排除慢集成和运行时集成测试。覆盖 marker 会把刻意排除的慢集成边界纳入，得到与默认门禁不一致的失败信号。

## 6. 自评

| 维度 | 评分 | 说明 |
| --- | ---: | --- |
| Cycle 合同符合度 | 28 / 30 | 覆盖 start、artifact、gate、recovery、publish；尚未接 scheduler 状态终结。 |
| Artifact store 使用一致性 | 25 / 25 | 所有写入走 existing artifact store。 |
| 测试覆盖 | 24 / 25 | 覆盖关键 happy path 和全部 update path 的 missing cycle；暂未覆盖 manifest missing 的文件系统异常。 |
| 副作用控制 | 20 / 20 | 无 DB、网络、LLM、当前时间读取。 |
| 总分 | 97 / 100 | 达到 Trial F 阈值。 |

自评风险：

- `phase5_cycle_ledger` 的 completed / finished_at 终结原语尚未实现，需等 scheduler 或 publish verifier 接入时补齐。
- publish manifest digest 使用原始文件 bytes 计算；如果后续 release verifier 采用 canonical JSON digest，需要统一。
- record artifact 当前只追加 ref，不校验 artifact family / schema version / lineage；这符合本轮最小原语边界，但后续可由 registry/schema gate 补强。
