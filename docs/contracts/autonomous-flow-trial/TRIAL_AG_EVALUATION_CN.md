# Trial AG 评估记录：Implementation Process Hardening Rules

状态：已完成  
输入：`TRIAL_AG_CONTEXT_PACK_CN.md`  
目标：评估近期实现试验的流程经验是否已固化为后续无人开发可执行约束。

## 1. 子任务

| 子进程 | owned files | 目标 |
| --- | --- | --- |
| AG1 | 流程合同、试验记录、本评估文件 | 固化 AC-AF 的流程经验 |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 流程规则可执行性 | 35 |
| 近期坑点覆盖 | 30 |
| 子进程 / 主进程边界清晰度 | 20 |
| 文档规模与门禁 | 15 |

自动重跑阈值：

- 未覆盖文件规模治理。
- 未覆盖 legacy migration 验收。
- 未区分子进程门禁和主进程接受。
- 文档只描述原则，没有进入 Context Pack 或验收规则。
- registry check 或 diff check 失败。

## 3. AG1 结果

AG1 已按 Context Pack 固化 AC-AF 暴露出的流程规则。

修改文件：

- `docs/contracts/AUTONOMOUS_DEVELOPMENT_FLOW_CN.md`
- `docs/contracts/AUTONOMOUS_FLOW_TRIAL_2026-05-20_CN.md`
- `docs/contracts/autonomous-flow-trial/TRIAL_AG_EVALUATION_CN.md`

主要固化内容：

- 在 P0 Context Pack 阶段加入文件行数、目标上限和拆分触发线要求。
- 在 P2 任务拆解阶段加入测试、fixture、helper、store、service 的规模预算规则。
- 在 P4 自动评审阶段加入语义 diff 审查，覆盖迁移、旧数据、crash replay、冲突分支、副作用、幂等和并发语义。
- 在自动重跑触发中加入基座能力不得只靠扫描逻辑、legacy migration 必须验收、文件规模接近上限必须处理。
- 在 P6 closeout 中要求评估文档记录子进程输出、主进程审查、主进程修正、最终门禁和残余风险。
- 在试验记录新增 AC-AF 实现试验补充结论，明确文件规模治理、子进程门禁与主进程接受分离、基座硬状态、legacy migration 和评估记录要求。

本轮没有修改代码、registry 或历史 trial 产物。

## 4. 主进程验证

AG1 本地门禁已执行：

- `PYTHONPATH=src python3 -m ashare_evidence.cli contract-registry-check --registry docs/contracts/registry/autonomous_flow_registry.v1.json --docs docs/contracts/AUTONOMOUS_DEVELOPMENT_FLOW_CN.md --docs docs/contracts/AUTONOMOUS_FLOW_TRIAL_2026-05-20_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_AG_CONTEXT_PACK_CN.md --docs docs/contracts/autonomous-flow-trial/TRIAL_AG_EVALUATION_CN.md --fail-on-unregistered --fail-on-deprecated`
- `git diff --check`
- `wc -l docs/contracts/AUTONOMOUS_DEVELOPMENT_FLOW_CN.md docs/contracts/AUTONOMOUS_FLOW_TRIAL_2026-05-20_CN.md docs/contracts/autonomous-flow-trial/TRIAL_AG_EVALUATION_CN.md`

结果：

- registry check：通过，0 issues。
- git diff check：通过。
- wc：流程合同 276 行，试验记录 182 行，AG 评估 92 行。

主进程复验：

- registry check：通过，4 docs，0 issues，registered ids 57。
- git diff check：通过。
- wc：流程合同 276 行，试验记录 182 行，AG 评估 92 行。
- 本轮只修改流程文档，不触发代码 full regression 或 runtime publish。

门禁修正记录：

- 首次 registry check 发现试验总记录中保留了 Trial A 的旧式无版本事件名，触发 deprecated id。AG1 没有修改 registry，也没有重写历史 trial 产物，只在允许修改的试验总记录中改为描述性措辞，随后 registry check 通过。

## 5. 重跑记录

未触发重跑。当前修改把 Context Pack 的五个硬要求都落到了流程阶段或试验记录：

- 文件规模治理进入 P0、P2、P4 和 AC-AF 试验补充结论。
- 子进程门禁不等于主进程接受进入 P2、P4 和 AC-AF 试验补充结论。
- 基座能力不能只靠扫描逻辑进入 P4 重跑触发和实现试验硬化规则。
- legacy migration 验收进入 P4 重跑触发和 AC-AF 试验补充结论。
- 评估文档必须记录主进程修正进入 P6 和 AC-AF 试验补充结论。

## 6. 自评

| 维度 | 权重 | 得分 | 说明 |
| --- | ---: | ---: | --- |
| 流程规则可执行性 | 35 | 33 | 每条规则都绑定到 Context Pack、任务拆解、评审、重跑或 closeout 节点。 |
| 近期坑点覆盖 | 30 | 30 | 覆盖 AC-AF 暴露的文件规模、门禁误判、扫描式幂等、reservation、legacy migration 和评估补录问题。 |
| 子进程 / 主进程边界清晰度 | 20 | 19 | 明确子进程只报告局部门禁，主进程负责语义 diff、修正记录和重跑判断。 |
| 文档规模与门禁 | 15 | 15 | 文档仍保持可读规模；registry check、diff check 和 wc 已由 AG1 与主进程复验。 |
| **总分** | **100** | **97** | 可接受并固化。 |

残余风险：

- 本轮只修改流程文档，没有把规则做成自动化 linter 或 CI gate；后续应把文件规模、评估字段完整性和 legacy migration 测试存在性升级为机器检查。
- 基座硬状态规则已经写入流程，但具体分布式原子边界仍需在对应实现 trial 中单独设计。
