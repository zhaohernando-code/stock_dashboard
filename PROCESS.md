# PROCESS

反回归笔记和可复用经验。状态快照见 PROJECT_STATUS.json。

## 2026-05-07

- **参数与公式治理首轮要以股票看板为边界**：常量/公式治理已经按计划收口到数据质量、信号融合、Phase 5、短投验证边界和前端状态阈值，不做全工作区一次性大迁移。稳定 contract 留代码，公式进纯函数，可调权重/阈值/窗口进入版本化 `policy_config_versions`，每次运行 payload 记录 config key/version/checksum，后续新增参数必须经过 policy audit。
- **pytest 默认边界必须是快回归**：Phase 5 日刷、`refresh-runtime-data`、真实分析流水线、seeded workspace 和发布刷新级验收不再属于默认 `python3 -m pytest`。这类任务要拆成更小的单元/契约测试；确需跑完整链路时显式走 `runtime_integration`/专项验收。当前默认 pytest 已收窄到 `162 passed, 126 deselected in 17.37s`，避免普通开发收尾被日刷量级任务拖住。
- **参数与公式治理发布记录**：实现提交 `0cd28e04cff05adcbe50bde1f9ba44045c8f02fd` 已合入 `main` 并发布到 runtime，release manifest 为 `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/releases/20260507T145446Z-0cd28e04cff0/manifest.json`，deploy verifier 为 `19 passed, 0 failed`。运行态 API `/policy-governance/active` 与 `/policy-governance/audit` 均返回 `status=pass`；真实 served 页面 `http://127.0.0.1:5173/?verify=policy-governance-final` 已验证 `运营复盘 -> 治理与验收` 展示 `参数与公式治理`、5 个 code-default active 配置、0 个硬约束失败、公式/常量清单，截图为 `output/playwright/policy-governance-runtime-final.png`。
- **短投收益反馈要进入多 benchmark 计划**：试验田后验验证不能只展示沪深300超额；已单独立项 `SHORTPICK_LAB_MULTI_BENCHMARK_FEEDBACK_PLAN.md`，目标是在收益反馈表头切换 `沪深300 / 中证1000 / 同板块等权`。同板块维度必须真实构造同行等权基准；缺中证行情、缺板块映射或同行样本不足时显示待补原因，不能用绝对收益或沪深300静默替代。
- **短投多 benchmark 落地口径**：实现不改表结构，继续让兼容字段 `benchmark_return / excess_return` 表示默认沪深300；新增 `validation_payload.benchmark_dimensions` 保存三维结果。模型反馈聚合也从同一 map 计算 `benchmark_metrics`，前端用收益反馈表头控件切换展示，不能改变候选排序、验证状态或实验边界。
- **短投多 benchmark 已发布并真实验收**：实现提交已进入 `main` 并发布到 runtime；当前成功发布 manifest 为 `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/releases/20260507T111724Z-211dc0291542/manifest.json`，deploy verifier 为 `19 passed, 0 failed`。运行态补跑 `shortpick-lab-validate-recent --days 30 --limit 20` 后，2026-05-05 批次已有 `10` 条 completed 验证快照，不再全部停在待窗口。API 验证确认 `/shortpick-lab/validation-queue` 的 `002384.SZ` 同时返回三维 benchmark：沪深300超额约 `+9.52%`、中证1000超额约 `+8.37%`、同板块 `C 制造业` 超额约 `+7.90%`；`/shortpick-lab/model-feedback` 也返回三维 `benchmark_metrics`。真实 served 页面 `http://127.0.0.1:5173/?verify=shortpick-multibenchmark` 已用 Playwright 验证 `试验田 -> 历史验证` 表头存在 `沪深300 / 中证1000 / 同板块` 切换，并且同一条 `2026-05-05 · 002384.SZ · 1日 · 已完成` 行会随切换显示不同 benchmark label 与超额收益。
- **短投收益反馈 UI、同板块同行样本和解析失败清理已发布验收**：修复提交 `77c6fab463b36fab89a90cdb2319ae3f626e62f1` 已合入 `main` 并发布到 runtime，manifest 为 `/Users/hernando_zhao/codex/runtime/projects/ashare-dashboard/output/releases/20260507T114943Z-77c6fab463b3/manifest.json`，deploy verifier 为 `19 passed, 0 failed`。收益反馈表头切换改为 AntD Select 下拉框，历史验证 page-size 下拉层级高于下方卡片；同板块基准在现有同行日线不足时会按板块代表股票池补齐并固定拉取，当前已验证 completed sector rows 为 `available=10`，不再有 `pending_sector_peer_baseline` 或 `0/2` 样本状态。`validate_shortpick_run` 会清理已被成功结果取代的 `PARSE_FAILED` 候选，计划任务的短投 daily cycle 在生成 run 后自动执行 `shortpick-lab-retry-failed`。真实 served 页面 `http://127.0.0.1:5173/?verify=shortpick-ui-peer-parse` 已用 Playwright 验证：今日批次不再显示解析失败，历史验证只有 1 个 benchmark 下拉且没有 segmented 控件，page-size 菜单完整显示 `20 / 50 / 100 / page`，切到 `同板块` 后 `002384.SZ` 行展示 `C 制造业` 10 样本基准。
- **AntD Tabs 选中态不再做胶囊圆角**：全局 Tabs 样式过去给 `.ant-tabs-tab` 和 `.ant-tabs-ink-bar` 统一加 `999px` 圆角，导致 `试验田` 等切换式 tab 的选中态变成圆角块。现在全局改为 `border-radius: 0`，并补充 `ant-tabs-card` 覆盖，避免后续 card-style Tabs 重新带回圆角。本地任务预览 `http://127.0.0.1:5174/` 已用 Chrome headless 进入 `试验田` 验证，`今日批次 / 历史验证 / 模型反馈` 三个 tab 的计算圆角均为 `0px`，截图为 `output/playwright/tabs-no-radius-shortpick-local-final.png`。
- **停牌/缺行情短投候选不能进入正常研究池**：`600958.SH 东方证券` 出现在 2026-05-06 试验田批次，是因为模型抓到了“收购上海证券 + 5月7日复牌”的公开事件催化，原始实验记录可保留；但验证层已判定信号日后无可交易入场价、最新日线只到 2026-04-17，这类 `suspended_or_no_current_bar` 样本不能继续作为正常研究池候选展示或统计。
- **短投可交易性门禁必须写回候选分桶**：后验验证发现 `pending_market_data`、`pending_entry_bar`、`suspended_or_no_current_bar`、`entry_unfillable_limit_up`、`tradeability_uncertain` 时，将候选持久标记为 `tradeability_blocked` 并计算 `display_bucket=diagnostic`；前端研究池只展示 `display_bucket=normal`，异常候选进入失败/异常诊断区，保留来源与原始模型输出留痕。
- **发布脚本不能假设新 worktree 已有前端依赖**：`scripts/publish-local-runtime.sh` 在临时干净快照或新 worktree 中运行时，`frontend/node_modules` 通常不存在，直接 `npm run build` 会在 `tsc` 上失败。发布脚本现在在 build 前检查 `frontend/node_modules/.bin/tsc` 和 `vite`，缺失时先按锁文件执行 `npm ci`；runtime 的 `scripts/start-local-frontend.sh` 也补同样检查，避免 runtime node_modules 被清理或首次启动时失败。
- **发布脚本的 repo build 必须复用 frontend env**：runtime 前端 LaunchAgent 会 source `~/.config/codex/ashare-dashboard.frontend.env` 后执行 `npm run build`，其中 PATH 会切到 Node 22。发布脚本如果不用同一 env 先构建 repo，可能用另一套 Node 产出不同 JS hash，导致 served asset parity 误报 repo/runtime 不一致。发布脚本现在在命令检查和 build 前读取同一个 frontend env。

