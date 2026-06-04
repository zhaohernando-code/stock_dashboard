import type {
  ShortpickCandidateView,
  ShortpickFeedbackGroup,
  ShortpickModelFeedbackItem,
  ShortpickRoundView,
  ShortpickValidationQueueItem,
  ShortpickValidationView,
} from "../types";
import { formatDate, formatPercent } from "../utils/format";

export const HORIZON_ORDER = [1, 3, 5, 10, 20];
export type ShortpickWorkspaceTab = "today" | "paper-tracking" | "validation" | "feedback" | "replay";
export const BENCHMARK_OPTIONS = [
  { label: "沪深300", value: "hs300" },
  { label: "中证1000", value: "csi1000" },
  { label: "同板块", value: "sector_equal_weight" },
];

export const SHORTPICK_WORKSPACE_TABS = new Set<ShortpickWorkspaceTab>(["today", "paper-tracking", "validation", "feedback", "replay"]);

export function priorityLabel(value: string): string {
  if (value === "cross_model_same_symbol") return "跨模型同票";
  if (value === "same_model_repeat_symbol") return "同模型重复";
  if (value === "cross_model_same_topic") return "跨模型同题材";
  if (value === "single_model_high_conviction") return "单模型高置信";
  if (value === "market_factor_default") return "策略默认";
  if (value === "market_factor_offensive") return "进攻对照";
  if (value === "market_factor_frozen_paper") return "冻结纸面策略";
  if (value === "market_factor_no_limit_chase") return "不追涨停控制";
  if (value === "market_factor_next_open_entry") return "次日开盘入场控制";
  if (value === "market_factor_top3_equal_weight") return "前三名等权组合";
  if (value === "market_factor_intraday_same_day_low_turnover_uptrend") return "14点同日低换手上升趋势";
  if (value === "momentum_10d_turnover_top3_equal_weight") return "10日动量换手 Top3 等权";
  if (value === "baseline_control") return "基线对照";
  if (value === "pending_consensus") return "等待共识";
  if (value === "tradeability_blocked") return "账户不可执行";
  if (value === "high_convergence") return "高收敛";
  if (value === "theme_convergence") return "题材收敛";
  if (value === "divergent_novel") return "发散新颖";
  if (value === "watch_only") return "观察";
  if (value === "failed_or_unusable") return "不可用";
  return "其他实验分组";
}

export function priorityColor(value: string): string {
  if (value === "cross_model_same_symbol" || value === "high_convergence") return "red";
  if (value === "cross_model_same_topic" || value === "theme_convergence") return "gold";
  if (value === "same_model_repeat_symbol" || value === "single_model_high_conviction") return "orange";
  if (value === "market_factor_default") return "green";
  if (value === "market_factor_offensive") return "cyan";
  if (value === "market_factor_frozen_paper") return "purple";
  if (value === "market_factor_no_limit_chase") return "green";
  if (value === "market_factor_next_open_entry") return "cyan";
  if (value === "market_factor_top3_equal_weight") return "geekblue";
  if (value === "market_factor_intraday_same_day_low_turnover_uptrend") return "blue";
  if (value === "momentum_10d_turnover_top3_equal_weight") return "geekblue";
  if (value === "baseline_control") return "default";
  if (value === "pending_consensus") return "gold";
  if (value === "tradeability_blocked") return "red";
  if (value === "divergent_novel") return "blue";
  if (value === "watch_only") return "default";
  if (value === "failed_or_unusable") return "red";
  return "default";
}

function looksLikeInternalKey(value?: string | null): boolean {
  return Boolean(value && /^[a-z0-9_:-]+$/i.test(value) && value.includes("_"));
}

export function modelFeedbackDisplayName(item: ShortpickModelFeedbackItem): string {
  if (item.display_model_label && !looksLikeInternalKey(item.display_model_label)) return item.display_model_label;
  if (item.model_group_key === "deepseek_v4_pro_1m" || item.provider_name === "deepseek") return "DeepSeek V4 Pro 1M";
  if (item.model_group_key === "chatgpt_5_5" || item.provider_name === "openai") return "ChatGPT 5.5";
  return "历史占位 / 不可归因样本";
}

