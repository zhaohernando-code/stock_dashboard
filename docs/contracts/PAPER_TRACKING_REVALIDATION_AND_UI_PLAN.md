# 修复方案：纸面追踪验证补跑 + 试验田筛选器归位 + 最新模拟交易折叠

状态：✅ 已定稿（两轮 DeepSeek 审核通过；首轮采纳 3 条 P1/P3 修正，复审确认闭环、可进入实施）
日期：2026-06-04
worktree：`worker-workspaces/stock_dashboard/20260604-fix-paper-tracking-ui-and-revalidation-b00316`

## 0. 阶段落地状态

| 步骤 | 状态 | 说明 |
|------|------|------|
| P1 验证补跑（含无数据自动补跑） | ⏳ 代码+测试完成，待合入/发布验证 | validate_recent 有界重验证循环(max_iter=10+去重+无新completed退出) + 日刷 analysis-only 也同步基准 bar；3 新测试通过；646 fast pytest + policy-audit pass；DeepSeek 可合入 |
| P2 顶部筛选器移入对应 tab | ⬜ 未开始 | 前端 |
| P3 最新模拟交易：冻结默认展示 + 本轮全量默认折叠 | ⬜ 未开始 | 前端 |
| P3b 规则模块内容默认折叠（新增需求） | ⬜ 未开始 | 前端 |
| 归档 | ⬜ 未开始 | 全部完成后 docs/contracts→docs/archive |

状态图例：⬜ 未开始 / ⏳ 进行中 / ✅ 已完成并合入 main。

## 1. 背景与已确认根因

三个问题已只读排查并经 DeepSeek 交叉验证（DeepSeek 在 #1 的"asc 排序挤出"机制有误，实际见下）：

### 问题 1：冻结策略 5 日退出最新停在 5/26 买入（现已 6/4）
- `validation_snapshots` 中冻结候选 5 日退出：最后一个 `completed` 是信号 05-22（买入 05-25，退出 06-01）；05-25 = `pending_benchmark_data`；05-26~06-03 = `pending_forward_window`。
- 个股日线已到 06-03（齐全），但**基准指数（000300/000905/000852）只到 06-02**，缺 06-03 → `pending_benchmark_data`。
- `pending_forward_window` 由 `exit_index = entry_index + horizon >= len(bars)` 触发（`shortpick_lab.py:4766`）：验证那一刻该候选前向 K 线不足 5 根。05-26 的 5 日快照 `updated_at=06-02`（当时前向仅 4 根），**06-03 新 K 线到位后未对它重验证**。
- 校正 DeepSeek 论断：`validate_recent_shortpick_runs` 的 `latest_runs` 查询是 `run_date.desc()` limit 20（最新优先，覆盖 06-03→05-25，**包含 05-26**），`pending_runs` 查询才是 `asc()` limit 20。所以"新批次被旧 pending 挤出"不成立；真实卡点是**数据到位后没有触发对应 horizon 的重算**，且基准指数滞后一天。

### 问题 2：顶部筛选器作用域错位
- 页面头部的"历史批次选择 + 起止日期"（`ShortpickLabView.tsx:741-765`）只调 `loadLab()`，仅驱动 `latestRun` → `最新模拟交易` tab 和 `TodayRunTab`。
- `纸面跟踪 / LLM历史验证 / LLM模型反馈 / 历史回放` 各 tab 用各自独立 API 加载，完全不受顶部筛选器影响。筛选器放在全局头部，造成"看起来全局、实际只管一个 tab"的误解。

### 问题 3：最新模拟交易只剩冻结策略
- `LatestSimulationTradeCard`（`ShortpickLabView.tsx:1349`）：`choiceRows = frozenRows.length ? frozenRows : fallbackRows`，`latestFrozenPaperTrackingChoices` 硬编码只取 `frozen_strategy`+`frozen_strategy_v2`，冻结有候选就永不回退到其余分组。
- 数据并未丢失：API 返回 206 条覆盖全部 5 个分组；下方"纸面跟踪记录"表（默认 `已入场`）仍能看到全分组。问题只在顶部卡片。