## 2026-05-06

- **短投试验田长期运行要有历史验证工作台**：每天 10 条推荐长期积累后，最新批次视图不足以回答“之前推荐验证在哪里看”。试验田页面必须拆为 `今日批次 / 历史验证 / 模型反馈`，历史验证走服务端分页，默认 50 条，按 candidate-horizon 展示 `1/3/5/10/20` 交易日状态和收益反馈。
- **短投失败不能混入正常研究池**：`PARSE_FAILED` 与 failed round 进入失败诊断区；DeepSeek/SearXNG 无搜索结果和 JSON 解析失败归为 retryable，模型配置缺失归为 configuration failure。重跑只处理失败轮次，旧失败 artifact id 与错误原因写入 retry history，不能删除失败痕迹。
- **短投历史验证工作台发布验收记录**：实现提交 `89e0de29a640724017020dc69665bda52c6c8636` 已合入 `main` 并通过临时干净快照 `/tmp/ashare-shortpick-history-publish.XbLpCS` 发布到 runtime；release manifest 为 `/private/tmp/ashare-shortpick-history-publish.XbLpCS/output/releases/20260506T135644Z-89e0de29a640/manifest.json`，deploy verifier 为 `19 passed, 0 failed`。运行态 API 已确认 `/shortpick-lab/runs` 返回 `2026-05-06` 批次 `operational_status=retryable_failures`、`retryable_failed_round_count=1`，`/shortpick-lab/validation-queue` 返回 95 条 candidate-horizon 验证行，`/shortpick-lab/model-feedback` 返回 GPT/DeepSeek 模型反馈。Chrome headless 桌面验收已验证 localhost `http://127.0.0.1:5173/` 与 canonical `https://hernando-zhao.cn/projects/ashare-dashboard/` 均可进入 `试验田`，并显示 `今日批次 / 历史验证 / 模型反馈 / 失败诊断 / 重跑失败轮次`；截图位于 `/tmp/ashare-shortpick-history-validation.png` 与 `/tmp/ashare-shortpick-history-canonical.png`。
- **短投试验田不能只存在手动入口**：盘后 daily 既要跑主分析，也要跑短投试验田的验证闭环。`run-scheduled-refresh.sh` 的 shortpick slot 默认启用，先执行 `shortpick-lab-validate-recent` 刷新近期旧批次的行情/基准复盘，再生成当天新 run；如确需停用，显式设置 `ASHARE_ENABLE_SHORTPICK_LAB=0`。
- **每日分析状态必须暴露子任务**：用户看到“每日分析已完成”时不能掩盖试验田未跑。`/dashboard/scheduled-refresh-status` 现在返回 `components`，前端展示 `主分析 / 试验田` 各自的成功、运行、失败或待补跑状态。

## 2026-05-05

