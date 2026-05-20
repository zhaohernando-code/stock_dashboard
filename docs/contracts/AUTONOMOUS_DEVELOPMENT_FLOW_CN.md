# 自运行开发流程合同

状态：v0.2 draft  
适用范围：当前项目作为自动化平台流程试验田时的需求拆解、设计、实现、评审、发布与复盘。  
目标：让纯 AI 项目组在无需人工持续介入的前提下，能持续产出可维护、可验证、可追溯的工程成果。

## 1. 背景

上一轮多 agent 设计试验说明，并行产出可以提高覆盖速度，但默认会出现三类风险：

- 各模块文档独立成立，跨模块 API、事件、artifact schema 无法自然对齐。
- 子进程倾向把 scaffold 阶段写成 production 级复杂方案，导致后续实现负担过重。
- 缺少自动化重跑条件，主进程需要人工判断哪些问题必须回炉。

因此本流程把开发拆为“流程设计 -> 试运行 -> 质量评估 -> 自动重跑 -> 固化”的闭环，而不是一次性并行生成。

## 2. 总原则

- **先全局协议，后模块设计**：任何并行任务开始前，必须先产出或读取统一术语、事件注册表、artifact schema、模块接口矩阵和成熟度模型。
- **按成熟度限制设计深度**：模块处于 scaffold / partial / usable / production 的不同阶段时，只允许写到对应复杂度。
- **子进程只处理局部，主进程负责收敛**：子 agent 不负责合并、发布、全局接口命名、最终质量结论或主线状态更新。
- **失败先自恢复，再升级为阻塞**：遇到超时、上下文缺失、schema 冲突、测试失败、浏览器假阴性时，流程必须先执行预定义恢复动作。
- **每轮必须留下可复用经验**：如果一次问题会重复出现，写入 `PROCESS.md`；如果是架构或产品方向选择，写入 `DECISIONS.md`；如果是当前进度，写入 `PROJECT_STATUS.json`。

## 3. 成熟度模型

### scaffold

适用于只有方向但没有稳定实现的能力。

必须包含：
- 目标与非目标。
- 不超过 5 个核心实体。
- 不超过 3 条核心流程。
- 当前依赖与风险。
- 架构决策类开放问题。

禁止包含：
- 复杂状态机。
- 完整生产 SLA。
- 大而全 API surface。
- 未验证的容量、成本或稳定性承诺。

### partial

适用于已有雏形，但合同、状态或验证链路仍不稳定的能力。

必须包含：
- scaffold 全部内容。
- 数据契约草案。
- 最小事件列表。
- 可执行验收标准。
- 已知迁移边界。

禁止包含：
- 把现有补丁包装成最终架构。
- 隐含依赖人工判定的流程。

### usable

适用于可运行、可验收，但还没达到企业级稳定性的能力。

必须包含：
- partial 全部内容。
- 状态机。
- 失败处理。
- 可观测性。
- 回归测试与门禁。
- 降级策略。

### production

适用于用户可见或关键生产链路。

必须包含：
- usable 全部内容。
- 发布与回滚方案。
- 安全、权限、审计。
- 容量与性能预算。
- 真实 served 验证。
- 事故恢复与演练要求。

## 4. 流程阶段

### P0：上下文冻结

输入：
- 用户原始需求。
- 项目 canonical docs。
- 当前 git 状态。
- 相关合同、决策、流程经验。

输出：
- `Context Pack`：任务目标、非目标、项目边界、当前成熟度、不可触碰范围、必须读取的文件。

自动规则：
- 若 git dirty，先判断是否为本任务产生；不允许覆盖未知改动。
- 若涉及 live-facing 代码，必须加入发布与真实浏览器验证要求。
- 若涉及前端新页面或新板块，必须加入 PC Web 与手机独立设计稿要求。
- 若涉及实现、测试或共享文档，必须在 `Context Pack` 中列出关注文件的当前行数、目标上限和拆分触发线；测试文件达到 260 行应视为需要主动拆分，接近 300 行不得作为“门禁通过即可接受”的状态。
- `Context Pack` 必须是短文档，不应把长状态文件全文转发给每个子进程；推荐只包含目标、当前阶段、owned files、registry allowlist、成熟度限制、必读文件路径和禁止动作。
- 如果子进程需要读取超过 5 个长文档，主进程应先压缩为 `Context Pack`，否则任务容易被上下文读取成本拖慢或超时。

### P1：全局协议基线

任何并行模块设计前，必须先生成或更新：

- 术语表。
- 事件注册表。
- artifact schema registry。
- 模块接口矩阵。
- 成熟度矩阵。

验收：
- 每个模块只能引用注册过的事件、artifact 和外部接口。
- 每个跨模块依赖必须有 provider、consumer、contract owner 和失败语义。
- 全局协议任务不得和依赖它的模块设计任务并行。必须先完成全局协议，再把 registry allowlist 放入模块设计的 `Context Pack`。
- 早期可使用 Markdown registry appendix 作为轻量门禁，但进入代码实现前必须有可脚本检查的 allowlist；核心平台能力应进一步升级为 JSON Schema、DB registry 或代码生成清单。