## 2. 修复方案

### P1：验证补跑 + 无数据时自动补跑（后端）

目标：5 日（及其余 horizon）退出窗口数据齐备后，必须自动被重算为 `completed`；缺基准/缺前向 K 线时要先自动拉取数据再补算，而不是停在 pending。

落地点（已并入 DeepSeek 审核修正，3 处加粗标 [DS]）：
1. **基准数据缺口在日刷同步层根治 [DS]**：根因要在日刷数据同步阶段消除——`phase5-daily-refresh` / `refresh-runtime-data` 的数据同步步骤必须把基准指数（000300/000905/000852/399300）刷到与个股同一最新交易日，使"个股到 06-03、基准停 06-02"不再发生。validate 内的 `sync_benchmark_index_bars` 按需补拉只作为**兜底**，不作为主修复；主修复是同步层保证基准与个股 K 线同日齐备。若 source 当日确无基准数据，记录 reason，下个 tick 重试，不静默停 pending。
2. **pending 全量补跑（循环 + 硬上限，禁止死循环）[DS]**：当前 `pending_runs` 查询 `asc()` limit 20，历史 pending 多时（market_factor 129 条 pending）较新 pending 可能排不上。改为循环补算直到"本轮无新增 completed"，但**必须有硬上限 `max_iter`（如 ≤10 轮）+ 每轮处理的 run 集合不重复**，且循环退出条件是「本轮 updated_validation_count 中新增 completed 数 == 0」或「达到 max_iter」——两者任一即停，杜绝 source 无数据时反复拉取/死循环。冻结策略+LLM 对照优先补算。
3. **无数据自动补跑触发**：`shortpick-lab-validate-recent` 每交易日盘后在个股+基准 K 线到位后跑一次（`ASHARE_SHORTPICK_VALIDATE_RECENT_AFTER_RUN=1` 已开）；发现"窗口已过但仍 pending"的候选时下一 tick 自动重试。
   - 关键判定："窗口已过但仍 pending" = `今天 - 买入日 >= horizon 个交易日` 且 snapshot 仍是 pending → 必须补算；补算前若发现个股/基准 K 线缺该区间，先拉数据（拉取也受 max_iter 上界约束）。

测试：
- 单元/契约测试：构造一个买入后已满 5 个交易日、个股 K 线齐全但 snapshot=pending_forward_window 的候选，跑补算后应变 completed。
- 构造 `pending_benchmark_data`（基准缺最新一天）场景，补算应先补基准再算出 excess_return。
- 边界：source 当日确实无数据时，状态保持 pending 但记录 reason，且不报错、下次可重试。

### P2：顶部筛选器移入对应 tab（前端）

- 把页面头部的"历史批次选择 + 起止日期 + 触发按钮"中**只服务 `loadLab()` 的筛选控件**（run-select、runDateFrom、runDateTo）从全局头部移到 `最新模拟交易`(today) tab 内部顶部。
- 全局头部只保留与所有 tab 相关的内容（标题、全局刷新按钮、运行/触发权限按钮）。
- 其余 tab 若需要自己的筛选（如 LLM历史验证已有自己的 filters），保持不动。
- 结果：筛选器的作用域与其物理位置一致，消除"全局筛选只影响一个 tab"的误解。

### P3：最新模拟交易卡片——冻结默认展示 + 本轮全量默认折叠（前端）

- `LatestSimulationTradeCard` 保留顶部冻结策略指标（frozenMetricItems）作为**默认展示主体**（这是正式跟踪主线，符合"顶部必须优先展示两个冻结策略指标"）。
- 在冻结展示下方，新增一个**默认折叠**的区块（Ant Design `Collapse`，`defaultActiveKey=[]`），展开后展示**本轮全量选股**。
  - **本轮口径按 `latestRun.id` 限定 [DS]**：用 `rows.filter(item => Number(item.run_id) === latestRun.id)`（含全部分组：冻结/LLM 对照/市场因子对照/同池随机基线），**不要**按"最新信号日"分组——后者会把不同 run 但同信号日的候选混进来。仅当 `latestRun` 缺失时，回退到 `latestPaperTrackingChoices` 的最新信号日口径。
  - 不再用"冻结优先不回退"把其余分组挡掉。
  - 折叠标题示例：`本轮全部候选（N 条，含对照组）`，N 取该 run 的全分组候选数。