- **短投试验田必须保持旁路隔离**：`shortpick_lab` 的 run/round/candidate/consensus/validation 只能进入独立表和独立 artifact，不能回写 `Recommendation`、`ModelResult`、watchlist、候选池或 simulation auto-model。后续任何把短投结果展示到单票/候选/模拟盘主链路的改动，都需要先补 `DECISIONS.md`。
- **原生联网实验不要被统一搜索器提前收敛**：本课题的主价值是观察弱引导、原生联网、全市场自由发现是否带来结构化系统之外的增量视角。系统可以记录 sources 和 raw output，但 v1 不替模型规定关键词或材料集合。
- **收敛不是 verified**：多模型/多轮一致只能提升研究池优先级。前端和 API 不得把 `high_convergence` 直接翻译成 `verified`、买入建议或主评分置信度；后验验证窗口完成前必须保持“待验证/研究优先级”语言。
- **短投试验田发布验收记录**：实现提交 `dc249b6b7bffa3f33ead2a80cd0c1afd3687426c` 已合入 `main` 并发布到 runtime，release manifest 为 `output/releases/20260504T200424Z-dc249b6b7bff/manifest.json`，deploy verifier 为 `19 passed, 0 failed`。`GET /shortpick-lab/runs?limit=1` 返回空列表属预期，因为本轮未触发真实 GPT/DeepSeek 实验；`GET /dashboard/candidates` 仍返回主候选池原数据，未被短投结果污染。
- **短投试验田浏览器验收记录**：Safari 已验证 localhost `http://127.0.0.1:5173/` 与 canonical `https://hernando-zhao.cn/projects/ashare-dashboard/` 都显示一级入口 `试验田`，进入后可见 `短投推荐试验田`、独立研究课题/不作为交易建议/不进入主推荐评分边界文案、刷新/触发/补跑复盘控件和空批次状态。Playwright CLI 本轮因 daemon runtime 的 `GlobalRequest` 类型错误无法启动，改用 Safari 验收；结束后已运行 `scripts/cleanup-browser-automation.sh`。
- **发布脚本刷新分支仍有历史缺口**：首次发布期间 post-deploy refresh 打印 `scripts/publish-local-runtime.sh: line 204: PYTHON_BIN: unbound variable`，但构建同步、backend/frontend health、canonical/local parity 和 deploy verifier 均已通过。后续若只需要同步 docs/status 提交，可用 `ASHARE_PUBLISH_REFRESH_MODE=skip` 避开刷新分支；单独修发布脚本时应补 `PYTHON_BIN` 初始化。
- **短投实验不能长事务执行模型调用**：首次真实触发时，旧实现把 run/round 创建、GPT/DeepSeek 调用、聚合和验证放在同一个 SQLite 写事务里，导致 `/watchlist` 等普通读接口等待到前端超时，随后前端 fallback 到 Vite origin 并显示 HTML/404 类错误。修复提交 `dc27dfc871ce4bfea48c550049087b9ac7edd8ad` 改为 run 创建后立即 commit、每轮结束 commit，并让本地 preview 不再 fallback 到 `5173` origin 作为 API。发布 manifest 为 `output/releases/20260505T033059Z-dc27dfc871ce/manifest.json`，deploy verifier 为 `19 passed, 0 failed`；Safari 已确认 `http://127.0.0.1:5173/` 关注池和 `试验田` 页面恢复，`GET /watchlist` 为 200。
- **真实流程跑完才算新功能验收**：以后这类会产生真实 runtime 行为的新功能，不能只靠单测、构建、发布和页面可见判定完成；必须按约定流程至少真实执行一次，并看护到最终状态、关键副作用边界和前端展示都通过。短投试验田本次真实验收 run `shortpick:2026-05-05:20260505033458300263` 已完成：GPT/Codex 与 DeepSeek 各 5 轮共 `10/0` 成功/失败，`parse_failed=0`，生成 10 个研究候选、1 个 consensus、50 个待行情验证快照；Safari 显示 `试验田` 最近批次完成、综合优先级 `发散新颖`、候选均为 `待验证`；主 `recommendations`、`watchlist_follows`、`watchlist_entries` 对这些短投标的均未新增记录。
- **DeepSeek 官方 API 不能标记为原生联网**：真实探针已证明当前 `api.deepseek.com` 标准 API 即使带 `enable_search` 也不会提供 Web Search，旧 run `shortpick:2026-05-05:20260505033458300263` 中 DeepSeek 5 轮属于脏数据。短投默认 DeepSeek executor 改为 `deepseek_tool_search_lobechat_searxng_v1`：DeepSeek 先自主生成搜索查询，系统只用 LobeChat 的本机 SearXNG 执行查询，再把公开搜索结果喂回 DeepSeek 生成最终 JSON；若无可达来源或模型声称无法搜索，轮次必须失败并留 artifact，不能进入正常候选。

## 2026-05-04