export function channelDisplayLabel(value?: string | null): string {
  if (value === "deepseek_tool_search_lobechat_searxng_v1") return "今日联网自由选股";
  if (value === "isolated_codex_cli") return "今日 ChatGPT 自由选股";
  if (value === "historical_replay_sealed_packet_llm") return "历史密封包回放";
  if (value === "historical_replay_llm_self_distiller") return "历史自蒸馏";
  if (value === "historical_replay_momentum_pool_distiller") return "动量池蒸馏";
  if (value === "historical_replay_momentum_pool_hard_veto") return "动量池 hard-veto 控制";
  if (value === "historical_replay_momentum_pool_rejector") return "动量池 rejector 控制";
  if (!value || looksLikeInternalKey(value)) return "实验通道";
  return value;
}

export function modelFeedbackSubLabel(item: ShortpickModelFeedbackItem): string {
  if (item.executor_kind === "model_group") {
    const channelCount = item.channels?.length ?? 0;
    return channelCount > 0 ? `${channelCount} 个实验通道` : "按真实模型聚合";
  }
  return channelDisplayLabel(item.channel_label ?? item.executor_kind);
}

export function feedbackGroupDisplayLabel(title: string, group: ShortpickFeedbackGroup): string {
  if (title === "优先级表现") return priorityLabel(group.group_key);
  if (group.label && !looksLikeInternalKey(group.label)) return group.label;
  return "其他分组";
}

export function entryPriceSourceLabel(value?: string | null): string {
  if (value === "next_close") return "次日收盘买入";
  if (value === "next_open") return "次日开盘买入";
  if (value === "same_close_proxy") return "同日收盘代理";
  if (value === "same_day_intraday_current") return "14点盘中买入";
  if (!value) return "待补入场口径";
  return "其他入场口径";
}

function trendRegimeLabel(value?: string | null): string {
  if (value === "uptrend") return "上行行情";
  if (value === "downtrend") return "下行行情";
  if (value === "range_bound") return "震荡行情";
  if (value === "missing" || value === "missing_regime") return "行情待识别";
  if (!value) return "行情待补";
  return "其他行情";
}

function volatilityRegimeLabel(value?: string | null): string {
  if (value === "low_volatility") return "低波动";
  if (value === "normal_volatility") return "常规波动";
  if (value === "high_volatility") return "高波动";
  if (value === "missing") return "波动待识别";
  return "";
}

function sizeStyleRegimeLabel(value?: string | null): string {
  if (value === "balanced_size") return "大小盘均衡";
  if (value === "large_cap_lead") return "大盘占优";
  if (value === "small_cap_lead") return "小盘占优";
  if (value === "missing") return "风格待识别";
  return "";
}

export function marketRegimeDisplayLabel(item: Record<string, unknown> | string | null | undefined): string {
  if (typeof item === "string") {
    const parts = item.split(":");
    if (parts.length >= 3) {
      return [trendRegimeLabel(parts[0]), volatilityRegimeLabel(parts[1]), sizeStyleRegimeLabel(parts[2])]
        .filter(Boolean)
        .join(" · ");
    }
    return trendRegimeLabel(item);
  }
  const rawTag = String(item?.market_regime_tag ?? item?.regime_group_key ?? "");
  const rawParts = rawTag.includes(":") ? rawTag.split(":") : [];
  const trend = String(item?.trend_regime ?? rawParts[0] ?? item?.regime_group_key ?? item?.market_regime_tag ?? "");
  const volatility = String(item?.volatility_regime ?? rawParts[1] ?? "");
  const sizeStyle = String(item?.size_style_regime ?? rawParts[2] ?? "");
  const isTrendOnly = String(item?.regime_granularity ?? "") === "trend_regime" || (!rawTag.includes(":") && !volatility && !sizeStyle);
  if (isTrendOnly) return trendRegimeLabel(trend);
  return [trendRegimeLabel(trend), volatilityRegimeLabel(volatility), sizeStyleRegimeLabel(sizeStyle)]
    .filter(Boolean)
    .join(" · ") || "行情待补";
}

export function isRecognizedMarketRegimeRow(item: Record<string, unknown>): boolean {
  const value = String(item.market_regime_tag ?? item.regime_group_key ?? item.trend_regime ?? "");
  return Boolean(value) && value !== "missing" && value !== "missing_regime" && !value.includes("missing");
}

export function periodKindLabel(value?: string | null): string {
  if (value === "month") return "月度";
  if (value === "quarter") return "季度";
  if (value === "year") return "年度";
  return "周期待补";
}

export function regimeSampleCaution(sampleCount: number): string {
  if (sampleCount < 6) return "低样本";
  if (sampleCount < 12) return "观察样本";
  return "样本尚可";
}

