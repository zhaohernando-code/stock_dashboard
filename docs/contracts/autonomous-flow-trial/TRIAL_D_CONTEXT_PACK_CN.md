# Trial D Context Pack：Registry Checker 与 Claim Ceiling Gate 最小实现

状态：active input  
上游决策：`TRIAL_C_EVALUATION_CN.md`、`TRIAL_C_LEDGER_AND_PUBLISH_DECISION_CN.md`、`TRIAL_C_REGISTRY_AND_CLAIM_GATE_DECISION_CN.md`  
目标：实现第一批可执行流程门禁，让后续子进程和实现任务能被机器检查，而不是只靠主进程人工审阅。

## 1. 本轮目标

Trial D 做最小代码实现：

1. 建立 JSON registry 与最小 JSON Schema。
2. 实现 registry checker 和 CLI 命令。
3. 实现 `claim_ceiling` 公共 gate 的纯函数库。
4. 增加 focused tests。

## 2. 非目标

- 不接入 scheduler。
- 不写 runtime artifact store。
- 不改前端。
- 不发布 runtime。
- 不改变当前策略、推荐、短投、模拟盘结果。
- 不把 gate 接入生产 projection。
- 不更新 `PROJECT_STATUS.json`。

## 3. 子任务拆分

### D1：Registry / Checker

Owned files:

- `docs/contracts/registry/autonomous_flow_registry.v1.json`
- `docs/contracts/registry/schemas/autonomous_flow_registry.schema.json`
- `docs/contracts/registry/schemas/phase5_cycle_ledger.schema.json`
- `docs/contracts/registry/schemas/phase5_gate_readout.schema.json`
- `docs/contracts/registry/schemas/phase5_recovery_ticket.schema.json`
- `src/ashare_evidence/contract_registry.py`
- `tests/test_contract_registry.py`
- `src/ashare_evidence/cli.py`

要求：

- JSON registry 至少包含 Trial B / C 已接受的 events、artifact families、interfaces、deprecated ids、maturity domains、claim ceiling levels。
- checker 能检查文档中反引号包裹的 registry-like id：未注册、deprecated、`proposed_*` 被当 registered dependency。
- 增加 CLI：`python -m ashare_evidence.cli contract-registry-check --registry ... --docs ... --fail-on-unregistered --fail-on-deprecated`。
- CLI 默认不初始化数据库。
- tests 使用 unittest / pytest 均可，但要符合现有风格。

### D2：Claim Ceiling Gate

Owned files:

- `src/ashare_evidence/claim_ceiling.py`
- `tests/test_claim_ceiling.py`

要求：

- 实现确定性纯函数，不读 DB、不读网络、不读环境变量、不读当前时间、不调用 LLM。
- 提供四级 ceiling：`blocked`、`research_observation`、`paper_tracking_candidate`、`validated_readout`。
- 输入至少支持 validation status、simulation boundary、staleness status、publish verification status、manual LLM disagreement、blocking reasons。
- 输出至少包含 `gate_status`、`claim_ceiling`、`allowed_claims`、`forbidden_claims`、`failing_gate_ids`、`incomplete_gate_ids`、`next_action`。
- tests 覆盖缺验证、stale projection、publish 未验证、manual LLM disagreement 不提升 ceiling、validated readout。

## 4. 共同约束

- 不提交 git。
- 不启动服务。
- 不发布 runtime。
- 不改 `PROJECT_STATUS.json`、`PROCESS.md`、`DECISIONS.md`。
- 不覆盖其他子进程文件。
- 不引入外部依赖；JSON Schema 校验如果标准库不足，先做最小结构校验，不新增 package。
- 修改 `cli.py` 只允许 D1。

## 5. 验收

- `git diff --check` 通过。
- D1 tests 通过。
- D2 tests 通过。
- `python -m ashare_evidence.cli contract-registry-check ...` 能对 Trial B / C 文档返回 pass。
- `claim_ceiling` tests 能证明 gate 不会因 manual LLM 或未发布状态提升结论强度。