- **已完成不能替代业务证据**：改进建议状态 `completed` 只能说明对应计划/任务已收口，不能直接让业务 gate 变为 `pass`。像“建议命中复盘覆盖”这类门禁必须重新读取真实 replay / benchmark / backtest 证据；若复盘记录、正式验证或组合补样本仍不足，即使计划任务完成也只能展示“治理计划已完成，但正式复盘口径仍待验证”的 `warn`。
- **看板不能展示过期中台任务快照**：股票看板读取改进建议时，需要用 `control_plane_task.id` 反查中台 `/api/tasks/:id` 的实时状态，并把 `publishVerified` / `workflowGates` 等状态投影到页面。控制面不可达时才保留 snapshot 状态并标记 `任务状态未实时同步`，避免本地建议文件里的旧 `blocked` 误导验收。
- **完成真值 gate 发布记录**：修复提交已合入 `main` 并发布为 `ba644dbc5f67d2606974ce7c8ed902080f427dfd`，release manifest 为 `output/releases/20260504T152200Z-ba644dbc5f67/manifest.json`，deploy verifier 为 `19 passed, 0 failed`。运行时 API 显示“建议命中复盘覆盖”为 `warn`，文案为“治理计划已完成，但正式复盘口径仍待验证”；4 只股票数据质量仍为 `pass`，`financial_data_stale` / `profile_incomplete` 未再出现。
- **长耗时按钮必须有面板内持续状态**：`重新审计` 这类会触发双模型和后端生成的动作不能只等接口返回后弹 message；点击后必须立即在当前工作面板显示 `进行中` 状态，并让按钮进入 loading/disabled。成功或失败也要保留在面板内，避免用户无法判断任务是否已经启动。
- **重新审计不能复用短请求超时**：改进建议审计实际会调用 reviewer，前端请求策略必须使用通用长耗时 timeout，而不是运营面板详情加载的短 timeout；否则用户会看到“进行中”后很快失败，真实审计仍可能在后端继续跑。
- **AntD 弹框必须走主题上下文，不用静态 confirm 兜底**：`Modal.confirm(...)` 这类静态 API 会绕开当前 React 树里的 `ConfigProvider + darkAlgorithm`，在夜间模式下容易让弹框、Select dropdown、按钮和说明文字落到不一致的 token 环境。桌面入口应统一使用 AntD `App` provider，并通过 `App.useApp()` 下发 `message` / `modal`；新增确认弹框禁止再写裸静态 `Modal.confirm(...)`。
- **暗色主题优先收口到 AntD token 链路**：修组件可读性时不要用全局 `.ant-select-dropdown`、`.ant-modal-content`、`.ant-popover-inner` 这类选择器堆补丁替代主题系统。CSS 例外只保留业务布局、业务容器或非 AntD 原生结构；AntD 原生弹框、下拉和确认交互应由 `ConfigProvider` token 和上下文 modal 承担。
- **流程回归根因必须追到 mainline containment**：本次“进入计划池”夜间弹窗修复曾经存在于任务分支 `task/stock_dashboard/20260504-dark-modal-theme`，但没有进入 `main/origin/main`，后续主线发布覆盖 runtime 后导致用户刷新仍复现。此类回归不是单纯样式问题，而是 closeout 允许 branch-local fix 被当成完成；后续必须依赖 hook/backend gate 检查任务 commit 已被 main 与 upstream 包含。
- **暗色弹框回归最终收尾记录**：修复提交 `ec81aa819fe0200a41de2225ce5832b3a1932a73` 已进入 `main/origin/main`，发布 manifest 为 `output/releases/20260504T145606Z-ec81aa819fe0/manifest.json`，deploy verifier 为 `19 passed, 0 failed`。Safari 已验证 localhost `http://127.0.0.1:5173/` 夜间模式下“进入计划池”模型选择弹框标题、说明、Select 当前值、任务说明和操作按钮可读；canonical `https://hernando-zhao.cn/projects/ashare-dashboard/` 已加载同一 runtime 页面与暗色主题。
- **验证冲突是解释优先级，不是普通指标**：RankIC 为负但正超额占比偏高时，用户首先需要知道“方向受益不等于排序能力成立”。这种冲突必须作为结构化字段从 API 保留下来，并在当前建议摘要、历史验证层、追问研究包、精简报告和移动端风险列表里排在普通风险或原始指标之前。
- **计划池提示词只能让用户审业务，不审代码**：改进建议进入中台 Plan 时，任务描述应把可审视内容限制在业务结果、风险边界、验收方式和真实外部决策。文件、字段、接口、测试命令、代码路径等实现细节由 AI 自行判断，只能作为内部参考，不能转成用户待回答问题。
- **600522 验证冲突收尾记录**：修复发布源提交 `54a0c2e18a43e54c054e5bac4bb072a08d8c370a`，release manifest 为 `output/releases/20260504T155249Z-54a0c2e18a43/manifest.json`，deploy verifier 为 `19 passed, 0 failed`。运行态 API 已确认 `historical_validation.validation_conflict`、`follow_up.research_packet.validation_conflict`、候选主风险和 copy prompt 均包含验证冲突；浏览器验收截图为 `output/playwright/600522-validation-conflict-local.png`。本轮还用中台 API 将原本模板化的计划反馈为业务可读计划，确认后续进入计划池的描述不应让用户审代码细节。

## 2026-05-03

