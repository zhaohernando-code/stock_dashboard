# Trial BI 评估记录：Forbidden Token Flow Codification

状态：verified
输入：`TRIAL_BI_CONTEXT_PACK_CN.md`
目标：评估 BG/BH 的 forbidden-token 与 no-reason-routing 经验是否已固化到全局流程。

## 1. 子任务

| 子进程 | owned files | 目标 | 状态 |
| --- | --- | --- | --- |
| BI1 | 全局流程文档、本评估文件 | 固化 forbidden-token 与 no-reason-routing 流程规则 | passed |

## 2. 评分

| 维度 | 权重 |
| --- | ---: |
| 规则准确性 | 40 |
| 可执行门禁引用 | 35 |
| 文档规模控制 | 15 |
| 验证完整性 | 10 |

自动重跑阈值：

- 没有引用 `--forbidden-source-token`。
- 没有明确禁止用 `reason` 文案改写 route/action/output。
- 将规则写成过宽泛的“禁止所有 reason 字段”。
- process hardening、forbidden-token smoke、registry 或 full regression 失败。

## 3. BI1 结果

BI1 已完成文档固化：

- `AUTONOMOUS_DEVELOPMENT_FLOW_CN.md` 在实现试验硬化规则中新增 forbidden source token 门禁要求，明确 Context Pack / closeout 可用 `process-hardening-check --forbidden-source-token path:token` 固化源码禁用。
- 明确 route/action/apply/output 等基座链路不得解析 `route.reason` 等自然语言 reason 文案来改写结构化 route、action 或 output；reason 仍可作为解释、诊断和审计字段。
- 明确真实 CLI / artifact root smoke 应验证当前 contract，不得为了测试预设反向改写核心 route。
- 未修改生产代码、测试代码或 registry。

## 4. 主进程验证

- Process hardening：`status=pass`，`issue_count=0`，全局流程文档包含 `forbidden-source-token` 与 `route.reason` 证据；行数 `282/340`，本文件 `51/140`。
- Forbidden-token smoke：`status=pass`，目标 `src/ashare_evidence/autonomous_flow_scheduler_action_route_auto_apply.py:'route.reason =='` 未命中 forbidden token。
- Registry：`status=pass`，`doc_count=2`，`issue_count=0`。
- Full regression：`PYTHONPATH=src python3 -m pytest -q` -> `497 passed, 147 deselected in 21.91s`。

主进程合入 BI1 产物后完成以下复验：

- process hardening：`status=pass`，`issue_count=0`，required evidence 命中 `forbidden-source-token` 与 `route.reason`。
- forbidden-token smoke：`status=pass`，`route.reason ==` 未命中。
- registry check：`status=pass`，`issue_count=0`。
- full regression：`497 passed, 147 deselected in 20.77s`。

## 5. 重跑记录

- 无重跑。首轮文档改动满足 required evidence、line budget、registry 和 full regression。

## 6. 自评

BI1 自评：93 / 100。规则准确区分了“reason 可诊断”和“不得用 reason 文案驱动结构化分支”，并把 BG/BH 经验落到可执行 `--forbidden-source-token` 门禁。残余风险是 forbidden token 仍是显式子串扫描，不提供 AST 级语义识别；这与 BH 工具合同一致，后续 Context Pack 需要给出具体 path/token。