- 这样默认视图干净（只冻结），但用户一键即可看到这一轮的全量选股对照，#3 的"其余消失"被解决（改为默认折叠而非永久隐藏）。

### P3b：规则模块内容默认折叠（新增需求，前端）

- 规则模块当前是 `冻结规则` / `冻结候选 v2 规则` 等 `Card` + `Descriptions` 常驻展开（`ShortpickLabView.tsx:1138` 起）。
- 改为：规则模块标题常驻，**具体内容（Descriptions、监测轨道表）默认折叠**（`Collapse defaultActiveKey=[]`），用户需要时展开。
- 范围：纸面跟踪相关的规则卡（冻结规则、冻结候选 v2 规则、市场因子对照规则等）的明细内容默认折叠；标题与一句话摘要可保留可见。

## 3. 实施顺序与风险

| 优先级 | 步骤 | 改动面 | 风险 | 验证 |
|------|------|------|------|------|
| P1 | 验证补跑 + 自愈 | `shortpick_lab.py`（validate_recent / validate_shortpick_run）、可能 run-scheduled-refresh.sh | 中（涉及数据拉取与循环补算，注意不要在 source 无数据时死循环；与 WAL/锁治理已落地，写锁不再阻塞读） | 单元/契约测试 + 真实日刷后 5/26+ 的 5 日退出变 completed |
| P2 | 筛选器移位 | `ShortpickLabView.tsx` | 低 | tsc --noEmit + 浏览器：筛选器在 today tab 内、其余 tab 无残留 |
| P3 | 卡片折叠全量 | `ShortpickLabView.tsx`、`shortpickLabPaperTracking.ts` | 低 | tsc + 浏览器：默认只冻结，展开见全分组本轮候选 |
| P3b | 规则折叠 | `ShortpickLabView.tsx` | 低 | tsc + 浏览器：规则明细默认折叠 |

## 4. 收尾要求
- P1 是 live-facing 后端逻辑：必须发布到 runtime + 重启 backend + 真实验证 5/26+ 退出补算；基准指数已刷到最新交易日。
- P2/P3/P3b 是 live-facing 前端：必须 publish + 真实 served 页面验证（tsc --noEmit 足够，无 ESLint）。
- 若改动评分/阈值/窗口/公式相关常量，跑 policy-audit（本方案预期不动业务阈值，仅补算逻辑与 UI）。
- 每步走 worktree→开发→测试→DeepSeek 审核→commit/push/合入 main/删 worktree，并更新本 plan 状态；全部完成后归档。

## 5. 待 DeepSeek 审核的疑点
1. ✅ 已闭环：循环补算加 `max_iter`（≤10）硬上限 + 退出条件「本轮新增 completed==0 或达上限」，杜绝 source 无数据时死循环（见 P1.2 [DS]）。
2. ✅ 已闭环：基准滞后根因在**日刷数据同步层**消除（个股与基准刷到同一最新交易日），validate 内补拉仅兜底（见 P1.1 [DS]）。
3. ✅ 已闭环：P3 折叠"本轮全量"按 **`latestRun.id`** 限定，不按信号日分组，避免混入不同 run（见 P3 [DS]）。
4. P3b 规则默认折叠：实施时需检查 `test_*` 是否断言规则 Descriptions 文案"可见"；若有静态测试取脚本/组件文本，断言仍成立（文本仍在 DOM，只是默认折叠），需实测确认；如断言依赖渲染可见性则同步调整。
5. P2 已确认用户明确要"直接移动到对应 tab"，不做"联动所有 tab"的更复杂方案。

（注：DeepSeek 审核后采纳 3 条 P1/P3 修正并入正文，本节疑点 1-3 已闭环。）