- **数据质量 profile 完整性要复用全局板块规则**：`profile_incomplete` 不应因为历史 `profile_payload` 尚未落 `board` 字段而重复报警；只要 `board_rule()` 能根据 symbol/profile 给出已验证板块，就应作为质量检查的全局兜底。财报 freshness 仍必须来自真实财报快照或 feature snapshot，不能用调低阈值消除 `financial_data_stale`。
- **发布 parity 不应比较盘中同步计数文案**：`intraday_source_status.message` 会包含本地/canonical 各自触发同步后“新增或更新 N 根 K 线”的实时计数，属于运行时噪声。release verifier 应比较 provider/status/symbol/timeframe 等稳定结构，不应用该文案阻断无关代码发布。
- **收尾不能停在任务分支提交**：这轮漏项的根因不是发布或验收没做，而是 closeout 规范只盯住了“commit / publish / browser verify”，没有把“合回 `main` 并回到干净工作树”写成硬门禁。后续凡是用户语义接近“提交、收尾、完成”的场景，都要把最终 git 状态当成验收项：任务分支提交后，默认继续 `merge -> checkout main -> 确认 clean`；如果因 PR 流程或用户要求故意不合入，必须在回复中明确说“已提交但未合入”。
- **同源数据质量建议必须先聚合再审计**：`financial_data_stale`、`profile_incomplete` 这类公共数据链路缺口会同时影响多只股票，差异复盘不应把它们铺成一串逐股“数据质量为 warn”建议。后续建议收集应按 `degraded_sources` 签名聚合：先生成一条批量根因修复建议，修复后重新运行数据质量与改进建议审计，再把残留异常转为逐股处理。
- **旧审计快照也要读时聚合**：完整 `run_improvement_suggestion_review` 会触发双模型 reviewer，真实 runtime 上可能长时间阻塞。若只是为了消除旧 snapshot 中同源数据质量建议的重复展示，应在 `suggestion_details/summary` 读取快照时做投影聚合，而不是依赖一次新的完整审计先完成。

## 2026-05-01

- **计划池控制面边界必须先写死再开发**：这轮出现偏移的根因不是功能实现本身，而是“服务器入口”和“权威任务后端”在文档里没有被明确区分。当前约束固定为：股票看板创建 Plan 任务默认命中本机 control-plane `127.0.0.1:8787`；`/middle` 只可视为认证后的入口/观察面，不能被默认当成创建任务的 canonical backend。未来若要切远端权威后端，必须先改两边规范和运维流程，再改代码。
- **计划池动作必须创建可审视的中台 Plan 任务**：`accepted_for_plan` 不能停留在股票看板本地状态。按钮需要先让用户选择执行模型，然后通过中台 `/api/tasks` 创建 `planMode=true / approvalRequired=true` 的任务，并把页面中的建议、证据、双模型审计、最终判断和生成计划写入任务描述。中台返回的 task id 必须回写到 suggestion snapshot，方便股票页和中台互相追踪。
- **中台任务 schema 需要向前兼容新增字段**：股票看板创建任务时会传 `provider`，老的本地 SQLite `tasks` 表没有该列会导致控制面后端启动失败。`local-control-server` 的 schema 初始化必须为既有 DB 补 `tasks.provider TEXT NOT NULL DEFAULT ''`，不能只修改新建表结构。
- **公网中台验收受统一登录层约束**：无登录态 headless 浏览器访问 `https://hernando-zhao.cn/middle` 会被重定向到统一登录页，这是预期认证行为。此类场景需要至少保留本地中台 API 验收结果；若要声明公网页面可见，必须使用已登录浏览器会话或由用户侧确认。
- **deploy verifier 不能假设 shell 环境等于后端环境**：`ANTHROPIC_AUTH_TOKEN` 实际在 `~/.config/codex/ashare-dashboard.backend.env` 中，发布/验证脚本需要显式 source 后端 env 再执行 `llm_service.route_model(...)` 检查；文档和日志只记录“存在且可用”，不得记录 token 值。
- **SQLAlchemy 2.x verifier SQL 必须用 `text()`**：`Session.execute("SELECT 1")` 会在 verifier 中误报数据库不可用，正确检查是 `from sqlalchemy import text; s.execute(text("SELECT 1"))`。
- **前端 health check 不应 grep 过期品牌字符串**：构建后的 `index.html` 当前稳定信号是 `#root` 和 `assets/index-*`，不是旧的 `ashare-dashboard` 文案。verifier 应检查真实构建结构，而不是已经从 HTML 中移除的字符串。
- **持久化 recommendation payload 需要显示层向后兼容**：新闻因子生产逻辑已把 score 限制在 `[-0.98, 0.98]`，但 runtime DB 可能仍有旧 payload 的 `±1.0`。服务层和 factor card 层必须同时做用户可见钳制，避免专业用户看到“满分因子”误判为满置信。
- **发布刷新不能无限阻塞 verification**：`publish-local-runtime.sh` 现在支持 `ASHARE_PUBLISH_REFRESH_MODE=sync|async|skip`，同步刷新有 `ASHARE_PUBLISH_REFRESH_TIMEOUT_SECONDS` 外层超时；本轮最终发布使用 `skip`，因为 API 显示层修复已能直接验证当前已服务 payload。
- **最终收尾记录**：`PYTHONPATH=src python3 -m pytest -q` 为 `212 passed in 516.29s`；最终发布快照 commit 为 `a76683eb0d41ca6e6165abb429fbb4a6ceeec3f5`，runtime `latest-successful.json` 已更新；发布脚本内置 deploy verifier 为 `19 passed, 0 failed` 并输出 `VERIFICATION PASSED`；真实 Chrome served-page 验收通过，页面标题 `波段决策看板`，可见 `工作台 / 关注股票 / 复盘`，console error 为空，截图为 `output/playwright/runtime-verify.png`。

## 2026-05-02