export function statusColor(value: string): string {
  if (value === "completed" || value === "success") return "green";
  if (value === "running") return "blue";
  if (value === "failed" || value === "parse_failed" || value === "retryable_failures") return "red";
  if (value === "partial_completed" || value.startsWith("pending")) return "gold";
  return "default";
}

export function statusLabel(value: string): string {
  const labels: Record<string, string> = {
    completed: "已完成",
    running: "运行中",
    failed: "失败",
    partial_completed: "部分完成",
    retryable_failures: "失败待重跑",
    parsed: "已解析",
    parse_failed: "解析失败",
    pending_market_data: "待行情",
    pending_forward_window: "待窗口",
    pending_entry_bar: "待入场价",
    pending_benchmark_data: "待基准",
    pending_sector_mapping: "缺板块映射",
    pending_sector_peer_baseline: "待板块样本",
    suspended_or_no_current_bar: "停牌/缺行情",
    entry_unfillable_limit_up: "入场涨停不可成交",
    tradeability_uncertain: "可交易性待确认",
  };
  return labels[value] ?? "待确认";
}

export function failureCategoryLabel(value?: string | null): string {
  if (value === "retryable_search_failure") return "搜索失败，可重跑";
  if (value === "retryable_parse_failure") return "解析失败，可重跑";
  if (value === "configuration_failure") return "配置失败";
  if (value === "round_execution_failure") return "执行失败";
  return "未分类失败";
}

export function roundModelLabel(round: ShortpickRoundView): string {
  return `${round.provider_name}:${round.model_name} #${round.round_index}`;
}

export function benchmarkLabel(value: string): string {
  return BENCHMARK_OPTIONS.find((item) => item.value === value)?.label ?? "沪深300";
}

export function benchmarkMetric(
  item: ShortpickValidationView | ShortpickValidationQueueItem,
  selectedBenchmark: string,
) {
  const dimension = item.benchmark_dimensions?.[selectedBenchmark];
  if (dimension) return dimension;
  if (selectedBenchmark === "hs300") {
    return {
      benchmark_label: item.benchmark_label || "沪深300",
      benchmark_return: item.benchmark_return,
      excess_return: item.excess_return,
      status: item.benchmark_return == null ? "pending_benchmark_data" : "available",
      reason: item.pending_reason,
    };
  }
  return {
    benchmark_label: benchmarkLabel(selectedBenchmark),
    benchmark_return: null,
    excess_return: null,
    status: selectedBenchmark === "sector_equal_weight" ? "pending_sector_peer_baseline" : "pending_benchmark_data",
    reason: selectedBenchmark === "sector_equal_weight" ? "待板块样本" : "待基准数据",
  };
}

export function benchmarkPendingText(status?: string | null, reason?: string | null): string {
  if (reason) return reason;
  if (status === "pending_sector_mapping") return "缺板块映射";
  if (status === "pending_sector_peer_baseline") return "待板块样本";
  if (status === "pending_benchmark_data") return "待基准数据";
  return "待基准数据";
}

export function validationSummary(candidate: ShortpickCandidateView, selectedBenchmark: string): string {
  const completed = candidate.validations.filter((item) => item.status === "completed");
  if (!completed.length) {
    const pending = candidate.validations[0];
    return pending ? statusLabel(pending.status) : "待验证";
  }
  const shortest = completed[0];
  const metric = benchmarkMetric(shortest, selectedBenchmark);
  if (metric.status !== "available") {
    return `${shortest.horizon_days}日 个股 ${formatPercent(shortest.stock_return)} / ${benchmarkPendingText(metric.status, metric.reason)}`;
  }
  return `${shortest.horizon_days}日 个股 ${formatPercent(shortest.stock_return)} / ${metric.benchmark_label || benchmarkLabel(selectedBenchmark)}超额 ${formatPercent(metric.excess_return)}`;
}

export function validationWindowNote(item: ShortpickValidationView | ShortpickValidationQueueItem): string | null {
  if (item.status !== "pending_forward_window") return null;
  const available = item.available_forward_bars ?? 0;
  const required = item.required_forward_bars ?? item.horizon_days;
  const entry = item.entry_at ? formatDate(item.entry_at) : "入场收盘";
  return `前向K线 ${available}/${required}；入场为 ${entry}，等待第 ${required} 个后续交易日收盘。`;
}

export function replayGateLabel(value?: string | null): string {
  if (value === "ready") return "可做初步统计比较";
  if (value === "exploratory") return "探索样本";
  if (value === "not_ready") return "样本不足";
  return "样本不足";
}