### P2：任务拆解与调度

拆解原则：
- 每个子任务必须有 disjoint owned files。
- 每个子任务必须声明成熟度。
- 子任务只允许产出指定文件，不提交、不发布、不改全局状态。
- 子任务提示词必须包含“你不是唯一进程，不要覆盖他人文件”。

冲突检查：
- 同一文件、同一模块 owner、同一 runtime lock、同一 artifact writer 不能并行写。
- 设计任务可并行；实现任务只有在接口矩阵稳定后才可并行。
- 子进程接到实现任务时，必须把新增或高频修改的测试、fixture、helper、store、service 文件纳入规模预算；如果任务天然会扩大已有大文件，拆分 helper 或测试文件属于本任务范围，不得留给后续“清理”。
- 多进程任务的 Context Pack 必须声明“门禁通过只是子进程完成信号，不等于主进程接受”；主进程仍需做语义 diff 审查后才能合并。

### P3：模块产出

子进程输出必须使用统一模板：

1. 目标。
2. 非目标。
3. 当前成熟度。
4. 领域模型。
5. 核心流程。
6. 依赖的全局协议。
7. 数据 / API / 事件契约。
8. 失败与恢复。
9. 验收标准。
10. 测试与门禁。
11. 开放问题。

开放问题必须分类：
- `architecture_decision`：必须在实现前由主进程收敛。
- `implementation_choice`：可由实现阶段按现有模式决定。
- `research_unknown`：需要实验或数据验证。

### P4：自动评审

评审至少包括四类：

- **结构评审**：是否按模板输出，是否缺必要章节。
- **一致性评审**：是否引用未注册事件、artifact、API 或术语。
- **成熟度评审**：是否写超当前阶段，是否把 scaffold 冒充 production。
- **工程评审**：是否可实现、可测试、可观测，是否有隐含人工等待。
- **语义评审**：子进程门禁通过后，主进程必须至少审查一次 diff，重点覆盖 legacy migration、旧数据兼容、crash replay、冲突分支、副作用边界、幂等与并发语义。

评分：
- 0-59：不合格，必须重跑。
- 60-74：可作为草案，但必须修正高风险项。
- 75-89：可进入实现拆解。
- 90-100：可作为稳定合同。

自动重跑触发：
- 存在未注册跨模块接口。
- 有 production 级承诺但缺 served 验证路径。
- 子进程改动越权文件。
- 开放问题未分类。
- 设计依赖人工口头确认才能继续。
- 子进程只用“先查再写”扫描逻辑承载幂等、调度、artifact 写入、状态机等基座能力，但没有硬状态、原子边界、ledger 或 reservation 语义。
- 新机制接入既有 artifact family 时，没有测试“旧数据存在、新索引不存在”的迁移路径，或可能让旧数据绕过冲突检测与 claim gate。
- 子进程产物接近文件规模触发线但未拆分，且评估文档没有把它记录为主进程修正或重跑原因。

### P5：重跑

重跑时禁止简单追加补丁，必须把评审结论转成新的输入合同：

- 明确哪些规则升级为硬约束。
- 明确上一轮哪些输出被废弃、保留或降级。
- 只重跑受影响模块，不重跑稳定模块。
- 重跑后重新执行 P4 评审。

### P6：固化

固化位置：
- 当前状态：`PROJECT_STATUS.json`。
- 架构/产品决策：`DECISIONS.md`。
- 可复用流程约束：`PROCESS.md`。
- 活跃合同：`docs/contracts/`。

closeout：
- 文档任务至少通过 markdown 结构和 git diff 检查。
- live-facing 任务必须发布到 runtime 并验证 localhost 与 canonical route。
- 默认合并回 `main`，保持工作树干净；`git diff` / `git diff --stat` 只能证明 tracked 文件差异，不能证明没有 untracked 文件。
- commit 后、merge 前或 merge 后，主进程必须在 closeout 执行 clean git status 门禁：`process-hardening-check --require-clean-git-status --git-root .`。
- 若 clean git status 门禁发现 untracked、modified 或 staged 残留，主进程必须回到 P4/P5 判断它是漏提交、越权改动，还是需要拆成新任务；不得把最终 clean status closeout 责任下放给子进程。
- 评估文档必须记录子进程输出、主进程语义审查、主进程修正、最终门禁和残余风险；若主进程修正了子进程遗漏，必须写明它是流程缺口还是局部实现缺口。

## 5. 子进程规则裁剪

子进程必须遵守：
- 读取指定 canonical docs。
- 只改 owned files。
- 不覆盖未知改动。
- 不提交 git。
- 不启动长期服务。
- 不发布 runtime。
- 不更新 `PROJECT_STATUS.json`、`PROCESS.md`、`DECISIONS.md`，除非任务明确授权。