- **运营复盘默认 tab 不能决定模拟盘是否拉取**：当前页面默认停在 `治理与验收`，而 `simulation_workspace` 过去只在切到 `模拟参数` tab 后才懒加载，导致首屏缺少模拟盘状态与双轨明细。复盘页首轮加载应保持 `summary-first`，但在 summary 成功后立即补拉 `simulation_workspace`；`portfolios`、`manual_queue` 等更重 section 仍按 tab 懒加载。
- **运营复盘模拟盘首屏拉取修复已发布并复验**：本轮通过临时快照仓 `/tmp/ashare-ops-prefetch.3XGKN1` 发布，release manifest 为 `/private/tmp/ashare-ops-prefetch.3XGKN1/output/releases/20260502T153722Z-40b27f0f1984/manifest.json`。发布脚本完成 runtime 同步、localhost 健康检查、parity verifier 与 deploy verification（`19 passed, 0 failed`）。浏览器侧复验分两路完成：1) Safari 真实登录态下访问 `https://hernando-zhao.cn/projects/ashare-dashboard/`，进入 `复盘` 后直接看到用户轨道/模型轨道与复盘卡片；2) Playwright 桌面视口访问 `http://127.0.0.1:5173/`，切到 `运营复盘` 时默认 tab 仍是 `治理与验收`，但页面已同步出现 `双轨同步模拟台`、`焦点 K 线`、`用户轨道`、`模型轨道`，无需再点击 `模拟参数` 才能看到模拟盘信息。
- **改进建议审计台的默认队列应排除已完成项**：`completed` 代表该建议已收口，不应继续占着“本周建议”默认队列造成“进入计划池”按钮灰掉但仍未出队的错觉。默认列表应只显示未完成项；若要追溯历史，需要单独提供 `已完成` 筛选，而不是把完成项继续混在待处理队列里。

## 2026-05-05

- **DeepSeek 官方 API 不能标记为原生联网短投 executor**：`/chat/completions` 路径没有 web-search 能力，`model_config.native_web_search=true` 不能只靠配置声明。短投实验的 DeepSeek 默认路径已改为 `deepseek_tool_search_lobechat_searxng_v1`：DeepSeek 先在隔离 prompt 中生成搜索计划，本机 LobeChat/SearXNG loopback 执行搜索，再把搜索证据喂回 DeepSeek 生成最终 JSON。旧的 OpenAI-compatible DeepSeek executor 在 shortpick 场景下直接 fail closed，避免无搜索能力时伪造来源。
- **脏 shortpick run 必须删除后重跑**：旧批次 `shortpick:2026-05-05:20260505033458300263` 依赖无联网 DeepSeek API，已从独立 `shortpick_lab` 表和 artifact 目录删除，不触碰 `Recommendation / ModelResult / Watchlist / PaperPortfolio` 主链路。新批次 `shortpick:2026-05-05:20260505064830869501` 已完成 10/0 轮：GPT 走 `isolated_codex_cli`，DeepSeek 走 `deepseek_tool_search_lobechat_searxng_v1`，DeepSeek 每轮都有搜索 query trace 与 SearXNG result count。
- **来源可信度当前只代表可达性与占位符拦截，不等于权威性**：新 run 的 sources integrity 结果为 `verified=41 / unreachable=4`，没有无来源 round；但是这还不是媒体/公告权威度评分。后续若提高研究质量，应在 URL 可达之后增加 domain/source authority 分层、公告/交易所/主流财经媒体优先级、以及低质量聚合站降权。
- **试验田验收必须跑完整 live flow**：本轮已发布、删除脏数据、真实触发新 run、检查 API schema、检查 DeepSeek 搜索 trace、检查 shortpick symbols 未进入 recommendations/watchlist，然后用 Safari 验证 `http://127.0.0.1:5173/` 和 `https://hernando-zhao.cn/projects/ashare-dashboard/` 均可进入 `试验田`，显示 2026-05-05 批次 10/0 完成，且页面保留“独立研究课题 / 不进入主推荐评分 / 不代表交易建议 / 未验证不得显示 verified”的边界文案。

## 2026-04-30