export function replayGateAlertType(value?: string | null): "success" | "warning" {
  return value === "ready" ? "success" : "warning";
}

export function replayGateReasonText(value?: unknown): string {
  const reason = String(value ?? "").trim();
  if (!reason) return "";
  if (reason === "Replay sample is broad enough for aggregate readout.") {
    return "样本覆盖已足够做聚合比较。";
  }
  return reason;
}

export function replayDecisionStatusColor(value?: string | null): string {
  if (!value) return "default";
  if (value.includes("ready") || value.includes("aligned") || value.includes("tracking")) return "green";
  if (value.includes("missing") || value.includes("blocker") || value.includes("gap") || value.includes("failed") || value.includes("no_verified")) return "red";
  if (value.includes("observe") || value.includes("waiting") || value.includes("insufficient")) return "gold";
  return "blue";
}

export function replayDecisionStatusLabel(value?: string | null): string {
  if (value === "observe_only") return "只观察";
  if (value === "no_verified_advantage") return "优势不足";
  if (value === "insufficient_sample") return "样本不足";
  if (value === "paper_tracking_only") return "纸面跟踪";
  if (value === "forward_observation") return "前向观察";
  if (value === "waiting_forward_sample") return "待前向";
  if (value === "directionally_aligned") return "方向一致";
  if (value === "execution_gap") return "执行落差";
  if (value === "selection_gap") return "选股待改善";
  if (value === "production_gate_blocker") return "门槛未过";
  if (value === "drawdown_blocker") return "回撤约束";
  if (value === "sample_blocker") return "样本不足";
  if (value === "forward_sample_blocker") return "前向样本";
  if (value === "entry_assumption_blocker") return "入场假设";
  if (value === "missing_artifact") return "待产物";
  if (value === "forward_tracking_only") return "仅前向";
  if (value === "diagnostic_proxy") return "代理诊断";
  if (value === "research_backtest") return "历史研究";
  if (value === "live_forward_paper") return "纸面前向";
  return value || "待判断";
}

export function funnelBasisLabel(value?: string | null): string {
  if (value === "stock_series") return "股票池";
  if (value === "candidate_horizon_rows") return "候选-周期";
  if (value === "blocked_candidate_horizon_rows") return "不可买行";
  return value || "待补";
}

export function operationalStatus(run: { summary: Record<string, unknown>; status: string }): string {
  return String(run.summary.operational_status ?? run.status);
}

export function sourceCredibilityLabel(value?: string | null): string {
  if (value === "verified") return "来源可达";
  if (value === "reachable_restricted") return "来源受限";
  if (value === "suspicious") return "疑似占位";
  if (value === "unreachable") return "不可达";
  if (value === "missing_url") return "缺 URL";
  return "未校验";
}

export function sourceCredibilityColor(value?: string | null): string {
  if (value === "verified") return "green";
  if (value === "reachable_restricted") return "gold";
  if (value === "suspicious" || value === "unreachable" || value === "missing_url") return "red";
  return "default";
}

export function sourceAuthorityLabel(value?: string | null): string {
  const labels: Record<string, string> = {
    exchange_or_company_disclosure: "公告/交易所",
    designated_disclosure_media: "指定披露媒体",
    mainstream_financial_media: "主流财经",
    vertical_industry_media: "行业媒体",
    broker_research_or_pdf: "券商/PDF",
    community_or_forum: "社区论坛",
    aggregator_or_unknown: "聚合/未知",
  };
  return labels[value || ""] ?? "聚合/未知";
}

export function sourceSupportLabel(value?: string | null): string {
  if (value === "supported_by_source_text") return "文本支持";
  if (value === "weak_or_unverified_source_support") return "弱支持";
  return "未检查";
}

export function topicLabel(candidate: ShortpickCandidateView): string {
  const topic = candidate.topic_normalization ?? {};
  const label = typeof topic.label_zh === "string" ? topic.label_zh.trim() : "";
  if (label) return label;
  return candidate.normalized_theme || "未归类题材";
}

