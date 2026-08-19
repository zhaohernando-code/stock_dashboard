# stock_dashboard 当前生效决定

本文件只保留仍影响生产、纸面、回测输入或研究准入的决定。任何策略探索开始前必须阅读 `docs/research/STRATEGY_RESEARCH_LEDGER.md`；失败经验、禁止重复项与下一方向只在该总纲维护。

## 生产与纸面基线

1. V3 是永久核心基线，真实优化前沿为 Rank4-only，生产外部信息权重为 `lambda=0`；研究候选不得直接替换 V3。
2. Rank5 不能生成买单，也不展示独立影子卡片；只允许低成本积累未见结果，不能自动重开。
3. 纸面追踪展示三个 V3 角色和一个外部信息对照，统一从 2026-07-08、20 万元起算，并进入同一表格、曲线和交易明细。
4. 外部信息对照只能延长已有持仓退出，不能独立创建买入；信号注册表 append-only，历史回填、重建段与真实前向必须分账。

## 个人可交易资格

1. 资格是任何打分和排序之前的硬过滤，不是分数惩罚。
2. 默认 profile 只允许普通 A 股主板；决策时点未复权价格高于 200 元剔除；未开通的创业板、科创板、北交所等关闭。
3. “开户不足一年”不自动等于证券交易经验不足一年，权限必须显式配置，不能把推测写成监管事实。
4. 历史回测、纸面追踪和 live-facing 候选共用同一 PIT eligibility snapshot，并记录每种剔除原因；禁止用未来价格或当前静态板块/ST 状态回填历史。

## 外部信息与 PIT 合同

1. 外部信息暂不进入 V3；历史回测不得临时联网，硬条件是 `available_at <= decision_cutoff`。
2. Raw 原始响应不可变；Normalized 统一 `published_at`、`first_seen_at`、`available_at` 与修订；每个决策时点冻结 PIT snapshot。
3. 无法提供必要时间谱系或不可修订声明的渠道不得晋级。个人电脑只保存高相关新闻摘要和元数据，不保存新闻正文，逻辑存储上限 2 GiB。
4. Tushare 结构化事件只能经官方 `api.tushare.pro` HTTPS 端点获取；现有事件只有公告日、没有供应商 revision ID 和日内发布时间，只属 provisional 研究输入。
5. 申万有效期行业归属解决了当前静态标签回填，但仍缺历史 `published_at/first_seen_at/revision`，不是严格生产级 PIT。

## 策略结构与验证

1. 股票自身量价与质量数据保持主信号。正面新闻不得独立触发买入；全球、板块、个股信息分别只能影响总体风险、相对排序、个股有界增量。
2. 权重按 `0 -> 有界静态权重 -> 规则动态权重 -> 受约束学习` 逐级晋升；黑箱只可作为挑战者，最终选择“一标准误以内最小权重”的稳定平台。
3. `lambda=0` 必须复现 NAV 与真实成交账本。现金释放产生的新买单、加仓挤掉后续买单、跨区间月份污染均不得计为 alpha。
4. 提前退出或延期持仓必须同时看共享现金账与冻结买入账；两本账不能同时通过时不得归因于外部信号。
5. 精确 V3 核心入口固定为 `negative_month_rank_weight_adjusted_capacity_cluster_v3_top3_20d_v1:trial-000`；`prefilter_score` 和 `v3_soft_quality` 不能冒充 `core_score`。冻结矩阵缺失记录不得用当前元数据事后补算。
6. 失败探索不保留临时实现、专项测试、重复预注册或逐日结果；只把关键结论合并进策略探索总纲，可复用数据的哈希与边界进入 retention contract。

## 权威来源

- 当前状态：`PROJECT_STATUS.json`
- 策略探索必读、失败结论与下一方向：`docs/research/STRATEGY_RESEARCH_LEDGER.md`
- 可复用数据、哈希与 claim ceiling：`docs/contracts/STRATEGY_RESEARCH_RETENTION_CONTRACT_2026-08-17.json`
- 工程与回测防回归原则：`PROCESS.md`
- 运行事实：源码、测试、runtime release manifest 与 served API
- 详细历史：Git；不得用旧报告覆盖当前总纲。