- **专业化改造先落证据链，再落视觉专业感**：P-1/P0 已按“可审计、可解释、受控内测 beta”方向落到代码。新增 `data_quality_snapshot`、`factor_ic_study`、`weight_sweep_study`、CSI benchmark context 和 operations summary/details，前端只消费真实后端字段；P1/P2/P3 中需要样本积累或人工批准的 horizon/权重/毕业 gate 不做运行时动态切换，也不把当前样本不足的 study 包装成结论。
- **缺新闻不是硬风险，但仍是置信天花板**：数据质量层把无新闻覆盖记为 `data_coverage_gap:news`，评分保留在 warn 区间，不单独打 fail；producer 仍保持已批准的 positive signal watch ceiling，避免“缺事件证据但价格偏强”直接暴露为强方向建议。
- **operations 首屏预算需要接口拆分**：新增 `/dashboard/operations/summary` 和 `/dashboard/operations/details`，summary 会清空 portfolios/replay/simulation_workspace 等重字段并保留 today-at-a-glance/data-quality/factor summary。旧 `/dashboard/operations` 暂保留一个兼容期。前端首屏已经改成 summary-first；进入 `模拟参数` tab 时才懒加载 `simulation_workspace`/`portfolios` 明细。
- **P-1/P0 发布验收记录**：通过临时干净快照 `/tmp/ashare-professionalization-publish.757YdN` 发布到 runtime，manifest 为 `/private/tmp/ashare-professionalization-publish.757YdN/output/releases/20260430T163756Z-ddd8a9c561ce/manifest.json`。发布脚本的同步、backend health、frontend health 都通过，但 `verify-deploy.sh` 仍因 backend env 缺 `ANTHROPIC_AUTH_TOKEN` 在 LLM 模块检查处失败。实际 served-route browser 验证通过：operations 首屏使用 `/dashboard/operations/summary`、未提前调用 full `/dashboard/operations`，切到 `模拟参数` 后才调用 `/dashboard/operations/details?section=simulation_workspace`，单票证据页展示因子权重/贡献，console error 为空。
- **P-1/P0 最终收尾验证**：`2026-05-01T01:16:03+08:00` 重新跑 `npm run build` 通过，目标回归 `tests/test_professionalization_plan.py tests/test_dashboard_views.py tests/test_phase5_holding_policy_study.py tests/test_phase5_producer_contract_study.py tests/test_phase5_holding_policy_experiments.py tests/test_phase5_horizon_study.py tests/test_api_access.py -q` 为 `54 passed`；runtime smoke 显示 operations summary `20.8KB`、`portfolios=0`、`simulation_workspace=False`，detail endpoint 可取 `simulation_workspace=True`，单票页包含 `data_quality/factor_validation/benchmark_context`。
- **事件驱动分析的外部数据必须 fail-open**：AKShare `stock_individual_info_flow` 等外部接口可能在非交易时段返回空 DataFrame、超时或抛异常。`event_analyzer._fetch_external_data()` 的所有外部调用必须在 try/except 内，失败时返回空数据而非中断整个分析流程。prompt 中 `外部实时信息` 块显示"暂无外部实时信息流数据"比让整个 refresh pipeline 崩溃合理得多。
- **新模块集成到已有 pipeline 时要保护现有流程**：CLI `_refresh_runtime_data_output` 中的事件检测和分析调用包裹在 try/except 内，确保 trigger check 或 LLM 调用失败不会阻断后续的 intraday sync、simulation step 和 Phase 2 rebuild。
- **prompt 改动必须同步更新测试里的断言字符串**：`_follow_up_payload` 中 `目标 horizon` → `目标周期`、`系统当前结论` → `系统当前建议`、`验证样本量` → `回测样本量` 三处文案调整后，`test_dashboard_views.py` 的对应断言也会断裂。每次改 prompt 文案后跑一遍相关测试确认。
- **用 Python 脚本做文件替换时注意行结构**：直接 `result = lines[:411] + [new_body + "\n"] + lines[483:]` 会把整个函数体压成一行。正确做法是把 new_body 拆成 `list[str]`，每个元素是一行（含 `\n`），再用 extend/concatenate。

## 2026-04-29

- **多账号回归要先分清“真串号”和“展示误导”**：这次 canonical 用户反馈里，后端隔离其实已经成立，`member` 的 watchlist/simulation 都是空白；真正误导来自前端把“当前账号自选”和“全局候选池”继续混在一个工作台里展示。排查顺序应先用直连或 canonical API 验证账号态，再决定是修数据层还是修呈现层。
- **`act_as` 不应跨刷新保留**：root 代看别的账号空间时，如果把 `act_as` 持久化到 storage，用户稍后回到 root 页面会误以为“原持仓消失/复盘停止”。这类空间切换更适合单页内临时状态，刷新或重开标签后默认回到 actor 自己的空间。
- **canonical member 验证不一定非靠手点 dropdown**：当浏览器自动化无法稳定选中账号切换器时，可以用真实根域签名 session 直接请求 canonical `/projects/ashare-dashboard/api/*`，再带 `X-Ashare-Act-As-Login` 验证 edge 注入和成员空间返回值。对这轮问题，这条路径足以证明 `member-a/amoeba` 的真实 canonical watchlist 为空且 simulation 仍是 draft。