export function baselineFamilyLabel(value?: string | null): string {
  if (!value) return "LLM自由选股";
  if (value === "llm") return "LLM原选";
  if (value === "llm_self_distilled") return "LLM自选蒸馏";
  if (value === "llm_momentum_distilled") return "LLM动量池蒸馏";
  if (value === "diagnostic_proxy_llm") return "诊断代理";
  if (value === "random_same_tradeable_universe") return "随机";
  if (value === "random_same_market_cap_bucket") return "同市值随机";
  if (value === "momentum_volume_baseline") return "动量成交量";
  if (value === "momentum_volume_expanded_pool") return "扩大动量池";
  if (value === "llm_reject_only") return "LLM只剔除保留池";
  if (value === "llm_reject_then_momentum_rank") return "LLM剔除后动量排序";
  if (value === "random_reject_then_momentum_rank") return "随机剔除后动量排序";
  if (value === "llm_hard_veto_then_momentum_rank") return "LLM硬否决后动量排序";
  if (value === "random_hard_veto_then_momentum_rank") return "随机硬否决后动量排序";
  if (value === "llm_strict_veto_then_momentum_rank") return "LLM严格否决后动量排序";
  if (value === "random_strict_veto_then_momentum_rank") return "随机严格否决后动量排序";
  if (value === "momentum_turnover_rank") return "换手优先动量排序";
  if (value === "momentum_10d_rank") return "10日持续动量排序";
  if (value === "momentum_10d_turnover_rank") return "10日动量换手排序";
  if (value === "momentum_10d_turnover_cooldown_rank") return "10日动量换手降追高排序";
  if (value === "frozen_paper_low_turnover_uptrend_v4") return "低换手上升趋势";
  if (value === "momentum_10d_turnover_legacy_second_candidate") return "旧主线第二候选";
  if (value === "momentum_10d_amount_turnover_strong_breadth_rank2") return "强广度低追高二候选";
  if (value === "momentum_10d_turnover_top3_equal_weight") return "前三名等权组合";
  if (value === "momentum_volume_golden_cross_10_200") return "10/200日金叉过滤";
  if (value === "momentum_10d_turnover_cooldown_diversified_rank") return "分散后的动量换手";
  if (value === "momentum_continuity_turnover_rank") return "持续动量换手复合排序";
  return "其他策略";
}

export function factorDiagnosticStatusLabel(value?: string | null): string {
  if (value === "eligible") return "可用于诊断";
  if (value === "ready") return "可观察";
  if (value === "pass") return "通过";
  if (value === "fail") return "未通过";
  if (value === "not_ready") return "样本不足";
  return "样本不足";
}

export function auditStatusLabel(value?: string | null): string {
  if (value === "pass") return "通过";
  if (value === "fail") return "失败";
  if (value === "diagnostic") return "诊断";
  return "待审计";
}

export function auditStatusColor(value?: string | null): string {
  if (value === "pass") return "green";
  if (value === "fail") return "red";
  if (value === "diagnostic") return "gold";
  return "default";
}

export function auditReasonLabel(value: string): string {
  const labels: Record<string, string> = {
    future_leakage_suspected: "疑似未来信息",
    source_after_cutoff: "来源晚于截点",
    source_not_in_packet: "引用包外来源",
    unsupported_claim: "关键事实缺来源支持",
    unverified_source_time: "来源时间未验证",
    symbol_not_in_universe: "不在当日股票池",
    not_tradeable: "当日不可交易",
  };
  return labels[value] ?? "其他审计原因";
}

export function sampleScopeLabel(selectedBenchmark: string): string {
  if (selectedBenchmark === "sector_equal_weight") return "以同板块等权为超额收益口径";
  if (selectedBenchmark === "csi1000") return "以中证1000为超额收益口径";
  return "以沪深300为超额收益口径";
}

export function projectionStatusLabel(value: string): string {
  if (value === "ready") return "已就绪";
  if (value === "partial_ready") return "部分就绪";
  if (value === "insufficient_forward_sample") return "继续观察";
  if (value === "ready_for_alignment") return "可对齐";
  if (value === "missing_artifact") return "待产物";
  return value || "待判断";
}

export function projectionDecisionLabel(value: string): string {
  if (value === "eligible_by_ci_lower_bound") return "下沿为正";
  if (value === "blocked_by_ci_lower_bound") return "下沿未过";
  if (value === "continue_observation") return "继续观察";
  if (value === "review_alignment") return "检查偏离";
  return value || "待判断";
}

export function initialShortpickWorkspaceTab(): ShortpickWorkspaceTab {
  const rawTab = new URLSearchParams(window.location.search).get("shortpickTab");
  return rawTab && SHORTPICK_WORKSPACE_TABS.has(rawTab as ShortpickWorkspaceTab)
    ? rawTab as ShortpickWorkspaceTab
    : "paper-tracking";
}