子进程可豁免：
- live browser 验收。
- runtime publish。
- 全局 closeout。
- 主线合并。
- 发布 manifest 更新。

主进程必须承担：
- 上下文冻结。
- 任务拆解。
- 全局协议收敛。
- 质量评估。
- 重跑决策。
- 持久状态更新。
- commit / merge / push。

## 6. 自恢复策略

| 场景 | 自动动作 | 何时升级为阻塞 |
| --- | --- | --- |
| 子进程超时 | 缩小任务范围后重试一次 | 同一 owned file 连续失败两次 |
| 文档结构缺章 | 自动生成缺章修复任务 | 修复后仍缺核心章节 |
| 接口命名冲突 | 以全局 registry 为准重写引用 | provider 与 consumer 语义冲突 |
| 浏览器验收异常 | 分层检查 health、hydration、auth、tunnel | localhost 与 canonical 同时不可验证 |
| 外部 LLM 超时 | 改为抽样评审或本地 reviewer | 关键安全/金融判断无法完成 |
| git dirty | 识别来源并避开未知改动 | 目标文件存在不可合并改动 |

## 7. 前端设计门禁

触发条件：
- 新建前端项目。
- 新增用户可见一级页面。
- 新增复杂工作台模块。
- 明显改变 PC 或手机信息架构。
- 用户明确要求视觉预期。

必做：
- PC Web 与手机尺寸分别设计；手机可独立信息架构。
- 单页 app 的 PC shell 必须占满视口宽高，内部模块允许局部滚动。
- 不允许横向滚动、直接裁切或依赖浏览器缩放才完整显示。
- 设计稿必须先经视觉 QA，再进入实现。

## 8. 当前试验要求

本项目后续流程试验按两轮执行：

1. **Trial A**：按 v0.2 流程重新生成当前任务的设计产出。
2. **评估**：使用 P4 四类评审打分，找出缺口。
3. **Trial B**：把评估结论升级为硬约束后，只重跑不合格部分。
4. **固化**：把有效规则写回 `PROCESS.md`，把方向性选择写入 `DECISIONS.md`。

目标不是追求一次完美，而是证明流程能在无人工补充提示的情况下自行发现问题、收敛问题并留下可复用规则。

## 9. 实现试验硬化规则

近期 AC-AF 实现试验暴露出一组必须进入后续无人开发的硬规则：

- **文件规模治理前置**：Context Pack 必须给出关注文件行数和拆分线。测试文件达到 260 行时，子进程要优先拆分 fixture、helper 或主题测试文件；接近 300 行即使门禁通过，也应由主进程判为维护性劣化。
- **子进程门禁不是接受条件**：子进程可报告 focused tests、ruff、registry check、diff check 和 full regression，但主进程必须独立评估 diff 语义。只有主进程确认迁移、旧数据、crash replay、冲突分支和副作用边界后，产物才可进入合并。
- **基座能力必须有硬状态**：幂等、调度、artifact 写入、状态机、claim gate 这类基座能力不能只靠扫描已有 ledger 得出结论。需要唯一性或并发保护时，必须设计可审计的 artifact、reservation 或 ledger，并明确原子边界和残余风险。
- **Legacy migration 是验收项**：任何新索引、新 reservation、新 artifact family 接入旧 ledger 时，测试必须覆盖旧数据存在但新硬状态缺失的路径，确认旧数据不会绕过冲突检测、claim gate 或恢复写入。
- **源码禁用要变成机器门禁**：当 Context Pack 或 closeout 禁止某类源码写法时，必须把禁令写成 `process-hardening-check --forbidden-source-token path:token`。例如 BG/BH 类任务可显式禁用 `src/.../autonomous_flow_scheduler_action_route_auto_apply.py:'route.reason =='`，避免依赖主进程记忆。
- **基座流转不得解析 reason 改结构**：route/action/apply/output 等基座链路只能用结构化 route、action、output 或新增结构化字段决定分支；`route.reason` 等 reason 字段仍可作为解释、诊断和审计文本，但不得靠匹配自然语言文案来改写结构化 route、action 或 output。
- **真实 smoke 验证当前 contract**：真实 artifact root / CLI smoke 的职责是证明当前 contract 下的端到端行为。若测试预设与真实 route contract 不一致，应修正 Context Pack、contract 或新增结构化字段，不得把测试预设反向压到核心 route。
- **主进程修正必须反哺流程**：如果主进程在子进程通过门禁后仍修正了文件拆分、迁移边界、schema 语义或文档验收，该修正必须写入评估文档，并判断是否需要重跑同类任务。
- **Clean status closeout 是主进程门禁**：Trial AN 之后，主进程 closeout 必须运行 `process-hardening-check --require-clean-git-status --git-root .`，因为 diff/stat 检查无法覆盖 untracked 文件；命中残留时必须回到评审或重跑，而不是让子进程承担全局收尾。