- **多账号隔离落地顺序**：先把身份上下文和数据归属改完，再改前端初始化。member 一旦还沿用旧的 `loadRuntimeSettings()` 启动顺序，就会在 `/settings/runtime` 上直接 403，造成整页白屏；正确顺序必须是 `/auth/context` → root 走 `/settings/runtime`，member 走 `/runtime/overview`。
- **关注池隔离不能等于分析断流**：自选列表要按账号隔离，但 symbol 级日更/分析资格必须按所有账号 active follows 的并集判断。移除某账号关注时只能删除该账号 follow；只有最后一个 follow 消失时，才允许全局 `watchlist_entries` 失去 active tracking。
- **模拟盘空白首登约束**：member 首次进入必须拿到独立 draft session，但 `can_start` 不能在空 `watch_symbols` 上误报 true。后端要同时在 workspace controls 和 `start_simulation_session()` 上都加护栏，避免 UI 隐藏了按钮但 API 仍可启动空 session。
- **局部回归要去掉重 fixture 依赖**：当前仓里已有一组与本次任务无关的 signal-engine fixture 回归（`build_signal_artifacts -> _fusion_state(...)` 参数漂移）。新增多账号测试如果继续复用 `seed_watchlist_fixture()`，会在进本次逻辑前先被旧回归拦住；这种情况下应改成最小自包含测试，只覆盖本轮 contract。
- **移动端设置 affordance**：只读状态行不能默认带右箭头；只有真实可操作且已接 handler/API 的项目才显示导航 affordance。二态偏好优先用 `Switch`，多选或模型选择才进入二级菜单。
- **移动端滑动操作视觉**：左滑删除这类 destructive action 的红色背景只能在展开状态出现；闭合态要避免卡片抗锯齿透出红色，展开态要取消卡片相邻侧圆角，避免出现双圆角边框。滑动释放后需吞掉下一次 click，防止误打开详情。
- **浏览器自动化恢复**：Playwright CLI 验收后必须运行 `scripts/cleanup-browser-automation.sh`。清理范围只包括 `playwright-core` daemon 和 `playwright_chromiumdev_profile-*` Chrome，不能 `pkill Chrome` 误伤用户普通浏览器。
- **移动端 app 化边界**：手机端不要把 PC 工作台继续压缩或在 `App.tsx` 堆 `isMobile` JSX。正确做法是 `App.tsx` 保持数据/handler 薄入口，移动端进独立 `components/mobile/*` shell；复盘页禁止复用 PC 宽表，必须用移动端卡片/列表表达同一数据。
- **Pydantic + future annotations 陷阱**：不要同时使用 `from __future__ import annotations` 和 `TYPE_CHECKING` 导入跨模块 Pydantic 类型。Pydantic v2 的 `model_rebuild()` 使用模块自身的 `sys.modules[module].__dict__` 解析前向引用，TYPE_CHECKING-only 类型不在该命名空间中。循环依赖时在 `__init__.py` 所有模块加载后注入类型并调用 `model_rebuild()`。
- **bash 脚本拼接陷阱**：不要用 `.join("; ")` 拼接数组生成 bash 命令，多余分号（如 `do;`、`then;`）会导致语法错误。改用字符串拼接，并对产物跑 `bash -n` 检查。
- **API 错误响应 key 约定**：JSON 错误响应用 `detail` 而非 `error`，前端 `core.ts` 只提取 `payload.detail` 展示给用户。key 用错会导致前端显示裸 HTTP 状态码而非中文提示。
- **LaunchAgent 配置规范**：定时任务用 `RunAtLoad` + `StartInterval`（或 `StartCalendarInterval`），服务进程用 `RunAtLoad` + `KeepAlive`。`StartInterval=300` 无法精确命中特定时钟分钟（如 08:10），需同时配置 `StartCalendarInterval` 数组。
- **SSH 隧道自愈**：隧道重连失败时先检查远端端口是否被旧 sshd 占坑；清理脚本失败时优先排查 bash 语法。隧道进程需自愈重连循环（指数退避），不能遇错即退。

## 2026-04-28

- **live-facing 任务完成定义**：repo 改动 → 测试 → publish → runtime refresh → 真实浏览器验收。缺任一步都不能算完成。
- **浏览器验收优先用 Safari**。Chrome 出现旧缓存页/空白页/异常 profile，但 curl/health/assets 正常时，直接切 Safari 复核。
- **canonical "打不开" 三步排查**：(1) `localhost 5173/8000` 是否健康？(2) canonical 是否只是 302 回登录页？(3) `com.codex.project-tunnel.ashare-dashboard` 是否被远端旧端口占坑？
- **canonical stale 排查**：先查 tunnel / remote port ownership，不要先误判为 repo 或 runtime 代码失效。
- **DeepSeek timeout 排查**：先对照运行时 `urlopen(..., timeout=...)` 阈值，再判断 provider 故障。当前机器默认代理链路对 DeepSeek 比显式 no-proxy 更稳，不能想当然把"走代理"当根因。
- **simulation 刷新**：不允许只 restart session，必须 `restart → step → rebuild`。持续运行时用"交易时段后台 tick + 单次 anchored step"，不要复用研究刷新链路。
- **Phase 5 holding-policy artifact**：必须容忍 payload 里 legacy `backtest_artifact_id` 漂移，优先使用真实存在的 artifact。
- **historical validation**：不能复用 `as_of_data_time` 之后的 future exit bars，否则 horizon study 会被未来泄漏污染。
- **盘后 freshness 文案**：用户可见层用 `截至 MM/DD HH:MM` 快照表达，不显示原始秒数。
- **follow-up prompt**：不要把 recommendation 结论前置成"答案模板"，先给事实、验证状态和冲突要求，系统结论放最后。
- **运营复盘文案**：同一状态优先压成一条摘要，不在多个位置重复堆叠。
- **Safari 缓存**：Safari 可能保留旧标签页内存态，页面自相矛盾时先刷新再判断。
- **dirty worktree 发布**：应通过临时干净快照仓执行，manifest 路径写回 durable docs。

## 2026-04-27 之前

- **项目入口**：固定以 PROJECT_STATUS.json、DECISIONS.md 为主，不回到根目录散落 phase 文档模式。
- **"统一账号"三层边界**：谁发身份、谁消费身份、谁负责路由授权。任一层仍是单账号就不能描述为"已支持多账户"。
- **"系统能力"三层归属**：每项能力必须说明属于 Web 控制面、会话工具、还是本机 CLI/脚本，不能因中台有按钮就假设当前环境也有同样入口。
- **Phase 5 真值源**：以 runtime DB 为准，repo 本地库不再当作 live 评估的替代品。
