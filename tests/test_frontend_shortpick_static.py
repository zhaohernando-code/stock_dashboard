import re
import unittest
from pathlib import Path

from ashare_evidence.shortpick_strategy_lab_read_model import ACTIVE_STRATEGY_CONFIG_IDS


class FrontendShortpickStaticTests(unittest.TestCase):
    def test_shortpick_strategy_lab_replaces_v2_surface(self) -> None:
        frontend_root = Path(__file__).resolve().parents[1] / "frontend" / "src"
        app_source = (frontend_root / "App.tsx").read_text(encoding="utf-8")
        mobile_source = (frontend_root / "components" / "mobile" / "MobileAppShell.tsx").read_text(encoding="utf-8")
        mobile_types_source = (frontend_root / "components" / "mobile" / "types.ts").read_text(encoding="utf-8")
        common_types_source = (frontend_root / "types" / "common.ts").read_text(encoding="utf-8")
        api_source = (frontend_root / "api" / "shortpick.ts").read_text(encoding="utf-8")
        api_index_source = (frontend_root / "api" / "index.ts").read_text(encoding="utf-8")
        component_source = (frontend_root / "components" / "ShortpickStrategyLabView.tsx").read_text(encoding="utf-8")

        self.assertIn('label: "v3模型"', app_source)
        self.assertIn('key: "shortpick-strategy-lab"', app_source)
        self.assertIn("<ShortpickStrategyLabView />", app_source)
        self.assertIn('"shortpick-strategy-lab"', common_types_source)
        self.assertIn('"shortpick-strategy-lab"', mobile_types_source)
        self.assertIn('label: "v3"', mobile_source)
        self.assertIn("<ShortpickStrategyLabView />", mobile_source)

        self.assertIn("getShortpickStrategyLabPaperTracking", api_source)
        self.assertIn("getShortpickStrategyLabHistoricalReplay", api_source)
        self.assertIn("/shortpick-strategy-lab/paper-tracking", api_source)
        self.assertIn("/shortpick-strategy-lab/historical-replay", api_source)
        self.assertNotIn("/shortpick-lab-v2/", api_source)
        self.assertIn("getShortpickStrategyLabPaperTracking", api_index_source)
        self.assertIn("getShortpickStrategyLabHistoricalReplay", api_index_source)
        paper_api_source = api_source.split("export function getShortpickStrategyLabPaperTracking()", 1)[1].split(
            "export function getShortpickStrategyLabHistoricalReplay", 1
        )[0]
        self.assertIn("operationsDashboardRequestBehavior", paper_api_source)
        history_api_source = api_source.split("export function getShortpickStrategyLabHistoricalReplay()", 1)[1]
        self.assertNotIn("sample_limit", history_api_source)

        self.assertIn('type ShortpickStrategyLabTab = "paper-tracking" | "historical-replay";', component_source)
        self.assertIn('label: "纸面追踪"', component_source)
        self.assertIn('label: "历史回放"', component_source)
        self.assertIn('readRouteParam("shortpickStrategyLabTab")', component_source)
        self.assertIn(
            'writeWorkbenchRoute({ view: "shortpick-strategy-lab", shortpickStrategyLabTab: nextTab }, "push");',
            component_source,
        )
        self.assertIn('window.addEventListener("popstate", handlePopState);', component_source)
        self.assertIn('window.removeEventListener("popstate", handlePopState);', component_source)
        self.assertIn("2026-07-08", component_source)
        self.assertIn("不允许延迟买入", component_source)
        self.assertIn("getShortpickStrategyLabPaperTracking", component_source)
        self.assertIn("getShortpickStrategyLabHistoricalReplay", component_source)
        self.assertIn("api.getShortpickStrategyLabHistoricalReplay()", component_source)
        self.assertNotIn("getShortpickPaperTracking", component_source)
        self.assertNotIn("getShortpickReplayRuns", component_source)
        self.assertNotIn("getShortpickValidationQueue", component_source)
        self.assertNotIn("getShortpickModelFeedback", component_source)
        self.assertNotIn("LLM历史验证", component_source)
        self.assertNotIn("LLM模型反馈", component_source)
        self.assertIn("const display = tracking?.paper_display;", component_source)
        self.assertIn('title={latestTrade?.title || "最新模拟交易"}', component_source)
        self.assertIn('title={strategyExplanation?.title || "策略说明"}', component_source)
        self.assertIn("PaperDisplayChartCard", component_source)
        self.assertIn("paperDisplayTableColumns", component_source)
        self.assertIn('title={table?.title || "模拟交易明细"}', component_source)
        self.assertIn("统一从 2026-07-08 起算", component_source)
        self.assertIn('if (value === "tracking_active") return "纸面追踪中";', component_source)
        self.assertIn("最新来源信号日", component_source)
        self.assertIn("数据缺口", component_source)
        self.assertIn("...(tracking?.selected_configs ?? [])", component_source)
        self.assertIn("...(tracking?.baseline_configs ?? [])", component_source)
        self.assertIn("const ACTIVE_STRATEGY_CONFIG_IDS = [", component_source)
        self.assertIn("activeStrategyRows", component_source)
        self.assertIn("活跃策略已收敛为 3 个角色", component_source)
        self.assertIn("其余策略仅保留历史归档，不再生成新计划单", component_source)
        active_ids_source = component_source.split("const ACTIVE_STRATEGY_CONFIG_IDS = [", 1)[1].split(
            "] as const;", 1
        )[0]
        self.assertEqual(set(re.findall(r'"([^"]+)"', active_ids_source)), set(ACTIVE_STRATEGY_CONFIG_IDS))

        paper_tab_source = component_source[
            component_source.index("function ShortpickStrategyLabPaperTab"):
            component_source.index("function ShortpickStrategyLabReplayTab")
        ]
        for forbidden in (
            "blocked：",
            "contract_ready：",
            "tracking?.current_status",
            "tracking?.claim_ceiling",
            "tracking?.evidence_basis",
            "tracking?.row_contract",
            "tracking?.records",
            "item.config_id",
            "item.decision_action",
            "回放补齐",
        ):
            self.assertNotIn(forbidden, paper_tab_source)
        for visible_text_match in ("contract_ready", "research_observation", "decision_action", "config_id"):
            self.assertNotRegex(paper_tab_source, rf">[^<\n{{}}]*{visible_text_match}[^<\n{{}}]*<")
        visible_text_fragments = re.findall(r">([^<\n{}]+)<", paper_tab_source)
        for visible_text in visible_text_fragments:
            self.assertNotRegex(visible_text, r"[a-z]+_[a-z_]+")
        self.assertIn('rowKey={(_item, index) => `paper-display-row-${index ?? 0}`}', paper_tab_source)

        replay_tab_source = component_source[
            component_source.index("function ShortpickStrategyLabReplayTab"):
            component_source.index("export function ShortpickStrategyLabView")
        ]
        self.assertIn("历史回放核心读数", replay_tab_source)
        self.assertIn("metric_groups", replay_tab_source)
        self.assertIn("完整历史策略指标对比", replay_tab_source)
        self.assertIn("HistoricalStrategyComparisonTable", component_source)
        for comparison_metric in (
            "total_return",
            "annualized_return",
            "final_nav_cny",
            "max_drawdown",
            "negative_month_count",
            "worst_monthly_return",
            "buy_order_count",
            "sell_order_count",
            "skipped_order_rate",
            "skipped_signal_rate",
            "turnover",
            "mean_invested_ratio",
            "p95_invested_ratio",
            "max_single_symbol_exposure_pct",
            "max_position_count",
            "tranche_count",
            "min_order_notional_cny",
            "budget_mode",
            "exit_policy",
        ):
            self.assertIn(comparison_metric, component_source)
        self.assertNotIn("decision_samples", replay_tab_source)
        self.assertNotIn("sampleColumns", replay_tab_source)
        self.assertNotIn("decision-sample", replay_tab_source)
        self.assertNotIn("决策样本", replay_tab_source)
        for visible_text_match in (
            "contract_ready",
            "research_observation",
            "true_forward_tracking",
            "historical_account_replay",
            "decision_action",
            "config_id",
        ):
            self.assertNotRegex(replay_tab_source, rf">[^<\n{{}}]*{visible_text_match}[^<\n{{}}]*<")
        replay_visible_text_fragments = re.findall(r">([^<\n{}]+)<", replay_tab_source)
        for visible_text in replay_visible_text_fragments:
            self.assertNotRegex(visible_text, r"[a-z]+_[a-z_]+")

    def test_shortpick_lab_is_independent_research_surface(self) -> None:
        frontend_root = Path(__file__).resolve().parents[1] / "frontend" / "src"
        app_source = (frontend_root / "App.tsx").read_text(encoding="utf-8")
        component_paths = [
            frontend_root / "components" / "ShortpickLabView.tsx",
            frontend_root / "components" / "shortpickLabLabels.ts",
            frontend_root / "components" / "shortpickLabPaperTracking.ts",
            frontend_root / "components" / "shortpickLabReplayMetrics.ts",
            frontend_root / "components" / "shortpickLabToday.tsx",
        ]
        component_source = "\n".join(path.read_text(encoding="utf-8") for path in component_paths)
        api_source = (frontend_root / "api" / "shortpick.ts").read_text(encoding="utf-8")

        self.assertIn('label: "试验田"', app_source)
        self.assertIn("<ShortpickLabView canTrigger={isRootUser}", app_source)
        self.assertIn("独立研究课题，不进入主推荐评分", component_source)
        self.assertIn("冻结纸面策略进入正式跟踪", component_source)
        self.assertIn("LLM 自由选股保留为对照组", component_source)
        self.assertIn("LLM纸面对照标的", component_source)
        self.assertIn("每日固定规则选1只", component_source)
        self.assertIn("市场因子对照规则", component_source)
        self.assertIn("冻结候选 v2 规则", component_source)
        self.assertIn("v2 开盘买入候选线", component_source)
        self.assertIn("冻结候选 v2", component_source)
        self.assertIn("同池随机基线", component_source)
        self.assertIn("前三名等权组合", component_source)
        self.assertIn("10/200日金叉过滤", component_source)
        self.assertIn("低换手上升趋势", component_source)
        self.assertIn("等权市场基准", component_source)
        self.assertIn("中证500", component_source)
        self.assertIn("中证1000", component_source)
        self.assertIn("指数序列未纳入本次主板样本库，不展示为0。", component_source)
        self.assertIn("每日1万元在前三名等权", component_source)
        self.assertIn("纸面跟踪记录（正式策略与对照组）", component_source)
        self.assertIn("搜索股票、代码、策略、日期", component_source)
        self.assertIn("comparePaperTrackingSignalEntryRows", component_source)
        self.assertIn("primaryPaperTrackingRows", component_source)
        self.assertIn("deprecatedPaperTrackingRows", component_source)
        self.assertIn("主表显示", component_source)
        self.assertIn("已归档 / 废弃观察桶", component_source)
        self.assertIn("退役候选与已归档移出主表", component_source)
        self.assertNotIn("组合 Ledger 回放对照", component_source)
        self.assertNotIn("combinedLedgerRows = combinedLedger?.rows ?? []", component_source)
        self.assertNotIn("后验回放行仅来自 combined_ledger artifact", component_source)
        self.assertNotIn("不并入主表 items", component_source)
        self.assertIn("strategyEvidenceBasisLabel(item.evidence_basis)", component_source)
        self.assertIn("后验前向回放", component_source)
        self.assertIn("已并入纸面跟踪记录", component_source)
        self.assertIn("item.combined_ledger_row_id || item.candidate_id", component_source)
        self.assertIn("strategyGovernanceStatusLabel(item.governance_status)", component_source)
        self.assertIn("inventory_archived", component_source)
        self.assertIn("库存归档", component_source)
        self.assertIn("inventory_archive_artifact_source", component_source)
        self.assertIn("inventory_archive_decision_count", component_source)
        self.assertIn('defaultSortOrder: "descend"', component_source)
        self.assertIn('sortDirections: ["descend", "ascend"]', component_source)
        self.assertIn("记录分组", component_source)
        self.assertNotIn("规则名称", component_source)
        self.assertIn("同股冷却过滤", component_source)
        self.assertIn("回撤/反转过滤", component_source)
        self.assertIn("重复暴露限制", component_source)
        self.assertIn("paperTrackingGroupFilterMatches(item, ledgerGroupFilter)", component_source)
        self.assertIn("paperTrackingRecordGroupLabel(item)", component_source)
        self.assertIn("入场状态", component_source)
        self.assertIn("买入口径", component_source)
        self.assertIn("机械5日已退出", component_source)
        self.assertIn("机械10日已退出", component_source)
        self.assertIn("等待10日窗口", component_source)
        self.assertIn("最新10日退出", component_source)
        self.assertIn("paperTrackingTrackExitDay(paperTrackingMechanical10dExitTrack(latestMechanical10d), latestMechanical10d)", component_source)
        self.assertIn("paperTrackingTrackReturn(paperTrackingMechanical10dExitTrack(latestMechanical10d), latestMechanical10d)", component_source)
        self.assertNotIn("latestMechanical10d ? paperTrackingExitDay(latestMechanical10d)", component_source)
        self.assertIn("止盈止损已退出", component_source)
        self.assertIn("等待退出结果", component_source)
        self.assertIn("没有符合当前筛选条件的纸面跟踪记录。", component_source)
        self.assertIn("后验验证完成前仅作为探索结果展示", component_source)
        self.assertIn("sourceCredibilityLabel", component_source)
        self.assertIn("sourceCredibilityColor", component_source)
        self.assertIn("credibility_status", component_source)
        self.assertIn("strategyGovernanceStatusLabel", component_source)
        self.assertIn("strategyGovernanceStatusColor", component_source)
        self.assertIn("strategyEvidenceBasisLabel", component_source)
        self.assertIn("strategyEvidenceBasisColor", component_source)
        self.assertIn("退役候选", component_source)
        self.assertIn("真实前向跟踪", component_source)
        self.assertIn("后验前向回放", component_source)
        self.assertIn("校验：", component_source)
        self.assertIn("主基准：", component_source)
        self.assertIn("沪深300", component_source)
        self.assertIn("超额收益", component_source)
        self.assertIn("pending_benchmark_data", component_source)
        self.assertIn("待基准", component_source)
        self.assertIn("前向K线", component_source)
        self.assertIn("重跑接口返回 404", component_source)
        self.assertIn("shortpick-feedback-summary", component_source)
        self.assertIn("shortpick-feedback-table", component_source)
        self.assertIn("model_groups", component_source)
        self.assertIn("modelFeedbackDisplayName", component_source)
        self.assertIn("channelDisplayLabel", component_source)
        self.assertIn("feedbackGroupDisplayLabel", component_source)
        self.assertIn("shortpick-benchmark-select", component_source)
        self.assertIn("shortpick-validation-card", component_source)
        self.assertIn('label: "历史回放"', component_source)
        self.assertIn('label: "最新模拟交易"', component_source)
        self.assertIn("title=\"最新模拟交易\"", component_source)
        self.assertIn("它会持续展示到下一次分析生成新的模拟交易为止", component_source)
        self.assertIn("不是按自然日“今天”临时清空或重算", component_source)
        self.assertIn("顶部必须优先展示两个冻结策略指标", component_source)
        self.assertIn("冻结策略 v1", component_source)
        self.assertIn("等待最新分析批次写入", component_source)
        self.assertIn("latestFrozenPaperTrackingChoices", component_source)
        self.assertIn('tracking_group === "frozen_strategy"', component_source)
        self.assertIn('tracking_group === "frozen_strategy_v2"', component_source)
        self.assertIn("latestPaperTrackingSignalDate", component_source)
        self.assertIn("const visibleWorkspaceTab = latestRun || activeWorkspaceTab !== \"today\"", component_source)
        self.assertIn("activeKey={visibleWorkspaceTab}", component_source)
        self.assertIn("loadMarketStudy", component_source)
        self.assertIn("历史回放主体不依赖这项重计算", component_source)
        self.assertIn("候选明细加载中", component_source)
        self.assertIn("来源清单加载中", component_source)
        self.assertIn("全局统计加载中", component_source)
        self.assertIn("严格来源", component_source)
        self.assertIn("可交易验证", component_source)
        self.assertIn("选股模式双口径对照", component_source)
        self.assertIn("逐只候选统计，用来观察选股池平均质量", component_source)
        self.assertIn("长样本5万元滚动资金曲线超额", component_source)
        self.assertIn("短窗口候选统计", component_source)
        self.assertIn("组合资金曲线", component_source)
        self.assertIn('activeWorkspaceTab === "replay"', component_source)
        self.assertIn("void loadReplay(undefined, { includeMarketStudy: true })", component_source)
        self.assertIn("历史分析结论", component_source)
        self.assertIn("可执行性漏斗", component_source)
        self.assertIn("入场假设矩阵", component_source)
        self.assertIn("14点同日口径只按日线代理展示", component_source)
        self.assertIn("稳定性、置信与归因", component_source)
        self.assertIn("长窗口策略样本", component_source)
        self.assertIn("行情切片覆盖", component_source)
        self.assertIn("确定性策略族切片，不替代 LLM 短窗口 replay", component_source)
        self.assertIn("组合置信区间", component_source)
        self.assertIn("组合时间稳定性", component_source)
        self.assertIn("组合收益归因", component_source)
        self.assertIn("股票/行业归因待全量逐笔 artifact", component_source)
        self.assertIn("非 LLM 历史组合期望", component_source)
        self.assertIn("冻结策略位置", component_source)
        self.assertIn("entryPriceSourceLabel", component_source)
        self.assertIn("marketRegimeDisplayLabel", component_source)
        self.assertIn("行情大类", component_source)
        self.assertIn("月度组合样本", component_source)
        self.assertIn("trade_regime_evidence", component_source)
        self.assertIn("交易级切片", component_source)
        self.assertIn("交易样本", component_source)
        self.assertIn("市场阶段", component_source)
        self.assertIn("行业/题材稳定性", component_source)
        self.assertIn("行业归因口径", component_source)
        self.assertIn("去最佳行业后", component_source)
        self.assertIn("下沿未过晋级线", component_source)
        self.assertIn("前向对齐", component_source)
        self.assertIn("策略治理投影", component_source)
        self.assertIn("strategy_governance_reporting", component_source)
        self.assertIn("页面不按 tracking_role 推断", component_source)
        self.assertIn("页面不会临时推导研究结论", component_source)
        self.assertIn("shortpick-replay-decision-grid", component_source)
        self.assertIn("策略收口接口当前没有可展示数据", component_source)
        self.assertIn('label: "纸面跟踪"', component_source)
        self.assertIn("PaperTrackingTab", component_source)
        self.assertNotIn('label: "今日批次"', component_source)
        self.assertNotIn("下轮股票选择", component_source)
        self.assertNotIn("当前股票选择", component_source)
        self.assertIn("getShortpickPaperTracking", api_source)
        self.assertIn("/shortpick-lab/paper-tracking", api_source)
        self.assertIn("longRunningRequestBehavior", api_source)
        self.assertIn("累计纸面收益", component_source)
        self.assertIn('className="shortpick-paper-effect-chart-head"', component_source)
        self.assertIn('className="shortpick-paper-effect-summary-tags"', component_source)
        self.assertIn('popupMatchSelectWidth={false}', component_source)
        self.assertIn('initializedDefaultStrategyRef', component_source)
        self.assertIn('strategyLabels.includes("冻结策略") ? "冻结策略"', component_source)
        self.assertIn('const [selectedRankingMetric, setSelectedRankingMetric] = useState<PaperTrackingRankingMetricKey>("meanReturn");', component_source)
        self.assertIn("PAPER_TRACKING_RANKING_METRIC_OPTIONS", component_source)
        self.assertIn('className="shortpick-paper-effect-metric-select"', component_source)
        self.assertIn("当前指标：{selectedRankingMetricLabel}", component_source)
        self.assertIn("清除图表联动筛选", component_source)
        self.assertIn("Charts remain comparative after table linkage, so they ignore record-group and exit-result filters.", component_source)
        self.assertIn("activeGroupFilter={ledgerGroupFilter}", component_source)
        self.assertIn("activeExitStateFilter={ledgerExitStateFilter}", component_source)
        self.assertIn("onClearSelection={handlePaperEffectClearSelection}", component_source)
        self.assertNotIn("累计图策略", component_source)
        self.assertIn("历史回放核心读数", component_source)
        self.assertIn("无上下文直接查询能否短投选股", component_source)
        self.assertIn("1 / 3 / 5 / 10 / 20 日", component_source)
        self.assertIn("模型与对照组比较", component_source)
        self.assertIn("封闭数据包与来源清单", component_source)
        self.assertIn("泄漏审计", component_source)
        self.assertIn("random_same_market_cap_bucket", component_source)
        self.assertIn("momentum_volume_baseline", component_source)
        self.assertIn("去最佳单票", component_source)
        self.assertIn("getShortpickReplayRuns", api_source)
        self.assertIn("/shortpick-lab/replay-runs", api_source)
        self.assertNotIn("<Segmented", component_source)
        self.assertIn('align: "center"', component_source)
        self.assertIn("/shortpick-lab/runs", api_source)
        self.assertIn("/shortpick-lab/candidates", api_source)
        self.assertNotIn("addWatchlist", component_source)
        self.assertNotIn("getStockDashboard", component_source)

    def test_local_preview_does_not_fallback_to_vite_origin_for_api(self) -> None:
        frontend_root = Path(__file__).resolve().parents[1] / "frontend" / "src"
        core_source = (frontend_root / "api" / "core.ts").read_text(encoding="utf-8")

        self.assertIn("function isLocalPreviewOrigin()", core_source)
        self.assertIn("window.location.port !== \"8000\"", core_source)
        self.assertIn("isLocalPreviewOrigin() || mountedDeploymentBase ? [] : [inferOriginBase()]", core_source)
        self.assertIn("!inferLocalBackendBase() && !mountedDeploymentBase && !basesToUse.includes(\"\")", core_source)

    def test_canonical_mounted_route_does_not_probe_root_api_fallbacks(self) -> None:
        frontend_root = Path(__file__).resolve().parents[1] / "frontend" / "src"
        core_source = (frontend_root / "api" / "core.ts").read_text(encoding="utf-8")
        dashboard_api_source = (frontend_root / "api" / "dashboard.ts").read_text(encoding="utf-8")

        self.assertIn("function isSameOriginMountedBase(base: string): boolean", core_source)
        self.assertIn("function hasMountedDeploymentBase(", core_source)
        self.assertIn("const mountedDeploymentBase = hasMountedDeploymentBase(mountedBase, locationBase);", core_source)
        self.assertIn("return !isLocalPreviewOrigin()", core_source)
        self.assertIn("isLocalPreviewOrigin() || mountedDeploymentBase ? [] : [inferOriginBase()]", core_source)
        self.assertIn("mountedDeploymentBase ? [] : [inferSiblingPortBackendBase()]", core_source)
        self.assertIn("!mountedDeploymentBase && !basesToUse.includes(\"\")", core_source)
        self.assertIn("} else if (isSameOriginMountedBase(base)) {", core_source)
        self.assertIn("urls.push(`${base}/api${normalizedPath}`);", core_source)
        self.assertIn("operationsDashboardRequestBehavior", dashboard_api_source)
        self.assertIn("'/stocks/' + encodeURIComponent(symbol) + '/dashboard',", dashboard_api_source)

    def test_workbench_route_defaults_to_shortpick_paper_tracking(self) -> None:
        frontend_root = Path(__file__).resolve().parents[1] / "frontend" / "src"
        app_source = (frontend_root / "App.tsx").read_text(encoding="utf-8")
        shortpick_source = (frontend_root / "components" / "ShortpickLabView.tsx").read_text(encoding="utf-8")
        labels_source = (frontend_root / "components" / "shortpickLabLabels.ts").read_text(encoding="utf-8")
        route_source = (frontend_root / "utils" / "route.ts").read_text(encoding="utf-8")

        self.assertIn('const DEFAULT_VIEW: ViewMode = "shortpick";', app_source)
        self.assertIn("const OPERATIONS_REVIEW_ENABLED = false;", app_source)
        self.assertIn('    : ["candidates", "stock", "shortpick", "shortpick-strategy-lab", "settings"],', app_source)
        self.assertIn("const canUseOperations = OPERATIONS_REVIEW_ENABLED;", app_source)
        self.assertIn('return rawView && VIEW_MODES.has(rawView as ViewMode) ? (rawView as ViewMode) : DEFAULT_VIEW;', app_source)
        self.assertIn('writeWorkbenchRoute({', app_source)
        self.assertIn('view,', app_source)
        self.assertIn('symbol: selectedSymbol,', app_source)
        self.assertIn('stockTab: view === "stock" ? stockActiveTab : null,', app_source)
        self.assertIn('window.addEventListener("popstate", handlePopState);', app_source)
        self.assertIn('writeWorkbenchRoute({ view: "shortpick", shortpickTab: visibleWorkspaceTab }, "replace");', shortpick_source)
        self.assertIn('writeWorkbenchRoute({ view: "shortpick", shortpickTab: key }, "push");', shortpick_source)
        self.assertIn('function loadWorkspaceTab(tab: ShortpickWorkspaceTab): void {', shortpick_source)
        self.assertIn('if (tab === "paper-tracking")', shortpick_source)
        self.assertIn('void loadPaperTracking();', shortpick_source)
        self.assertIn('loadWorkspaceTab(activeWorkspaceTab);', shortpick_source)
        self.assertNotIn('void loadLab();\n    void loadPaperTracking();\n    void loadValidationQueue(1, DEFAULT_VALIDATION_PAGE_SIZE);\n    void loadFeedback();', shortpick_source)
        self.assertIn('if (viewRef.current !== "shortpick")', app_source)
        self.assertIn("getShortpickPaperTrackingSummary", app_source)
        self.assertNotIn("void api.getShortpickPaperTracking()", app_source)
        self.assertIn("/shortpick-lab/paper-tracking/summary", (frontend_root / "api" / "shortpick.ts").read_text(encoding="utf-8"))
        self.assertIn(': "paper-tracking";', labels_source)
        self.assertIn('export function writeWorkbenchRoute(', route_source)
        self.assertIn('window.history[mode === "push" ? "pushState" : "replaceState"]', route_source)

    def test_operations_hot_paths_use_summary_and_details_not_full_dashboard(self) -> None:
        frontend_root = Path(__file__).resolve().parents[1] / "frontend" / "src"
        api_source = (Path(__file__).resolve().parents[1] / "src" / "ashare_evidence" / "api.py").read_text(encoding="utf-8")
        app_source = (frontend_root / "App.tsx").read_text(encoding="utf-8")
        dashboard_api_source = (frontend_root / "api" / "dashboard.ts").read_text(encoding="utf-8")

        self.assertIn("const operationsResult = await api.getOperationsSummary(symbol);", app_source)
        self.assertIn("const operationsResult = await api.getOperationsSummary(selectedSymbol);", app_source)
        self.assertIn('void loadOperationsDetailSections(["simulation_workspace", "portfolios"], selectedSymbol);', app_source)
        self.assertNotIn("api.getOperationsDashboard(", app_source)
        self.assertIn("export function getOperationsDashboard(sampleSymbol: string)", dashboard_api_source)
        self.assertIn("prewarm_operations_response_cache()", api_source)
        self.assertIn("start_operations_response_cache_prewarm()", api_source)
        self.assertGreaterEqual(api_source.count("store_operations_response("), 5)


if __name__ == "__main__":
    unittest.main()
