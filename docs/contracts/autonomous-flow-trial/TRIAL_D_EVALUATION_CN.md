# Trial D 评估记录：Registry Checker 与 Claim Ceiling Gate

状态：进行中  
输入：`TRIAL_D_CONTEXT_PACK_CN.md`  
目标：评估 D1 / D2 代码实现是否足以作为后续无人开发流程的第一批机器门禁。

## 1. 子任务拆解

| 子进程 | 范围 | 目标 |
| --- | --- | --- |
| D1 | Registry JSON、schemas、checker、CLI、tests | 让合同引用可被机器检查 |
| D2 | Claim ceiling gate、tests | 统一用户可见结论强度上限 |

## 2. 评分标准

| 维度 | 权重 |
| --- | ---: |
| 合同符合度 | 25 |
| 测试覆盖 | 25 |
| 与现有代码风格一致性 | 20 |
| 无人流程能力提升 | 20 |
| 子进程边界遵守 | 10 |

自动重跑阈值：

- 总分低于 85。
- 测试失败。
- CLI 会初始化数据库或触发 runtime 行为。
- claim gate 读取外部状态、时间、DB、网络、LLM。
- 子进程越权文件。

## 3. D1 结果

接受。

改动范围：

- `docs/contracts/registry/autonomous_flow_registry.v1.json`
- `docs/contracts/registry/schemas/autonomous_flow_registry.schema.json`
- `docs/contracts/registry/schemas/phase5_cycle_ledger.schema.json`
- `docs/contracts/registry/schemas/phase5_gate_readout.schema.json`
- `docs/contracts/registry/schemas/phase5_recovery_ticket.schema.json`
- `src/ashare_evidence/contract_registry.py`
- `tests/test_contract_registry.py`
- `src/ashare_evidence/cli.py`

评分：

| 维度 | 权重 | 得分 | 说明 |
| --- | ---: | ---: | --- |
| 合同符合度 | 25 | 24 | JSON registry 覆盖 accepted ids、deprecated ids、maturity、claim levels。 |
| 测试覆盖 | 25 | 23 | 覆盖结构校验、未注册、deprecated、proposed misuse、CLI 无 DB 初始化。 |
| 与现有代码风格一致性 | 20 | 18 | 使用标准库、argparse、现有 CLI 模式；未新增依赖。 |
| 无人流程能力提升 | 20 | 20 | 后续 Context Pack 和子进程输出可被机器检查。 |
| 子进程边界遵守 | 10 | 10 | 只改 owned files。 |
| **总分** | **100** | **95** | 接受。 |

主进程复验：

```bash
PYTHONPATH=src python3 -m pytest tests/test_contract_registry.py tests/test_claim_ceiling.py
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_B_GLOBAL_PROTOCOL_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_C_LEDGER_AND_PUBLISH_DECISION_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_C_REGISTRY_AND_CLAIM_GATE_DECISION_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_D_CONTEXT_PACK_CN.md \
  --fail-on-unregistered \
  --fail-on-deprecated
```

结果：focused tests `11 passed`；registry CLI `status=pass`、`issue_count=0`。

## 4. D2 结果

接受。

改动范围：

- `src/ashare_evidence/claim_ceiling.py`
- `tests/test_claim_ceiling.py`

评分：

| 维度 | 权重 | 得分 | 说明 |
| --- | ---: | ---: | --- |
| 合同符合度 | 25 | 24 | 实现四级 ceiling 与 required output fields。 |
| 测试覆盖 | 25 | 23 | 覆盖缺验证、stale、publish pending、manual LLM disagreement、simulation-only、validated readout。 |
| 与现有代码风格一致性 | 20 | 19 | 纯函数、无外部依赖、无副作用。 |
| 无人流程能力提升 | 20 | 19 | 后续 projection/scheduler 可复用同一 gate。 |
| 子进程边界遵守 | 10 | 10 | 只改 owned files。 |
| **总分** | **100** | **95** | 接受。 |

主进程复验：同 D1 focused test 命令，`tests/test_claim_ceiling.py` 6 个用例通过。

## 5. 主进程验证

已完成：

- `git diff --check` 通过。
- `PYTHONPATH=src python3 -m pytest tests/test_contract_registry.py tests/test_claim_ceiling.py` 通过，`11 passed`。
- `PYTHONPATH=src python3 -m pytest -q` 首轮暴露一个既有权限测试断言漂移：测试名要求 analyst 可以 create / execute manual research，但断言仍期待 create 403。
- D3 子进程只修改 `tests/test_api_access.py`，把该测试修正为 analyst create 200、execute 200、complete 仍 403。
- 修正后 `PYTHONPATH=src python3 -m pytest -q` 通过，`229 passed, 147 deselected`。
- pre-commit 首轮阻断 `cli.py` 继续增长；主进程把 `policy-audit` 与 `contract-registry-check` wiring 抽到 `src/ashare_evidence/cli_governance.py`，使 `cli.py` 降到 1241 行。
- CLI 拆分后 focused tests 通过，完整 `PYTHONPATH=src python3 -m pytest -q` 再次通过，`229 passed, 147 deselected`。
- `PYTHONPATH=src python3 -m ashare_evidence.cli policy-audit --fail-on-new-unclassified --fail-on-direct-config-read --fail-on-formula-side-effects --fail-on-missing-config-lineage` 通过。
- registry CLI 对 Trial B/C/D 输入通过，`issue_count=0`。
- 本轮是最小流程门禁实现，不涉及 live-facing UI 或 runtime，因此不触发 runtime publish 和浏览器验收。

## 6. 重跑记录

本轮不触发重跑。

残余风险进入下一轮：

- Registry checker 仍是正则 + 上下文启发式扫描，极端 Markdown 格式可能误报或漏报；后续若误报率升高，再升级 Markdown parser。
- JSON Schema 当前作为合同文件存在，checker 只做最小结构校验；后续需要更严格 schema validator 时再引入，但不能新增不必要依赖。
- `claim_ceiling` 尚未接入 projection / scheduler / reviewer；下一轮应先用 registry checker 生成 Context Pack，再分派接入点设计或实现。
