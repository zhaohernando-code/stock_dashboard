# Trial BI 上下文包：Forbidden Token Flow Codification

目标：把 BG/BH 两轮经验写回全局开发流程文档，使后续基座类开发能够在 Context Pack 与 closeout 中显式使用 `process-hardening-check --forbidden-source-token`，而不是依赖主进程人工记忆“不要解析 reason 文案”。

## 1. 背景

Trial BG1 暴露出“子进程通过匹配 `route.reason` 自然语言改写 route type”的补丁式实现。Trial BH 已新增可执行门禁 `--forbidden-source-token path:token`。本轮不改代码，只把这条经验固化到 `AUTONOMOUS_DEVELOPMENT_FLOW_CN.md` 的硬化规则中，并更新评估记录。

## 2. 本轮范围

必须做：

- 更新 `docs/contracts/AUTONOMOUS_DEVELOPMENT_FLOW_CN.md`。
- 明确：当 Context Pack 禁止某类源码写法时，应使用 `process-hardening-check --forbidden-source-token path:token` 固化为机器门禁。
- 明确：route/action/apply 等基座流转不得解析自然语言 `reason` 来改变结构化 route、action 或 output；如果 contract 期望与真实 route 不一致，应修正 contract 或新增结构化字段。
- 明确：真实 smoke 的职责是验证当前 contract 下的端到端行为，不应为了测试预设改写核心 route。
- 不改生产代码，不改 registry。

不得做：

- 不新增 process-hardening 功能。
- 不重写全局流程文档大段结构。
- 不新增过宽泛的“禁止所有 reason 使用”规则；本轮强调显式 forbidden token 和结构化 contract。

## 3. 子进程任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| BI1 | 全局流程文档、本评估文件 | 固化 forbidden-token 与 no-reason-routing 流程规则 |

## 4. 文件规模预算

- `docs/contracts/AUTONOMOUS_DEVELOPMENT_FLOW_CN.md`：hard 340，warning 320。
- `docs/contracts/autonomous-flow-trial/TRIAL_BI_EVALUATION_CN.md`：hard 140，warning 110。

如果达到 warning，必须压缩，不要继续扩写。

## 5. 验证命令

Process hardening：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_BI_EVALUATION_CN.md \
  --line-budget docs/contracts/AUTONOMOUS_DEVELOPMENT_FLOW_CN.md:340:320 \
  --line-budget docs/contracts/autonomous-flow-trial/TRIAL_BI_EVALUATION_CN.md:140:110 \
  --required-evidence docs/contracts/AUTONOMOUS_DEVELOPMENT_FLOW_CN.md:forbidden-source-token \
  --required-evidence docs/contracts/AUTONOMOUS_DEVELOPMENT_FLOW_CN.md:route.reason
```

Forbidden-token smoke：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli process-hardening-check \
  --evaluation-doc docs/contracts/autonomous-flow-trial/TRIAL_BI_EVALUATION_CN.md \
  --line-budget docs/contracts/AUTONOMOUS_DEVELOPMENT_FLOW_CN.md:340:320 \
  --forbidden-source-token src/ashare_evidence/autonomous_flow_scheduler_action_route_auto_apply.py:'route.reason =='
```

Registry：

```bash
PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check \
  --registry docs/contracts/registry/autonomous_flow_registry.v1.json \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BI_CONTEXT_PACK_CN.md \
  --docs docs/contracts/autonomous-flow-trial/TRIAL_BI_EVALUATION_CN.md \
  --fail-on-unregistered --fail-on-deprecated
```

Full regression：

```bash
PYTHONPATH=src python3 -m pytest -q
```
