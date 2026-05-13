import {
  Alert,
  Button,
  Card,
  Checkbox,
  Collapse,
  Descriptions,
  Empty,
  Input,
  List,
  Progress,
  Row,
  Col,
  Select,
  Space,
  Skeleton,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
} from "antd";
import type { ColumnsType, TablePaginationConfig } from "antd/es/table";
import { ExperimentOutlined, ReloadOutlined, SafetyCertificateOutlined, SyncOutlined } from "@ant-design/icons";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import type {
  ShortpickCandidateView,
  ShortpickFeedbackGroup,
  ShortpickMarketFactorStudyResponse,
  ShortpickMarketPortfolioMetric,
  ShortpickModelFeedbackItem,
  ShortpickModelFeedbackResponse,
  ShortpickPaperTrackingItem,
  ShortpickPaperTrackingResponse,
  ShortpickReplayFeedbackResponse,
  ShortpickReplayFeedbackFamily,
  ShortpickReplaySourceResponse,
  ShortpickRoundView,
  ShortpickRunView,
  ShortpickValidationQueueItem,
  ShortpickValidationQueueResponse,
  ShortpickValidationView,
} from "../types";
import { formatDate, formatNumber, formatPercent, valueTone } from "../utils/format";

const { Paragraph, Text, Title } = Typography;
const DEFAULT_VALIDATION_PAGE_SIZE = 50;
const HORIZON_ORDER = [1, 3, 5, 10, 20];
type ShortpickWorkspaceTab = "today" | "paper-tracking" | "validation" | "feedback" | "replay";
const SHORTPICK_WORKSPACE_TABS = new Set<ShortpickWorkspaceTab>(["today", "paper-tracking", "validation", "feedback", "replay"]);
const BENCHMARK_OPTIONS = [
  { label: "沪深300", value: "hs300" },
  { label: "中证1000", value: "csi1000" },
  { label: "同板块", value: "sector_equal_weight" },
];

function priorityLabel(value: string): string {
  if (value === "cross_model_same_symbol") return "跨模型同票";
  if (value === "same_model_repeat_symbol") return "同模型重复";
  if (value === "cross_model_same_topic") return "跨模型同题材";
  if (value === "single_model_high_conviction") return "单模型高置信";
  if (value === "market_factor_default") return "策略默认";
  if (value === "market_factor_offensive") return "进攻对照";
  if (value === "market_factor_frozen_paper") return "冻结纸面策略";
  if (value === "high_convergence") return "高收敛";
  if (value === "theme_convergence") return "题材收敛";
  if (value === "divergent_novel") return "发散新颖";
  if (value === "watch_only") return "观察";
  if (value === "failed_or_unusable") return "不可用";
  return "待聚合";
}

function priorityColor(value: string): string {
  if (value === "cross_model_same_symbol" || value === "high_convergence") return "red";
  if (value === "cross_model_same_topic" || value === "theme_convergence") return "gold";
  if (value === "same_model_repeat_symbol" || value === "single_model_high_conviction") return "orange";
  if (value === "market_factor_default") return "green";
  if (value === "market_factor_offensive") return "cyan";
  if (value === "market_factor_frozen_paper") return "purple";
  if (value === "divergent_novel") return "blue";
  if (value === "watch_only") return "default";
  if (value === "failed_or_unusable") return "red";
  return "default";
}

function statusColor(value: string): string {
  if (value === "completed" || value === "success") return "green";
  if (value === "running") return "blue";
  if (value === "failed" || value === "parse_failed" || value === "retryable_failures") return "red";
  if (value === "partial_completed" || value.startsWith("pending")) return "gold";
  return "default";
}

function statusLabel(value: string): string {
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

function failureCategoryLabel(value?: string | null): string {
  if (value === "retryable_search_failure") return "搜索失败，可重跑";
  if (value === "retryable_parse_failure") return "解析失败，可重跑";
  if (value === "configuration_failure") return "配置失败";
  if (value === "round_execution_failure") return "执行失败";
  return "未分类失败";
}

function roundModelLabel(round: ShortpickRoundView): string {
  return `${round.provider_name}:${round.model_name} #${round.round_index}`;
}

function benchmarkLabel(value: string): string {
  return BENCHMARK_OPTIONS.find((item) => item.value === value)?.label ?? "沪深300";
}

function benchmarkMetric(
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

function benchmarkPendingText(status?: string | null, reason?: string | null): string {
  if (reason) return reason;
  if (status === "pending_sector_mapping") return "缺板块映射";
  if (status === "pending_sector_peer_baseline") return "待板块样本";
  if (status === "pending_benchmark_data") return "待基准数据";
  return "待基准数据";
}

function validationSummary(candidate: ShortpickCandidateView, selectedBenchmark: string): string {
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

function validationWindowNote(item: ShortpickValidationView | ShortpickValidationQueueItem): string | null {
  if (item.status !== "pending_forward_window") return null;
  const available = item.available_forward_bars ?? 0;
  const required = item.required_forward_bars ?? item.horizon_days;
  const entry = item.entry_at ? formatDate(item.entry_at) : "入场收盘";
  return `前向K线 ${available}/${required}；入场为 ${entry}，等待第 ${required} 个后续交易日收盘。`;
}

function recordValue<T>(record: Record<string, unknown> | undefined, key: string): T | undefined {
  return record?.[key] as T | undefined;
}

function horizonSortValue(value: string | number): number {
  const horizon = Number(value);
  if (!Number.isFinite(horizon)) return Number.MAX_SAFE_INTEGER;
  const index = HORIZON_ORDER.indexOf(horizon);
  return index >= 0 ? index : HORIZON_ORDER.length + horizon;
}

function sortHorizonGroups<T extends { group_key: string | number }>(groups: T[]): T[] {
  return [...groups].sort((left, right) => horizonSortValue(left.group_key) - horizonSortValue(right.group_key));
}

function sortHorizons(values: number[]): number[] {
  return [...values].sort((left, right) => horizonSortValue(left) - horizonSortValue(right));
}

function validationCoverage(run: ShortpickRunView): string {
  const completed = Number(run.summary.validation_completed_count ?? run.summary.completed_validation_count ?? 0);
  const total = Number(run.summary.validation_total_count ?? 0);
  if (total) return `${completed} / ${total}`;
  const counts = recordValue<Record<string, number>>(run.summary, "validation_status_counts") ?? {};
  const derivedTotal = Object.values(counts).reduce((sum, value) => sum + Number(value || 0), 0);
  return `${completed} / ${derivedTotal}`;
}

function primaryBenchmarkLabel(run: ShortpickRunView): string {
  const primary = recordValue<Record<string, string>>(run.summary, "primary_benchmark");
  return primary?.label || "沪深300";
}

function replayGateLabel(value?: string | null): string {
  if (value === "ready") return "可做初步统计比较";
  if (value === "exploratory") return "探索样本";
  if (value === "not_ready") return "样本不足";
  return "样本不足";
}

function replayGateAlertType(value?: string | null): "success" | "warning" {
  return value === "ready" ? "success" : "warning";
}

function replayGateReasonText(value?: unknown): string {
  const reason = String(value ?? "").trim();
  if (!reason) return "";
  if (reason === "Replay sample is broad enough for aggregate readout.") {
    return "样本覆盖已足够做聚合比较。";
  }
  return reason;
}

function loadingAwareText(loading: boolean, value: string | number | null | undefined, emptyText = "暂无数据") {
  if (loading) return <Text type="secondary">加载中</Text>;
  if (value === null || value === undefined || value === "") return <Text type="secondary">{emptyText}</Text>;
  return value;
}

function loadingAwareStrong(loading: boolean, value: string | number | null | undefined, emptyText = "暂无数据") {
  if (loading) return <strong className="shortpick-loading-value">加载中</strong>;
  if (value === null || value === undefined || value === "") return <strong className="shortpick-empty-value">{emptyText}</strong>;
  return <strong>{value}</strong>;
}

function selectedBenchmarkGroupMetric(group: ShortpickFeedbackGroup, selectedBenchmark: string) {
  const metric = group.benchmark_metrics?.[selectedBenchmark];
  return {
    meanExcessReturn: metric?.mean_excess_return ?? (selectedBenchmark === "hs300" ? group.mean_excess_return : null),
    positiveExcessRate: metric?.positive_excess_rate ?? (selectedBenchmark === "hs300" ? group.positive_excess_rate : null),
    tradableMeanExcessReturn: selectedBenchmark === "hs300" ? group.tradable_mean_excess_return : null,
    tradablePositiveExcessRate: selectedBenchmark === "hs300" ? group.tradable_positive_excess_rate : null,
    availableCount: metric?.available_count ?? group.completed_official_sample_count ?? group.completed_validation_count,
    tradableAvailableCount: group.completed_tradable_sample_count ?? group.completed_validation_count,
    pendingReasons: metric?.pending_reasons ? Object.keys(metric.pending_reasons) : [],
  };
}

function operationalStatus(run: ShortpickRunView): string {
  return String(run.summary.operational_status ?? run.status);
}

function sourceCredibilityLabel(value?: string | null): string {
  if (value === "verified") return "来源可达";
  if (value === "reachable_restricted") return "来源受限";
  if (value === "suspicious") return "疑似占位";
  if (value === "unreachable") return "不可达";
  if (value === "missing_url") return "缺 URL";
  return "未校验";
}

function sourceCredibilityColor(value?: string | null): string {
  if (value === "verified") return "green";
  if (value === "reachable_restricted") return "gold";
  if (value === "suspicious" || value === "unreachable" || value === "missing_url") return "red";
  return "default";
}

function sourceAuthorityLabel(value?: string | null): string {
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

function sourceSupportLabel(value?: string | null): string {
  if (value === "supported_by_source_text") return "文本支持";
  if (value === "weak_or_unverified_source_support") return "弱支持";
  return "未检查";
}

function topicLabel(candidate: ShortpickCandidateView): string {
  const topic = candidate.topic_normalization ?? {};
  const label = typeof topic.label_zh === "string" ? topic.label_zh.trim() : "";
  if (label) return label;
  return candidate.normalized_theme || "未归类题材";
}

function baselineFamilyLabel(value?: string | null): string {
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

function factorDiagnosticStatusLabel(value?: string | null): string {
  if (value === "eligible") return "可用于诊断";
  if (value === "ready") return "可观察";
  if (value === "pass") return "通过";
  if (value === "fail") return "未通过";
  if (value === "not_ready") return "样本不足";
  return "样本不足";
}

function auditStatusLabel(value?: string | null): string {
  if (value === "pass") return "通过";
  if (value === "fail") return "失败";
  if (value === "diagnostic") return "诊断";
  return "待审计";
}

function auditStatusColor(value?: string | null): string {
  if (value === "pass") return "green";
  if (value === "fail") return "red";
  if (value === "diagnostic") return "gold";
  return "default";
}

function auditReasonLabel(value: string): string {
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

function sampleScopeLabel(selectedBenchmark: string): string {
  if (selectedBenchmark === "sector_equal_weight") return "以同板块等权为超额收益口径";
  if (selectedBenchmark === "csi1000") return "以中证1000为超额收益口径";
  return "以沪深300为超额收益口径";
}

function marketPortfolioMetric(
  study: ShortpickMarketFactorStudyResponse | null,
  period: "train" | "holdout" | "replay_window" | "all",
  strategy: string,
): ShortpickMarketPortfolioMetric | null {
  return study?.portfolio_summary?.[period]?.[strategy] ?? null;
}

function frozenStrategy(study: ShortpickMarketFactorStudyResponse | null): Record<string, unknown> {
  return recordValue<Record<string, unknown>>(study ? (study as unknown as Record<string, unknown>) : undefined, "frozen_paper_strategy") ?? {};
}

function frozenStrategyEvidence(study: ShortpickMarketFactorStudyResponse | null): Record<string, unknown> {
  return recordValue<Record<string, unknown>>(frozenStrategy(study), "evidence") ?? {};
}

function frozenStrategySummary(study: ShortpickMarketFactorStudyResponse | null): Record<string, unknown> {
  return recordValue<Record<string, unknown>>(frozenStrategyEvidence(study), "summary") ?? {};
}

function frozenStrategyDataScope(study: ShortpickMarketFactorStudyResponse | null): Record<string, unknown> {
  return recordValue<Record<string, unknown>>(frozenStrategyEvidence(study), "data_scope") ?? {};
}

function frozenStrategyProductionEvidence(study: ShortpickMarketFactorStudyResponse | null): Record<string, unknown> {
  return recordValue<Record<string, unknown>>(frozenStrategyEvidence(study), "production_evidence") ?? {};
}

function frozenStrategyPaperControls(study: ShortpickMarketFactorStudyResponse | null): Record<string, Record<string, unknown>> {
  return recordValue<Record<string, Record<string, unknown>>>(frozenStrategyEvidence(study), "paper_control_summaries") ?? {};
}

function frozenBenchmarkReferences(study: ShortpickMarketFactorStudyResponse | null): Record<string, Record<string, unknown>> {
  return recordValue<Record<string, Record<string, unknown>>>(frozenStrategyEvidence(study), "benchmark_references") ?? {};
}

function indexBenchmarkReferenceText(indexRefs: Record<string, Record<string, unknown>>): string {
  const labels: Array<[string, string]> = [
    ["000300.SH", "沪深300"],
    ["000905.SH", "中证500"],
    ["000852.SH", "中证1000"],
  ];
  const available = labels
    .filter(([symbol]) => Boolean(indexRefs[symbol]?.available))
    .map(([symbol, label]) => `${label} ${formatPercent(Number(indexRefs[symbol]?.total_return ?? 0))}`);
  return available.length ? available.join(" · ") : "指数序列未纳入本次主板样本库，不展示为0。";
}

type ReplayFamilyDisplayRow = ShortpickReplayFeedbackFamily & {
  display_source?: "candidate_replay" | "portfolio_backtest";
  display_key?: string;
  display_label?: string;
  display_metric_label?: string;
  display_value?: number | null;
  display_note?: string;
  display_trade_count?: number | null;
  display_total_return?: number | null;
  display_max_drawdown?: number | null;
};

function replayPortfolioControlFamilyRows(study: ShortpickMarketFactorStudyResponse | null): ReplayFamilyDisplayRow[] {
  const controls = frozenStrategyPaperControls(study);
  const controlConfigs = [
    {
      strategy: "low_turnover_20d_uptrend_liquid_top120",
      family: "frozen_paper_low_turnover_uptrend_v4",
      label: "低换手上升趋势",
      note: "组合回测：当前冻结纸面主策略",
    },
    {
      strategy: "ret10_turnover_second_market_positive_cooldown",
      family: "momentum_10d_turnover_legacy_second_candidate",
      label: "旧主线第二候选",
      note: "组合回测：旧冻结主线，保留为真实纸面对照",
    },
    {
      strategy: "ret10_turnover_second_market_positive_cooldown_stop8",
      family: "momentum_10d_turnover_legacy_second_candidate_stop8",
      label: "旧主线第二候选加止损",
      note: "组合回测：旧冻结主线加8%收盘止损",
    },
    {
      strategy: "ret10_amount_turnover_strong_breadth_rank2_stop12",
      family: "momentum_10d_amount_turnover_strong_breadth_rank2",
      label: "强广度低追高二候选",
      note: "组合回测：市场强广度时取低追高二候选",
    },
    {
      strategy: "ret10_turnover_top3_market_positive_cooldown_equal_weight",
      family: "momentum_10d_turnover_top3_equal_weight",
      label: "前三名等权组合",
      note: "组合回测：每日1万元在前三名等权",
    },
    {
      strategy: "momentum_volume_golden_cross_10_200",
      family: "momentum_volume_golden_cross_10_200",
      label: "10/200日金叉过滤",
      note: "组合回测：只选当日金叉标的",
    },
    {
      strategy: "ret10_turnover",
      family: "momentum_10d_turnover_rank",
      label: "10日动量换手首位",
      note: "组合回测：原始进攻动量换手首位",
    },
    {
      strategy: "ret10_turnover_cooldown",
      family: "momentum_10d_turnover_cooldown_rank",
      label: "10日动量换手降追高",
      note: "组合回测：动量换手叠加当日追高惩罚",
    },
  ];
  return controlConfigs.flatMap((config) => {
    const summary = recordValue<Record<string, unknown>>(controls[config.strategy], "summary") ?? {};
    if (!Object.keys(summary).length) return [];
    const tradeCount = Number(summary.trade_count ?? 0);
    const excessReturn = recordValue<number>(summary, "excess_total_return");
    const totalReturn = recordValue<number>(summary, "total_return");
    const maxDrawdown = recordValue<number>(summary, "max_drawdown");
    return [{
      baseline_family: config.family,
      label: config.label,
      candidate_count: tradeCount,
      official_sample_count: tradeCount,
      completed_official_sample_count: tradeCount,
      validation_by_horizon: [{
        group_key: "long_sample",
        label: "长样本",
        sample_count: tradeCount,
        official_sample_count: tradeCount,
        completed_validation_count: tradeCount,
        completed_official_sample_count: tradeCount,
        mean_stock_return: totalReturn,
        mean_excess_return: excessReturn,
        trimmed_mean_excess_return: null,
        positive_excess_rate: null,
        max_drawdown: maxDrawdown,
        max_favorable_return: null,
        status_counts: { completed: tradeCount },
      }],
      robustness_metrics: {},
      display_source: "portfolio_backtest",
      display_key: `portfolio:${config.strategy}`,
      display_label: config.label,
      display_metric_label: "长样本超额",
      display_value: excessReturn,
      display_note: config.note,
      display_trade_count: tradeCount,
      display_total_return: totalReturn,
      display_max_drawdown: maxDrawdown,
    }];
  });
}

function replayFamilyDisplayRows(
  feedback: ShortpickReplayFeedbackResponse | null,
  study: ShortpickMarketFactorStudyResponse | null,
): ReplayFamilyDisplayRow[] {
  const replayRows = (feedback?.families ?? []).map((family) => ({
    ...family,
    display_source: "candidate_replay" as const,
  }));
  const portfolioRows = replayPortfolioControlFamilyRows(study);
  return [...replayRows, ...portfolioRows];
}

function replayFamilyMetric(
  family: ReplayFamilyDisplayRow,
  selectedBenchmark: string,
): {
  value?: number | null;
  tradableValue?: number | null;
  label: string;
  sampleCount: number;
  tradableSampleCount: number;
  note?: string;
} {
  if (family.display_source === "portfolio_backtest") {
    return {
      value: family.display_value,
      tradableValue: family.display_value,
      label: family.display_metric_label ?? "长样本超额",
      sampleCount: Number(family.display_trade_count ?? family.completed_official_sample_count ?? 0),
      tradableSampleCount: Number(family.display_trade_count ?? family.completed_tradable_sample_count ?? 0),
      note: family.display_note,
    };
  }
  const horizon5 = family.validation_by_horizon.find((group) => String(group.group_key) === "5");
  const metric = horizon5?.benchmark_metrics?.[selectedBenchmark];
  return {
    value: metric?.mean_excess_return ?? horizon5?.mean_excess_return,
    tradableValue: selectedBenchmark === "hs300" ? horizon5?.tradable_mean_excess_return : null,
    label: "5日平均超额",
    sampleCount: Number(horizon5?.completed_official_sample_count ?? 0),
    tradableSampleCount: Number(horizon5?.completed_tradable_sample_count ?? 0),
  };
}

type StrategyDualTestConfig = {
  key: string;
  label: string;
  replayFamily?: string;
  marketStrategy?: string;
  portfolioStrategy?: string;
  note: string;
};

const STRATEGY_DUAL_TEST_CONFIGS: StrategyDualTestConfig[] = [
  {
    key: "low_turnover_uptrend",
    label: "低换手上升趋势",
    marketStrategy: "low_turnover_20d_uptrend_liquid_top120",
    portfolioStrategy: "low_turnover_20d_uptrend_liquid_top120",
    note: "主策略；候选侧看同公式逐条收益，组合侧看5万滚动资金曲线。",
  },
  {
    key: "momentum_volume",
    label: "动量成交量",
    replayFamily: "momentum_volume_baseline",
    marketStrategy: "base",
    note: "原始动量成交额池；候选回放有封闭来源窗口，组合侧用市场因子同日组合。",
  },
  {
    key: "ret10_turnover",
    label: "10日动量换手复合排序",
    replayFamily: "momentum_10d_turnover_rank",
    marketStrategy: "ret10_turnover",
    portfolioStrategy: "ret10_turnover",
    note: "进攻动量口径；候选平均和账户资金曲线分别回答不同问题。",
  },
  {
    key: "ret10_turnover_cooldown",
    label: "10日动量换手降追高",
    replayFamily: "momentum_10d_turnover_cooldown_rank",
    marketStrategy: "ret10_turnover_cooldown",
    portfolioStrategy: "ret10_turnover_cooldown",
    note: "在10日动量换手基础上惩罚当日过热。",
  },
  {
    key: "ret10_amount_turnover_rank2",
    label: "强广度低追高二候选",
    marketStrategy: "ret10_amount_turnover_cooldown",
    portfolioStrategy: "ret10_amount_turnover_strong_breadth_rank2_stop12",
    note: "组合侧包含市场强度条件、第二候选和12%止损；候选侧只展示基础排序逐条验证。",
  },
  {
    key: "top3_equal_weight",
    label: "前三名等权组合",
    marketStrategy: "ret10_turnover",
    portfolioStrategy: "ret10_turnover_top3_market_positive_cooldown_equal_weight",
    note: "组合专属分散变体；候选侧用基础10日动量换手逐条验证作参照。",
  },
  {
    key: "golden_cross",
    label: "10/200日金叉过滤",
    marketStrategy: "momentum_volume_golden_cross_10_200",
    portfolioStrategy: "momentum_volume_golden_cross_10_200",
    note: "信号触发次数少，适合作为低频过滤参考。",
  },
  {
    key: "legacy_second",
    label: "旧主线第二候选",
    marketStrategy: "ret10_turnover",
    portfolioStrategy: "ret10_turnover_second_market_positive_cooldown_stop8",
    note: "组合侧包含市场转正、不过热、第二候选和8%止损；候选侧用基础排序作参照。",
  },
];

type StrategyMetricDisplay = {
  value?: number | null;
  secondaryValue?: number | null;
  secondaryLabel?: string;
  sampleCount?: number | null;
  secondarySampleCount?: number | null;
  label: string;
  detail?: string;
  source: string;
  exact: boolean;
};

function marketStudyPeriodMetric(
  study: ShortpickMarketFactorStudyResponse | null,
  strategy: string | undefined,
  period: string,
  horizon = "5",
): StrategyMetricDisplay | null {
  if (!study || !strategy) return null;
  const summary = study.period_summary?.[period]?.[strategy];
  if (!summary) return null;
  const byHorizon = recordValue<Record<string, Record<string, unknown>>>(summary, "by_horizon") ?? {};
  const block = byHorizon[horizon] ?? {};
  const value = recordValue<number>(block, "mean_net_excess_return") ?? recordValue<number>(summary, "mean_net_excess_return");
  const trimmed = recordValue<number>(block, "trimmed_mean_net_excess_return") ?? recordValue<number>(summary, "trimmed_mean_net_excess_return");
  const completed = recordValue<number>(block, "completed_count") ?? recordValue<number>(summary, "completed_count");
  const selected = recordValue<number>(summary, "selected_symbol_day_count");
  return {
    value,
    secondaryValue: trimmed,
    secondaryLabel: "去极值均值",
    sampleCount: completed,
    secondarySampleCount: selected,
    label: `短窗口${horizon}日逐候选平均超额`,
    detail: `候选 ${formatNumber(Number(completed ?? 0))} · 入选股票日 ${formatNumber(Number(selected ?? 0))}`,
    source: period === "replay_window" ? "短窗口候选统计" : "样本外候选统计",
    exact: true,
  };
}

function marketStudyPortfolioMetricDisplay(
  study: ShortpickMarketFactorStudyResponse | null,
  strategy: string | undefined,
  period: string,
  horizon = "5",
): StrategyMetricDisplay | null {
  if (!study || !strategy) return null;
  const summary = study.portfolio_summary?.[period]?.[strategy];
  if (!summary) return null;
  const block = summary.by_horizon?.[horizon] ?? {};
  const value = recordValue<number>(block, "mean_net_excess_return") ?? summary.mean_net_excess_return;
  const trimmed = recordValue<number>(block, "trimmed_mean_net_excess_return") ?? summary.trimmed_mean_net_excess_return;
  const portfolioCount = recordValue<number>(block, "portfolio_count") ?? summary.portfolio_count;
  return {
    value,
    secondaryValue: trimmed,
    secondaryLabel: "去极值均值",
    sampleCount: portfolioCount,
    secondarySampleCount: summary.completed_member_count,
    label: `短窗口${horizon}日同日组合平均超额`,
    detail: `组合 ${formatNumber(Number(portfolioCount ?? 0))} · 成员 ${formatNumber(Number(summary.completed_member_count ?? 0))}`,
    source: period === "replay_window" ? "短窗口同日组合统计" : "样本外同日组合统计",
    exact: true,
  };
}

function replayCandidateMetricDisplay(
  feedback: ShortpickReplayFeedbackResponse | null,
  familyKey: string | undefined,
  selectedBenchmark: string,
): StrategyMetricDisplay | null {
  if (!feedback || !familyKey) return null;
  const family = feedback.families.find((item) => item.baseline_family === familyKey);
  if (!family) return null;
  const metric = replayFamilyMetric({ ...family, display_source: "candidate_replay" }, selectedBenchmark);
  return {
    value: metric.value,
    secondaryValue: metric.tradableValue,
    secondaryLabel: "可交易口径",
    sampleCount: metric.sampleCount,
    secondarySampleCount: metric.tradableSampleCount,
    label: `封闭回放${metric.label}`,
    detail: `严格来源 ${formatNumber(metric.sampleCount)} · 可交易 ${formatNumber(metric.tradableSampleCount)}`,
    source: "短窗口逐候选统计",
    exact: true,
  };
}

function rollingPortfolioMetricDisplay(
  study: ShortpickMarketFactorStudyResponse | null,
  strategy: string | undefined,
): StrategyMetricDisplay | null {
  if (!study || !strategy) return null;
  const control = frozenStrategyPaperControls(study)[strategy];
  const summary = recordValue<Record<string, unknown>>(control, "summary") ?? {};
  if (!Object.keys(summary).length) return null;
  return {
    value: recordValue<number>(summary, "excess_total_return"),
    secondaryValue: recordValue<number>(summary, "total_return"),
    secondaryLabel: "组合总收益",
    sampleCount: recordValue<number>(summary, "trade_count"),
    secondarySampleCount: recordValue<number>(summary, "day_count"),
    label: "长样本5万元滚动资金曲线超额",
    detail: `交易 ${formatNumber(Number(summary.trade_count ?? 0))} · 覆盖 ${formatNumber(Number(summary.day_count ?? 0))} 个交易日 · 最大回撤 ${formatPercent(recordValue<number>(summary, "max_drawdown"))}`,
    source: "长样本账户路径回测",
    exact: true,
  };
}

function StrategyMetricCell({ metric }: { metric: StrategyMetricDisplay | null }) {
  if (!metric) {
    return (
      <Space direction="vertical" size={0}>
        <Tag color="red">统计缺失</Tag>
        <Text type="secondary">该策略缺少预计算统计，请补齐历史回放 artifact。</Text>
      </Space>
    );
  }
  const showSecondary = metric.secondaryValue !== undefined
    && metric.secondaryValue !== null
    && (metric.value === undefined || metric.value === null || Math.abs(Number(metric.secondaryValue) - Number(metric.value)) > 0.000001);
  return (
    <Space direction="vertical" size={0}>
      <Text className={`value-${valueTone(metric.value)}`}>{formatPercent(metric.value)}</Text>
      <Text type="secondary">{metric.label}</Text>
      {showSecondary ? (
        <Text type="secondary">{metric.secondaryLabel ?? "补充指标"} {formatPercent(metric.secondaryValue)}</Text>
      ) : null}
      <Text type="secondary">{metric.detail}</Text>
      <Text type="secondary">{metric.source}</Text>
    </Space>
  );
}

function ReplayDualTestMatrix({
  feedback,
  marketStudy,
  selectedBenchmark,
  loading,
}: {
  feedback: ShortpickReplayFeedbackResponse | null;
  marketStudy: ShortpickMarketFactorStudyResponse | null;
  selectedBenchmark: string;
  loading: boolean;
}) {
  const rows = STRATEGY_DUAL_TEST_CONFIGS.map((config) => {
    const replayMetric = replayCandidateMetricDisplay(feedback, config.replayFamily, selectedBenchmark);
    const marketCandidate = marketStudyPeriodMetric(marketStudy, config.marketStrategy, "replay_window");
    const rollingPortfolio = rollingPortfolioMetricDisplay(marketStudy, config.portfolioStrategy);
    const marketPortfolio = marketStudyPortfolioMetricDisplay(marketStudy, config.marketStrategy, "replay_window");
    return {
      ...config,
      candidateMetric: replayMetric ?? marketCandidate,
      portfolioMetric: rollingPortfolio ?? marketPortfolio,
      candidateSourceIsProxy: !replayMetric && Boolean(marketCandidate),
      portfolioSourceIsProxy: !rollingPortfolio && Boolean(marketPortfolio),
    };
  });
  return (
    <div className="shortpick-dual-test-matrix">
      <Space direction="vertical" size={2}>
        <Title level={5}>选股模式双口径对照</Title>
        <Text type="secondary">每一行是同一个选股模式。左侧是短窗口内入选股票的平均表现，右侧是按5万元本金滚动买卖形成的长样本账户结果。</Text>
        <Text type="secondary">两个数字的时间范围和统计对象不同：候选平均用于判断选股池质量，资金曲线用于观察真实执行后的账户路径。</Text>
      </Space>
      <Table
        className="shortpick-replay-stat-table"
        rowKey="key"
        size="small"
        loading={loading}
        pagination={false}
        columns={[
          {
            title: "选股模式",
            render: (_, item) => (
              <Space direction="vertical" size={0}>
                <Text strong>{item.label}</Text>
                <Text type="secondary">{item.note}</Text>
              </Space>
            ),
          },
          {
            title: "候选逐条验证",
            render: (_, item) => (
              <Space direction="vertical" size={0}>
                <StrategyMetricCell metric={item.candidateMetric} />
                {item.candidateSourceIsProxy ? <Tag color="gold">近似参照</Tag> : null}
              </Space>
            ),
          },
          {
            title: "组合回测",
            render: (_, item) => (
              <Space direction="vertical" size={0}>
                <StrategyMetricCell metric={item.portfolioMetric} />
                {item.portfolioSourceIsProxy ? <Tag color="blue">同日组合</Tag> : null}
              </Space>
            ),
          },
          {
            title: "可比性",
            render: (_, item) => (
              <Space direction="vertical" size={0}>
                <Text>{item.candidateMetric && item.portfolioMetric ? "两种口径都有数据" : "口径待补"}</Text>
                <Text type="secondary">{item.candidateSourceIsProxy || item.portfolioSourceIsProxy ? "含近似参照，适合看方向，不适合做严格证明。" : "同策略可并排观察，排序时按各自口径分别比较。"}</Text>
              </Space>
            ),
          },
        ]}
        dataSource={rows}
      />
    </div>
  );
}

function statusCountText(counts?: Record<string, number> | null): string {
  const entries = Object.entries(counts ?? {}).filter(([, value]) => Number(value) > 0);
  return entries.length ? entries.map(([key, value]) => `${statusLabel(key)} ${value}`).join(" · ") : "--";
}

function concentrationText(metric?: ShortpickMarketPortfolioMetric | null): string {
  const concentration = metric?.concentration;
  const share = recordValue<number>(concentration, "top_industry_share");
  return `最高行业占比 ${formatPercent(share)}`;
}

function shortHash(value?: string | null): string {
  return value ? value.slice(0, 12) : "--";
}

function paperTrackingStatusLabel(value?: string | null): string {
  if (value === "tracking_active") return "已有正式标的";
  if (value === "waiting_first_frozen_run") return "等待首批";
  if (value === "no_signal") return "本批次未触发";
  if (value === "waiting_signal") return "等待信号";
  return "等待跟踪";
}

function paperTrackingAlertType(value?: string | null): "success" | "info" | "warning" {
  if (value === "tracking_active") return "success";
  if (value === "waiting_first_frozen_run") return "warning";
  return "info";
}

function paperTrackingGroupLabel(value?: string | null): string {
  if (value === "llm_paper_control") return "LLM纸面对照";
  if (value === "market_factor_control") return "市场因子对照";
  if (value === "market_random_control") return "同池随机基线";
  if (value === "frozen_strategy") return "冻结策略";
  return "纸面跟踪";
}

function paperTrackingGroupColor(value?: string | null): string {
  if (value === "llm_paper_control") return "blue";
  if (value === "market_factor_control") return "cyan";
  if (value === "market_random_control") return "default";
  if (value === "frozen_strategy") return "purple";
  return "default";
}

function initialShortpickWorkspaceTab(): ShortpickWorkspaceTab {
  const rawTab = new URLSearchParams(window.location.search).get("shortpickTab");
  return rawTab && SHORTPICK_WORKSPACE_TABS.has(rawTab as ShortpickWorkspaceTab)
    ? rawTab as ShortpickWorkspaceTab
    : "today";
}

function paperTrackingDisplayRank(item: ShortpickPaperTrackingItem): number {
  if (item.tracking_group === "frozen_strategy") return 0;
  if (item.tracking_group === "llm_paper_control") return 1;
  if (item.tracking_group === "market_factor_control") return 2;
  if (item.tracking_group === "market_random_control") return 3;
  return 4;
}

function paperTrackingChoiceLabel(latestRun?: Record<string, unknown> | null): "当前" | "下轮" {
  const now = new Date();
  const day = now.getDay();
  const minutes = now.getHours() * 60 + now.getMinutes();
  const isTradingDaytime = day >= 1 && day <= 5 && minutes >= 9 * 60 + 30 && minutes <= 15 * 60;
  if (isTradingDaytime) return "当前";
  const runDate = typeof latestRun?.run_date === "string" ? latestRun.run_date : "";
  const today = localDateString(now);
  const isAfterClose = day >= 1 && day <= 5 && minutes > 15 * 60;
  if (isAfterClose && runDate !== today) return "当前";
  return "下轮";
}

function localDateString(value = new Date()): string {
  return `${value.getFullYear()}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}

function nextWeekdayAfter(runDate: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(runDate);
  if (!match) return "下一交易日";
  const next = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]) + 1);
  while (next.getDay() === 0 || next.getDay() === 6) {
    next.setDate(next.getDate() + 1);
  }
  return `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, "0")}-${String(next.getDate()).padStart(2, "0")}`;
}

function paperTrackingSignalDate(item: ShortpickPaperTrackingItem): string {
  return item.signal_date || item.run_date;
}

function paperTrackingEntryDate(item: ShortpickPaperTrackingItem): string {
  return item.entry_date || nextWeekdayAfter(paperTrackingSignalDate(item));
}

function paperTrackingExpectedEntryText(item: ShortpickPaperTrackingItem): string {
  const isIntraday = Boolean(item.entry_rule?.includes("盘中") || item.entry_rule?.includes("当前价"));
  const session = isIntraday ? "盘中" : item.entry_rule?.includes("开盘") ? "开盘" : "收盘";
  return `预计买入 ${paperTrackingEntryDate(item)} ${session}`;
}

function hasPaperTrackingEntered(item: ShortpickPaperTrackingItem, today = localDateString()): boolean {
  const entryDate = paperTrackingEntryDate(item);
  return /^\d{4}-\d{2}-\d{2}$/.test(entryDate) && entryDate <= today;
}

function paperTrackingChoiceTimingText(
  choiceLabel: "当前" | "下轮",
  choiceRows: ShortpickPaperTrackingItem[],
  latestRun?: Record<string, unknown> | null,
): string {
  const runDate = typeof latestRun?.run_date === "string" ? latestRun.run_date : "";
  const signalDate = choiceRows[0] ? paperTrackingSignalDate(choiceRows[0]) : runDate;
  const entryDate = choiceRows[0] ? paperTrackingEntryDate(choiceRows[0]) : runDate ? nextWeekdayAfter(runDate) : "";
  const hasOpenEntry = choiceRows.some((item) => item.entry_rule?.includes("开盘"));
  const hasIntradayEntry = choiceRows.some((item) => item.entry_rule?.includes("盘中") || item.entry_rule?.includes("当前价"));
  if (!signalDate) return choiceLabel === "下轮" ? "信号日待确认 · 次一交易日收盘买入" : "当前跟踪信号待确认";
  if (hasIntradayEntry) {
    return `信号日 ${signalDate} · 含同日盘中当前价买入对照`;
  }
  if (hasOpenEntry) {
    return `信号日 ${signalDate} · 预计买入日 ${entryDate}，不同对照按各自入场规则执行`;
  }
  if (choiceLabel === "下轮") {
    return `信号日 ${signalDate} · 预计买入 ${entryDate} 收盘`;
  }
  return `当前跟踪 · 信号日 ${signalDate} · 入场口径为次一交易日收盘买入`;
}

function latestPaperTrackingChoices(rows: ShortpickPaperTrackingItem[], latestRun?: Record<string, unknown> | null): ShortpickPaperTrackingItem[] {
  const latestRunId = Number(latestRun?.id ?? 0);
  const latestRunDate = typeof latestRun?.run_date === "string" ? latestRun.run_date : "";
  const scoped = rows.filter((item) => (
    latestRunId ? Number(item.run_id) === latestRunId : latestRunDate ? item.run_date === latestRunDate : false
  ));
  const source = scoped.length ? scoped : rows;
  const latestDate = source.reduce((value, item) => (paperTrackingSignalDate(item) > value ? paperTrackingSignalDate(item) : value), "");
  return source
    .filter((item) => paperTrackingSignalDate(item) === latestDate)
    .sort((left, right) => (
      paperTrackingDisplayRank(left) - paperTrackingDisplayRank(right)
      || Number(left.source_rank ?? 99) - Number(right.source_rank ?? 99)
      || left.name.localeCompare(right.name, "zh-Hans-CN")
    ));
}

function nextPendingEntryDate(rows: ShortpickPaperTrackingItem[]): string {
  const today = localDateString();
  return rows
    .map((item) => paperTrackingEntryDate(item))
    .filter((value) => /^\d{4}-\d{2}-\d{2}$/.test(value) && value > today)
    .sort()[0] ?? "";
}

export function ShortpickLabView({ canTrigger }: { canTrigger: boolean }) {
  const [runs, setRuns] = useState<ShortpickRunView[]>([]);
  const [selectedRun, setSelectedRun] = useState<ShortpickRunView | null>(null);
  const [candidates, setCandidates] = useState<ShortpickCandidateView[]>([]);
  const [validationQueue, setValidationQueue] = useState<ShortpickValidationQueueResponse | null>(null);
  const [feedback, setFeedback] = useState<ShortpickModelFeedbackResponse | null>(null);
  const [replayRuns, setReplayRuns] = useState<ShortpickRunView[]>([]);
  const [selectedReplayRun, setSelectedReplayRun] = useState<ShortpickRunView | null>(null);
  const [replayCandidates, setReplayCandidates] = useState<ShortpickCandidateView[]>([]);
  const [replaySources, setReplaySources] = useState<ShortpickReplaySourceResponse | null>(null);
  const [replayFeedback, setReplayFeedback] = useState<ShortpickReplayFeedbackResponse | null>(null);
  const [replayAggregateFeedback, setReplayAggregateFeedback] = useState<ShortpickReplayFeedbackResponse | null>(null);
  const [replayFeedbackLoading, setReplayFeedbackLoading] = useState(false);
  const [replayAggregateLoading, setReplayAggregateLoading] = useState(false);
  const [marketStudy, setMarketStudy] = useState<ShortpickMarketFactorStudyResponse | null>(null);
  const [marketStudyLoading, setMarketStudyLoading] = useState(false);
  const [paperTracking, setPaperTracking] = useState<ShortpickPaperTrackingResponse | null>(null);
  const [paperTrackingLoading, setPaperTrackingLoading] = useState(false);
  const replayFeedbackRunIdRef = useRef<number | null>(null);
  const replayAggregateLoadingRef = useRef(false);
  const marketStudyLoadingRef = useRef(false);
  const [loading, setLoading] = useState(false);
  const [validationLoading, setValidationLoading] = useState(false);
  const [feedbackLoading, setFeedbackLoading] = useState(false);
  const [replayLoading, setReplayLoading] = useState(false);
  const [action, setAction] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [validationFilters, setValidationFilters] = useState({ status: "", horizon: "", model: "", symbol: "" });
  const [validationPage, setValidationPage] = useState({ current: 1, pageSize: DEFAULT_VALIDATION_PAGE_SIZE });
  const [selectedBenchmark, setSelectedBenchmark] = useState("hs300");
  const [activeWorkspaceTab, setActiveWorkspaceTab] = useState<ShortpickWorkspaceTab>(() => initialShortpickWorkspaceTab());

  const latestRun = selectedRun ?? runs[0] ?? null;
  const normalCandidates = useMemo(
    () => candidates.filter((item) => item.parse_status === "parsed" && item.symbol !== "PARSE_FAILED" && item.display_bucket !== "diagnostic"),
    [candidates],
  );
  const failedCandidates = useMemo(
    () => candidates.filter((item) => item.parse_status !== "parsed" || item.symbol === "PARSE_FAILED" || item.display_bucket === "diagnostic"),
    [candidates],
  );
  const failedRounds = useMemo(
    () => (latestRun?.rounds ?? []).filter((item) => item.status === "failed"),
    [latestRun],
  );
  const visibleWorkspaceTab = latestRun || activeWorkspaceTab !== "today"
    ? activeWorkspaceTab
    : paperTracking
      ? "paper-tracking"
      : "replay";

  async function loadLab(runId?: number): Promise<void> {
    setLoading(true);
    setError(null);
    try {
      const runList = await api.getShortpickRuns({ limit: 20 });
      const targetRunId = runId ?? selectedRun?.id ?? runList.data.items[0]?.id;
      const target = runList.data.items.find((item) => item.id === targetRunId) ?? runList.data.items[0] ?? null;
      setRuns(runList.data.items);
      setSelectedRun(target);
      if (target) {
        const candidateList = await api.getShortpickCandidates({ runId: target.id, limit: 100 });
        setCandidates(candidateList.data.items);
      } else {
        setCandidates([]);
      }
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "加载短投推荐试验田失败。");
    } finally {
      setLoading(false);
    }
  }

  async function loadValidationQueue(page = validationPage.current, pageSize = validationPage.pageSize): Promise<void> {
    setValidationLoading(true);
    if (activeWorkspaceTab === "validation") {
      setError(null);
    }
    try {
      const result = await api.getShortpickValidationQueue({
        limit: pageSize,
        offset: (page - 1) * pageSize,
        status: validationFilters.status || undefined,
        horizon: validationFilters.horizon ? Number(validationFilters.horizon) : undefined,
        model: validationFilters.model || undefined,
        symbol: validationFilters.symbol || undefined,
      });
      setValidationQueue(result.data);
      setValidationPage({ current: page, pageSize });
    } catch (queueError) {
      if (activeWorkspaceTab === "validation") {
        setError(queueError instanceof Error ? queueError.message : "加载历史验证失败。");
      } else {
        console.warn("加载历史验证失败", queueError);
      }
    } finally {
      setValidationLoading(false);
    }
  }

  async function loadFeedback(): Promise<void> {
    setFeedbackLoading(true);
    if (activeWorkspaceTab === "feedback") {
      setError(null);
    }
    try {
      const result = await api.getShortpickModelFeedback();
      setFeedback(result.data);
    } catch (feedbackError) {
      if (activeWorkspaceTab === "feedback") {
        setError(feedbackError instanceof Error ? feedbackError.message : "加载模型反馈失败。");
      } else {
        console.warn("加载模型反馈失败", feedbackError);
      }
    } finally {
      setFeedbackLoading(false);
    }
  }

  async function loadMarketStudy(): Promise<void> {
    if (marketStudy || marketStudyLoadingRef.current) return;
    marketStudyLoadingRef.current = true;
    setMarketStudyLoading(true);
    try {
      const result = await api.getShortpickMarketFactorStudy();
      setMarketStudy(result.data);
    } catch (studyError) {
      console.warn("加载策略收口失败", studyError);
    } finally {
      marketStudyLoadingRef.current = false;
      setMarketStudyLoading(false);
    }
  }

  async function loadPaperTracking(): Promise<void> {
    setPaperTrackingLoading(true);
    try {
      const result = await api.getShortpickPaperTracking();
      setPaperTracking(result.data);
    } catch (trackingError) {
      console.warn("加载纸面跟踪失败", trackingError);
      setPaperTracking(null);
    } finally {
      setPaperTrackingLoading(false);
    }
  }

  async function loadReplayAggregateFeedback(): Promise<void> {
    if (replayAggregateLoadingRef.current) return;
    replayAggregateLoadingRef.current = true;
    setReplayAggregateLoading(true);
    try {
      const result = await api.getShortpickReplayFeedback();
      setReplayAggregateFeedback(result.data);
    } catch (aggregateError) {
      console.warn("加载历史回放全局统计失败", aggregateError);
    } finally {
      replayAggregateLoadingRef.current = false;
      setReplayAggregateLoading(false);
    }
  }

  async function loadReplayRunFeedback(runId: number): Promise<void> {
    replayFeedbackRunIdRef.current = runId;
    setReplayFeedbackLoading(true);
    try {
      const result = await api.getShortpickReplayFeedback(runId);
      if (replayFeedbackRunIdRef.current === runId) {
        setReplayFeedback(result.data);
      }
    } catch (statsError) {
      if (replayFeedbackRunIdRef.current === runId) {
        setReplayFeedback(null);
      }
      console.warn("加载历史回放批次统计失败", statsError);
    } finally {
      if (replayFeedbackRunIdRef.current === runId) {
        setReplayFeedbackLoading(false);
      }
    }
  }

  async function loadReplay(runId?: number, options: { includeMarketStudy?: boolean } = {}): Promise<void> {
    setReplayLoading(true);
    if (activeWorkspaceTab === "replay") {
      setError(null);
    }
    try {
      const runList = await api.getShortpickReplayRuns({ limit: 100 });
      const targetRunId = runId ?? selectedReplayRun?.id ?? runList.data.items[0]?.id;
      const target = runList.data.items.find((item) => item.id === targetRunId) ?? runList.data.items[0] ?? null;
      setReplayRuns(runList.data.items);
      setSelectedReplayRun(target);
      void loadReplayAggregateFeedback();
      if (options.includeMarketStudy) {
        void loadMarketStudy();
      }
      if (target) {
        setReplayCandidates([]);
        setReplaySources(null);
        setReplayFeedback(null);
        replayFeedbackRunIdRef.current = target.id;
        setReplayFeedbackLoading(true);
        const [candidateList, sourcePacket] = await Promise.all([
          api.getShortpickReplayCandidates(target.id),
          api.getShortpickReplaySources(target.id),
        ]);
        setReplayCandidates(candidateList.data.items);
        setReplaySources(sourcePacket.data);
        void loadReplayRunFeedback(target.id);
      } else {
        setReplayCandidates([]);
        setReplaySources(null);
        setReplayFeedback(null);
        replayFeedbackRunIdRef.current = null;
        setReplayFeedbackLoading(false);
      }
    } catch (replayError) {
      if (activeWorkspaceTab === "replay") {
        setError(replayError instanceof Error ? replayError.message : "加载历史回放失败。");
      } else {
        console.warn("加载历史回放失败", replayError);
      }
    } finally {
      setReplayLoading(false);
    }
  }

  async function handleCreateRun(): Promise<void> {
    setAction("run");
    setError(null);
    try {
      const result = await api.createShortpickRun({ rounds_per_model: 5 });
      await loadLab(result.data.id);
      await loadPaperTracking();
      await loadValidationQueue(1, validationPage.pageSize);
      await loadFeedback();
    } catch (runError) {
      setError(runError instanceof Error ? runError.message : "触发短投推荐实验失败。");
    } finally {
      setAction(null);
    }
  }

  async function handleValidateRun(): Promise<void> {
    if (!latestRun) return;
    setAction("validate");
    setError(null);
    try {
      await api.validateShortpickRun(latestRun.id, { horizons: [1, 3, 5, 10, 20] });
      await loadLab(latestRun.id);
      await loadPaperTracking();
      await loadValidationQueue(validationPage.current, validationPage.pageSize);
      await loadFeedback();
    } catch (validateError) {
      setError(validateError instanceof Error ? validateError.message : "补跑后验复盘失败。");
    } finally {
      setAction(null);
    }
  }

  async function handleRetryFailedRounds(): Promise<void> {
    if (!latestRun) return;
    setAction("retry");
    setError(null);
    try {
      await api.retryShortpickFailedRounds(latestRun.id, {});
      await loadLab(latestRun.id);
      await loadPaperTracking();
      await loadValidationQueue(validationPage.current, validationPage.pageSize);
      await loadFeedback();
    } catch (retryError) {
      const message = retryError instanceof Error ? retryError.message : "重跑失败轮次失败。";
      setError(
        message.includes("404")
          ? "重跑接口返回 404。通常是页面仍在使用旧版本或边缘路由尚未刷新；请刷新页面后重试。如果失败轮次已经被后台补跑，刷新后按钮会自动消失。"
          : message,
      );
    } finally {
      setAction(null);
    }
  }

  useEffect(() => {
    void loadLab();
    void loadPaperTracking();
    void loadValidationQueue(1, DEFAULT_VALIDATION_PAGE_SIZE);
    void loadFeedback();
  }, []);

  const benchmarkSwitcher = (
    <Space size={8} className="shortpick-benchmark-switcher">
      <span>收益反馈</span>
      <Select
        className="shortpick-benchmark-select"
        size="small"
        options={BENCHMARK_OPTIONS}
        value={selectedBenchmark}
        onChange={(value) => setSelectedBenchmark(value)}
        popupMatchSelectWidth={false}
      />
    </Space>
  );

  const candidateColumns: ColumnsType<ShortpickCandidateView> = [
    {
      title: "研究标的",
      dataIndex: "symbol",
      key: "symbol",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Text strong>{item.name} · {item.symbol}</Text>
          <Text type="secondary">{topicLabel(item)}</Text>
        </Space>
      ),
    },
    {
      title: "优先级",
      dataIndex: "research_priority",
      key: "research_priority",
      render: (value: string, item) => (
        <Space wrap>
          <Tag color={priorityColor(value)}>{priorityLabel(value)}</Tag>
          {item.tracking_role === "llm_paper_control_primary" ? <Tag color="blue">LLM纸面对照</Tag> : null}
          {item.baseline_family ? <Tag color="cyan">{baselineFamilyLabel(item.baseline_family)}</Tag> : null}
          {item.is_system_external ? <Tag color="blue">系统外新视角</Tag> : <Tag>系统内已覆盖</Tag>}
        </Space>
      ),
    },
    {
      title: "模型理由",
      dataIndex: "thesis",
      key: "thesis",
      render: (value: string | null) => <Text>{value || "--"}</Text>,
    },
    {
      title: "验证",
      key: "validation",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Text>{validationSummary(item, selectedBenchmark)}</Text>
          <Text type="secondary">验证完成前按待验证处理</Text>
        </Space>
      ),
    },
  ];

  const validationColumns: ColumnsType<ShortpickValidationQueueItem> = [
    {
      title: "批次 / 标的",
      key: "stock",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Text strong>{item.name} · {item.symbol}</Text>
          <Text type="secondary">{item.run_date} · {item.provider_name || "--"}:{item.model_name || "--"}</Text>
        </Space>
      ),
    },
    {
      title: "周期",
      dataIndex: "horizon_days",
      key: "horizon_days",
      render: (value: number) => <Tag>{value}日</Tag>,
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      render: (value: string) => <Tag color={statusColor(value)}>{statusLabel(value)}</Tag>,
    },
    {
      title: benchmarkSwitcher,
      key: "returns",
      render: (_, item) => {
        const metric = benchmarkMetric(item, selectedBenchmark);
        return (
          <Space direction="vertical" size={0}>
            {metric.status === "available" ? (
              <>
                <Text className={`value-${valueTone(metric.excess_return)}`}>超额收益 {formatPercent(metric.excess_return)}</Text>
                <Text type="secondary">个股 {formatPercent(item.stock_return)} / {metric.benchmark_label || benchmarkLabel(selectedBenchmark)} {formatPercent(metric.benchmark_return)}</Text>
              </>
            ) : (
              <>
                <Text type="secondary">{benchmarkPendingText(metric.status, metric.reason)}</Text>
                <Text type="secondary">个股 {formatPercent(item.stock_return)} / {metric.benchmark_label || benchmarkLabel(selectedBenchmark)} 待补</Text>
              </>
            )}
          </Space>
        );
      },
    },
    {
      title: "窗口",
      key: "window",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Text>{item.entry_at ? formatDate(item.entry_at) : "等待入场"} → {item.exit_at ? formatDate(item.exit_at) : "等待窗口"}</Text>
          {validationWindowNote(item) ? <Text type="secondary">{validationWindowNote(item)}</Text> : null}
          <Text type="secondary">浮盈 {formatPercent(item.max_favorable_return)} / 回撤 {formatPercent(item.max_drawdown)}</Text>
        </Space>
      ),
    },
  ];

  const feedbackColumns: ColumnsType<ShortpickModelFeedbackItem> = [
    {
      title: "模型",
      key: "model",
      align: "center",
      render: (_, item) => (
        <Space direction="vertical" size={0} align="center" className="shortpick-centered-cell">
          <Text strong>{item.provider_name}:{item.model_name}</Text>
          <Text type="secondary">{item.executor_kind}</Text>
        </Space>
      ),
    },
    {
      title: "轮次质量",
      key: "rounds",
      align: "center",
      render: (_, item) => (
        <Space direction="vertical" size={0} align="center" className="shortpick-centered-cell">
          <Text>{item.completed_round_count} / {item.round_count} 成功</Text>
          <Text type="secondary">失败 {item.failed_round_count} · 可重跑 {item.retryable_failed_round_count} · 解析失败 {item.parse_failed_candidate_count}</Text>
        </Space>
      ),
    },
    {
      title: "成功率",
      dataIndex: "success_rate",
      key: "success_rate",
      align: "center",
      render: (value?: number | null) => <Text>{formatPercent(value)}</Text>,
    },
    {
      title: "来源质量",
      key: "sources",
      align: "center",
      render: (_, item) => (
        <Space wrap className="shortpick-centered-cell">
          {Object.entries(item.source_credibility_counts).map(([key, value]) => (
            <Tag key={key} color={sourceCredibilityColor(key)}>{sourceCredibilityLabel(key)} {value}</Tag>
          ))}
        </Space>
      ),
    },
  ];

  return (
    <section className="shortpick-lab">
      <Card className="panel-card shortpick-lab-header">
        <div className="shortpick-lab-title">
          <div>
            <Paragraph className="topbar-kicker">Short Pick Lab</Paragraph>
            <Title level={3}>短投推荐试验田</Title>
            <Paragraph className="panel-description">
              独立研究课题，不进入主推荐评分；冻结纸面策略进入正式跟踪，LLM 自由选股保留为对照组；后验验证完成前仅作为探索结果展示。
            </Paragraph>
          </div>
          <Space wrap>
            <Select
              className="shortpick-run-select"
              value={latestRun?.id}
              placeholder="选择历史批次"
              options={runs.map((run) => ({
                value: run.id,
                label: `${run.run_date} · ${statusLabel(operationalStatus(run))}`,
              }))}
              onChange={(runId) => void loadLab(Number(runId))}
            />
            <Button icon={<ReloadOutlined />} onClick={() => {
              void loadLab(latestRun?.id);
              void loadPaperTracking();
              void loadValidationQueue(validationPage.current, validationPage.pageSize);
              void loadFeedback();
              if (activeWorkspaceTab === "replay") {
                void loadReplay(selectedReplayRun?.id, { includeMarketStudy: true });
              }
            }} loading={loading || validationLoading || feedbackLoading || replayLoading}>
              刷新
            </Button>
            {canTrigger ? (
              <>
                <Button
                  type="primary"
                  icon={<ExperimentOutlined />}
                  loading={action === "run"}
                  onClick={() => void handleCreateRun()}
                >
                  生成LLM对照批次
                </Button>
                <Button
                  icon={<SyncOutlined />}
                  disabled={!latestRun}
                  loading={action === "validate"}
                  onClick={() => void handleValidateRun()}
                >
                  补跑对照复盘
                </Button>
                <Button
                  danger
                  disabled={!latestRun || !failedRounds.some((item) => item.retryable)}
                  loading={action === "retry"}
                  onClick={() => void handleRetryFailedRounds()}
                >
                  重跑失败轮次
                </Button>
              </>
            ) : null}
          </Space>
        </div>
        {error ? <Alert type="error" showIcon message={error} /> : null}
      </Card>

      {!latestRun && !loading && !replayRuns.length && !paperTracking ? (
        <Card className="panel-card">
          <Empty description="暂无短投推荐实验批次" />
        </Card>
      ) : null}

      {latestRun || replayRuns.length || paperTracking ? (
        <Tabs
          className="shortpick-workspace-tabs"
          activeKey={visibleWorkspaceTab}
          onChange={(key) => {
            if (SHORTPICK_WORKSPACE_TABS.has(key as ShortpickWorkspaceTab)) {
              setActiveWorkspaceTab(key as ShortpickWorkspaceTab);
            }
            if (key === "replay") {
              void loadReplay(selectedReplayRun?.id, { includeMarketStudy: true });
            }
          }}
          items={[
            {
              key: "today",
              label: "今日批次",
              children: latestRun ? (
                <TodayRunTab
                  run={latestRun}
                  paperTracking={paperTracking}
                  paperTrackingLoading={paperTrackingLoading}
                  normalCandidates={normalCandidates}
                  failedCandidates={failedCandidates}
                  failedRounds={failedRounds}
                  loading={loading}
                  candidateColumns={candidateColumns}
                  selectedBenchmark={selectedBenchmark}
                />
              ) : (
                <Card className="panel-card">
                  <Empty description="暂无LLM对照批次；可先查看纸面跟踪或历史回放。" />
                </Card>
              ),
            },
            {
              key: "paper-tracking",
              label: "纸面跟踪",
              children: <PaperTrackingTab tracking={paperTracking} loading={paperTrackingLoading} />,
            },
            {
              key: "validation",
              label: "LLM历史验证",
              children: (
                <ValidationQueueTab
                  filters={validationFilters}
                  onFiltersChange={setValidationFilters}
                  onSearch={() => void loadValidationQueue(1, validationPage.pageSize)}
                  queue={validationQueue}
                  loading={validationLoading}
                  columns={validationColumns}
                  page={validationPage}
                  onPageChange={(pagination) => {
                    void loadValidationQueue(pagination.current ?? 1, pagination.pageSize ?? DEFAULT_VALIDATION_PAGE_SIZE);
                  }}
                />
              ),
            },
            {
              key: "feedback",
              label: "LLM模型反馈",
              children: <ModelFeedbackTab feedback={feedback} loading={feedbackLoading} columns={feedbackColumns} selectedBenchmark={selectedBenchmark} />,
            },
            {
              key: "replay",
              label: "历史回放",
              children: (
                <HistoricalReplayTab
                  runs={replayRuns}
                  selectedRun={selectedReplayRun}
                  candidates={replayCandidates}
                  sources={replaySources}
                  feedback={replayFeedback}
                  aggregateFeedback={replayAggregateFeedback}
                  feedbackLoading={replayFeedbackLoading}
                  aggregateFeedbackLoading={replayAggregateLoading}
                  marketStudy={marketStudy}
                  marketStudyLoading={marketStudyLoading}
                  loading={replayLoading}
                  selectedBenchmark={selectedBenchmark}
                  onSelectRun={(runId) => void loadReplay(runId, { includeMarketStudy: true })}
                  onReload={() => void loadReplay(selectedReplayRun?.id, { includeMarketStudy: true })}
                />
              ),
            },
          ]}
        />
      ) : null}

      <Alert
        type="info"
        showIcon
        icon={<SafetyCertificateOutlined />}
        message="隔离规则"
        description="短投推荐实验保存在独立数据域，不影响现有候选池、自选池、量化推荐、模拟盘自动调仓或生产权重。来源可达只代表 URL/访问层校验，不等于权威来源。"
      />
    </section>
  );
}

function TodayRunTab({
  run,
  paperTracking,
  paperTrackingLoading,
  normalCandidates,
  failedCandidates,
  failedRounds,
  loading,
  candidateColumns,
  selectedBenchmark,
}: {
  run: ShortpickRunView;
  paperTracking: ShortpickPaperTrackingResponse | null;
  paperTrackingLoading: boolean;
  normalCandidates: ShortpickCandidateView[];
  failedCandidates: ShortpickCandidateView[];
  failedRounds: ShortpickRoundView[];
  loading: boolean;
  candidateColumns: ColumnsType<ShortpickCandidateView>;
  selectedBenchmark: string;
}) {
  const llmControlCandidate = normalCandidates.find((item) => item.tracking_role === "llm_paper_control_primary");
  const llmControl = llmControlCandidate?.llm_paper_control ?? {};
  const llmAccountFilterRule = String(
    llmControl.account_filter_rule ?? "仅允许沪深主板普通A股；排除科创板、创业板、北交所、ST/退市风险类标的。",
  );
  const llmSelectionRule = String(
    llmControl.selection_rule ?? "先过滤到新开户普通现金账户可买范围；再优先跨模型同票，其次同模型重复、跨模型同题材、单模型高置信、系统外新视角；再按来源质量、置信度、来源数量、股票代码和候选ID稳定排序。",
  );
  return (
    <>
      <Row gutter={[16, 16]} className="shortpick-metrics">
        <Col xs={24} md={6}>
          <div className="shortpick-metric">
            <span>最近批次</span>
            <strong>{run.run_date}</strong>
            <Tag color={statusColor(operationalStatus(run))}>{statusLabel(operationalStatus(run))}</Tag>
          </div>
        </Col>
        <Col xs={24} md={6}>
          <div className="shortpick-metric">
            <span>完成 / 失败轮次</span>
            <strong>{Number(run.summary.completed_round_count ?? 0)} / {Number(run.summary.failed_round_count ?? 0)}</strong>
            <Text type="secondary">{Number(run.summary.retryable_failed_round_count ?? 0)} 个可重跑</Text>
          </div>
        </Col>
        <Col xs={24} md={6}>
          <div className="shortpick-metric">
            <span>LLM 对照状态</span>
            <strong>{priorityLabel(run.consensus?.research_priority ?? "pending")}</strong>
            <Text type="secondary">只用于和冻结策略对比</Text>
          </div>
        </Col>
        <Col xs={24} md={6}>
          <div className="shortpick-metric">
            <span>LLM 验证覆盖</span>
            <strong>{validationCoverage(run)}</strong>
            <Text type="secondary">主基准：{primaryBenchmarkLabel(run)}</Text>
          </div>
        </Col>
      </Row>

      <FrozenRunStatus run={run} normalCandidates={normalCandidates} paperTracking={paperTracking} loading={paperTrackingLoading} />

      <Card className="panel-card" title="LLM纸面对照标的" extra={<Tag color="blue">每日固定规则选1只</Tag>}>
        {llmControlCandidate ? (
          <Descriptions size="small" column={{ xs: 1, md: 3 }}>
            <Descriptions.Item label="纸面对照">{llmControlCandidate.name} · {llmControlCandidate.symbol}</Descriptions.Item>
            <Descriptions.Item label="原始优先级">{priorityLabel(llmControlCandidate.research_priority)}</Descriptions.Item>
            <Descriptions.Item label="验证口径">同一入场，四轨退出</Descriptions.Item>
            <Descriptions.Item label="账户过滤" span={3}>
              {llmAccountFilterRule}
            </Descriptions.Item>
            <Descriptions.Item label="选择规则" span={3}>
              {llmSelectionRule}
            </Descriptions.Item>
          </Descriptions>
        ) : (
          <Empty description="本批次尚未形成LLM纸面对照标的；下一次完整LLM批次会按固定规则提前选出1只。" />
        )}
      </Card>

      {failedRounds.length || failedCandidates.length ? (
        <FailureDiagnostics failedRounds={failedRounds} failedCandidates={failedCandidates} selectedBenchmark={selectedBenchmark} />
      ) : null}

      <Card
        className="panel-card"
        title="LLM 对照组收敛"
        extra={<Tag color="default">不作为主策略</Tag>}
      >
        {run.consensus ? (
          <>
            <Row gutter={[20, 16]}>
              <Col xs={24} md={8}>
                <Progress percent={Math.round(run.consensus.stock_convergence * 100)} size="small" />
                <Text>单票收敛</Text>
              </Col>
              <Col xs={24} md={8}>
                <Progress percent={Math.round(run.consensus.theme_convergence * 100)} size="small" />
                <Text>题材收敛</Text>
              </Col>
              <Col xs={24} md={8}>
                <Progress percent={Math.round(run.consensus.source_diversity * 100)} size="small" />
                <Text>来源多样性</Text>
              </Col>
            </Row>
            <Descriptions className="shortpick-consensus-desc" size="small" column={{ xs: 1, md: 3 }}>
              <Descriptions.Item label="领先股票">
                {Array.isArray(run.consensus.summary.leader_symbols)
                  ? (run.consensus.summary.leader_symbols as string[]).join(" / ") || "--"
                  : "--"}
              </Descriptions.Item>
              <Descriptions.Item label="领先题材">
                {recordValue<Record<string, string>>(run.consensus.summary, "leader_theme_labels")
                  ? Object.values(recordValue<Record<string, string>>(run.consensus.summary, "leader_theme_labels") ?? {}).join(" / ") || "--"
                  : Array.isArray(run.consensus.summary.leader_themes)
                    ? (run.consensus.summary.leader_themes as string[]).join(" / ") || "--"
                    : "--"}
              </Descriptions.Item>
              <Descriptions.Item label="解释">
                {String(run.consensus.summary.interpretation ?? "模型一致性只代表研究优先级。")}
              </Descriptions.Item>
            </Descriptions>
          </>
        ) : (
          <Empty description="等待聚合结果" />
        )}
      </Card>

      <Card className="panel-card" title="对照研究池" extra={<Text type="secondary">LLM 自由选股与动量对照样本</Text>}>
        <Table
          rowKey="id"
          size="middle"
          loading={loading}
          columns={candidateColumns}
          dataSource={normalCandidates}
          pagination={{ pageSize: 8 }}
          expandable={{
            expandedRowRender: (item) => (
              <div className="shortpick-detail-grid">
                <div>
                  <Title level={5}>催化与风险</Title>
                  <List size="small" dataSource={[...item.catalysts, ...item.risks]} renderItem={(text) => <List.Item>{text}</List.Item>} />
                </div>
                <div>
                  <Title level={5}>后验复盘</Title>
                  <ValidationList items={item.validations} selectedBenchmark={selectedBenchmark} />
                </div>
                <div>
                  <Title level={5}>来源与留痕</Title>
                  <SourceList candidate={item} />
                </div>
              </div>
            ),
          }}
        />
      </Card>

      <Card className="panel-card" title="LLM 原始推荐（对照）">
        <Table
          rowKey="id"
          size="middle"
          loading={loading}
          columns={roundColumns()}
          dataSource={run.rounds}
          pagination={{ pageSize: 10 }}
        />
      </Card>
    </>
  );
}

function FrozenRunStatus({
  run,
  normalCandidates,
  paperTracking,
  loading,
}: {
  run: ShortpickRunView;
  normalCandidates: ShortpickCandidateView[];
  paperTracking: ShortpickPaperTrackingResponse | null;
  loading: boolean;
}) {
  const overlay = recordValue<Record<string, unknown>>(run.summary, "market_factor_overlay") ?? {};
  const frozen = recordValue<Record<string, unknown>>(overlay, "frozen_paper_strategy") ?? {};
  const regime = recordValue<Record<string, unknown>>(overlay, "regime") ?? {};
  const frozenCandidate = normalCandidates.find((item) => item.research_priority === "market_factor_frozen_paper");
  const gatePass = Boolean(frozen.gate_pass);
  const inserted = Boolean(frozen.inserted);
  const trackingStatus = paperTracking?.current_status;
  const isWaitingFirstFrozenRun = trackingStatus === "waiting_first_frozen_run" && !Object.keys(frozen).length;
  const alertType = isWaitingFirstFrozenRun ? "warning" : inserted ? "success" : gatePass ? "warning" : paperTrackingAlertType(trackingStatus);
  const alertMessage = isWaitingFirstFrozenRun
    ? "冻结策略已启用，等待首个正式跟踪批次"
    : inserted
      ? "本批次已生成冻结策略标的"
      : gatePass
        ? "启用条件满足，但候选不足"
        : paperTracking?.current_label || "本批次未触发冻结策略";
  const frozenSelectionRule = String(
    frozen.selection_rule ?? "当全市场10日上涨占比不低于45%时，选择20日趋势向上、成交额较高且换手率相对不拥挤的第1名",
  );
  const frozenRiskRule = String(
    frozen.risk_rule ?? "同一入场信号并行记录机械5日、机械10日、条件检查和10%止盈四条退出轨道。",
  );
  const alertDescription = isWaitingFirstFrozenRun
    ? "当前最新 LLM 对照批次生成于规则冻结前；下一次盘后批次会按冻结规则写入正式纸面跟踪或记录未触发原因。"
    : inserted && frozenCandidate
      ? `本批次纸面跟踪标的：${frozenCandidate.symbol} ${frozenCandidate.name}。规则已冻结：${frozenSelectionRule}。${frozenRiskRule}`
      : paperTracking?.current_message || "冻结策略只在市场转正且候选池不过热时启动；未启动批次也会记录为真实纸面跟踪的一部分。";
  return (
    <Card className="panel-card shortpick-frozen-status" title="正式纸面跟踪（冻结策略）" loading={loading && !paperTracking}>
      <Alert
        showIcon
        type={alertType}
        message={alertMessage}
        description={alertDescription}
      />
      <Row gutter={[12, 12]} className="shortpick-frozen-metrics">
        <Col xs={24} md={8}>
          <div className="shortpick-metric">
            <span>跟踪阶段</span>
            <strong>规则冻结</strong>
            <Text type="secondary">需要40个真实交易日后再评价</Text>
          </div>
        </Col>
        <Col xs={24} md={8}>
          <div className="shortpick-metric">
            <span>市场状态</span>
            <strong>{formatPercent(Number(regime.universe_ret10_mean ?? 0))}</strong>
            <Text type="secondary">全市场10日平均收益</Text>
          </div>
        </Col>
        <Col xs={24} md={8}>
          <div className="shortpick-metric">
            <span>候选池热度</span>
            <strong>{formatPercent(Number(regime.pool_ret1_mean ?? 0))}</strong>
            <Text type="secondary">扩大候选池1日平均涨幅</Text>
          </div>
        </Col>
      </Row>
    </Card>
  );
}

function PaperTrackingTab({
  tracking,
  loading,
}: {
  tracking: ShortpickPaperTrackingResponse | null;
  loading: boolean;
}) {
  const contract = tracking?.contract ?? {};
  const llmControlContract = tracking?.llm_control_contract ?? {};
  const marketControlContract = tracking?.market_control_contract ?? {};
  const summary = tracking?.summary ?? {};
  const latestRun = tracking?.latest_run ?? null;
  const rows = tracking?.items ?? [];
  const [showFrozenOnly, setShowFrozenOnly] = useState(false);
  const enteredRows = rows.filter((item) => hasPaperTrackingEntered(item));
  const displayRows = showFrozenOnly ? enteredRows.filter((item) => item.tracking_group === "frozen_strategy") : enteredRows;
  const choiceLabel = paperTrackingChoiceLabel(latestRun);
  const choiceRows = latestPaperTrackingChoices(rows, latestRun);
  const choiceTimingText = paperTrackingChoiceTimingText(choiceLabel, choiceRows, latestRun);
  const pendingEntryDate = nextPendingEntryDate(rows);
  const monitoringTracks = (Array.isArray(contract.monitoring_tracks) ? contract.monitoring_tracks : []) as Record<string, unknown>[];
  const marketControls = (Array.isArray(marketControlContract.controls) ? marketControlContract.controls : []) as Record<string, unknown>[];
  const columns: ColumnsType<ShortpickPaperTrackingItem> = [
    {
      title: "信号 / 买入",
      dataIndex: "run_date",
      key: "run_date",
      render: (value: string, item) => (
        <Space direction="vertical" size={0}>
          <Text strong>{paperTrackingSignalDate(item)}</Text>
          <Text type="secondary">买入 {paperTrackingEntryDate(item)}</Text>
        </Space>
      ),
    },
    {
      title: "纸面标的",
      key: "symbol",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Text strong>{item.name} · {item.symbol}</Text>
          <Space wrap size={4}>
            <Tag color={paperTrackingGroupColor(item.tracking_group)}>{paperTrackingGroupLabel(item.tracking_group)}</Tag>
            <Text type="secondary">{item.selection_label || "纸面对照"}</Text>
          </Space>
        </Space>
      ),
    },
    {
      title: "买入与退出",
      key: "rules",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Text>{item.entry_rule || "次一交易日收盘买入"}</Text>
          <Text type="secondary">{item.exit_rule || "机械5日、机械10日、条件检查、10%触达止盈四轨监测"}</Text>
        </Space>
      ),
    },
    {
      title: "触发状态",
      key: "gate",
      render: (_, item) => (
        <Space wrap>
          <Tag color={paperTrackingGroupColor(item.tracking_group)}>
            {item.tracking_group === "llm_paper_control"
              ? "固定规则第1只"
              : item.tracking_group === "market_random_control"
                ? `池内第 ${Number(item.source_rank ?? 1)} 只`
                : `第 ${Number(item.source_rank ?? 2)} 候选`}
          </Tag>
          <Tag color={item.gate?.inserted === false ? "gold" : "green"}>{item.gate?.inserted === false ? "未写入" : "已写入"}</Tag>
        </Space>
      ),
    },
    {
      title: "说明",
      dataIndex: "thesis",
      key: "thesis",
      render: (value?: string | null) => <Text>{value || "--"}</Text>,
    },
  ];

  return (
    <>
      <Card className="panel-card shortpick-frozen-status" title="冻结策略纸面跟踪">
        <Alert
          showIcon
          type={paperTrackingAlertType(tracking?.current_status)}
          message={tracking?.current_label || "等待纸面跟踪状态"}
          description={tracking?.current_message || "正在读取冻结策略的纸面跟踪 ledger；该区域只读取已有记录，不触发模型或行情更新。"}
        />
        <Row gutter={[12, 12]} className="shortpick-frozen-metrics">
          <Col xs={24} md={6}>
            <div className="shortpick-metric">
              <span>当前状态</span>
              <strong>{paperTrackingStatusLabel(tracking?.current_status)}</strong>
              <Text type="secondary">冻结日期 {String(summary.frozen_at ?? contract.frozen_at ?? "--")}</Text>
            </div>
          </Col>
          <Col xs={24} md={6}>
            <div className="shortpick-metric">
              <span>正式跟踪数</span>
              <strong>{Number(summary.tracked_signal_count ?? 0)}</strong>
              <Text type="secondary">前向观察 {Number(summary.required_forward_trading_days ?? contract.required_forward_trading_days ?? 40)} 个交易日</Text>
            </div>
          </Col>
          <Col xs={24} md={6}>
            <div className="shortpick-metric">
              <span>LLM纸面对照数</span>
              <strong>{Number(summary.llm_paper_control_signal_count ?? 0)}</strong>
              <Text type="secondary">每天从LLM池提前固定选1只</Text>
            </div>
          </Col>
          <Col xs={24} md={6}>
            <div className="shortpick-metric">
              <span>市场对照数</span>
              <strong>{Number(summary.market_control_signal_count ?? 0)}</strong>
              <Text type="secondary">第1名、降追高、随机同池基线</Text>
            </div>
          </Col>
        </Row>
      </Card>

      <Card
        className="panel-card shortpick-choice-card"
        title={`${choiceLabel}股票选择`}
        extra={<Tag color={choiceLabel === "下轮" ? "purple" : "blue"}>{choiceLabel}</Tag>}
      >
        <Paragraph className="shortpick-choice-timing">
          <Text strong>{choiceTimingText}</Text>
        </Paragraph>
        <Paragraph className="panel-description">
          {choiceLabel === "下轮"
            ? "这里展示的是最新盘后批次生成的下一交易日纸面买入观察清单，不是下一交易日开盘后重新计算的新批次；冻结规则固定排在第一。"
            : "交易时段或下一轮结果未生成前，以下为当前正在跟踪的纸面选择；冻结规则固定排在第一。"}
        </Paragraph>
        {choiceRows.length ? (
          <List
            className="shortpick-choice-list"
            dataSource={choiceRows}
            renderItem={(item, index) => (
              <List.Item>
                <div className="shortpick-choice-item">
                  <div className="shortpick-choice-rank">{index + 1}</div>
                  <div className="shortpick-choice-copy">
                    <Space wrap size={6}>
                      <Text strong>{item.name} · {item.symbol}</Text>
                      <Tag color={paperTrackingGroupColor(item.tracking_group)}>{paperTrackingGroupLabel(item.tracking_group)}</Tag>
                      {index === 0 && item.tracking_group === "frozen_strategy" ? <Tag color="purple">冻结规则优先</Tag> : null}
                    </Space>
                    <Text type="secondary">{item.selection_label || "纸面对照"} · {paperTrackingExpectedEntryText(item)}</Text>
                    <Text type="secondary">{item.entry_rule || "次一交易日收盘买入"}</Text>
                  </div>
                </div>
              </List.Item>
            )}
          />
        ) : (
          <Empty description={loading ? "股票选择加载中" : "暂无可展示的纸面选择。"} image={Empty.PRESENTED_IMAGE_SIMPLE} />
        )}
      </Card>

      <Card className="panel-card" title="冻结规则">
        <Descriptions size="small" column={{ xs: 1, md: 2 }}>
          <Descriptions.Item label="策略名称" span={2}>{String(contract.label ?? "冻结纸面策略：低换手上升趋势四轨监测")}</Descriptions.Item>
          <Descriptions.Item label="运行方式">{String(contract.mode ?? "每日滚动 5x1万；持有天数按交易日计算")}</Descriptions.Item>
          <Descriptions.Item label="候选池">{String(contract.pool_rule ?? "先扩大动量成交量候选池")}</Descriptions.Item>
          <Descriptions.Item label="选择规则">{String(contract.selection_rule ?? "当全市场10日上涨占比不低于45%时，选择20日趋势向上、成交额较高且换手率相对不拥挤的第1名")}</Descriptions.Item>
          <Descriptions.Item label="监测规则">{String(contract.risk_rule ?? "机械5日、机械10日、条件检查、10%触达止盈四轨监测")}</Descriptions.Item>
          <Descriptions.Item label="边界说明" span={2}>{String(summary.scope_note ?? contract.scope_note ?? "LLM自由选股保留为对照组。")}</Descriptions.Item>
        </Descriptions>
        {monitoringTracks.length ? (
          <List
            className="shortpick-track-list"
            size="small"
            dataSource={monitoringTracks}
            renderItem={(track) => (
              <List.Item>
                <Space direction="vertical" size={0}>
                  <Text strong>{String(track.label ?? track.key ?? "退出轨道")}</Text>
                  <Text type="secondary">{String(track.description ?? "")}</Text>
                </Space>
              </List.Item>
            )}
          />
        ) : null}
      </Card>

      <Card className="panel-card" title="LLM纸面对照规则">
        <Descriptions size="small" column={{ xs: 1, md: 2 }}>
          <Descriptions.Item label="对照名称" span={2}>{String(llmControlContract.label ?? "LLM纸面对照：每日固定规则选1只")}</Descriptions.Item>
          <Descriptions.Item label="运行方式">{String(llmControlContract.mode ?? "从当日LLM自由推荐池中提前选1只")}</Descriptions.Item>
          <Descriptions.Item label="选择规则" span={2}>{String(llmControlContract.selection_rule ?? "跨模型同票优先，再按来源质量、置信度和稳定排序。")}</Descriptions.Item>
          <Descriptions.Item label="监测规则" span={2}>{String(llmControlContract.monitoring_rule ?? "和冻结策略使用同一入场口径与四条退出轨道。")}</Descriptions.Item>
          <Descriptions.Item label="边界说明" span={2}>{String(summary.llm_control_scope_note ?? llmControlContract.scope_note ?? "全量LLM推荐池继续保留为研究样本。")}</Descriptions.Item>
          <Descriptions.Item label="最近批次">{String(latestRun?.run_date ?? "--")}</Descriptions.Item>
          <Descriptions.Item label="批次状态">{latestRun?.has_frozen_overlay ? "已包含冻结覆盖层" : "等待冻结后批次"}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card className="panel-card" title="市场因子对照规则">
        <Descriptions size="small" column={{ xs: 1, md: 2 }}>
          <Descriptions.Item label="对照名称" span={2}>{String(marketControlContract.label ?? "市场因子纸面对照：同池简单选法")}</Descriptions.Item>
          <Descriptions.Item label="运行方式" span={2}>{String(marketControlContract.mode ?? "和冻结策略使用同一个动量成交量Top40候选池，每个规则每天最多提前固定1只。")}</Descriptions.Item>
          <Descriptions.Item label="监测规则" span={2}>{String(marketControlContract.monitoring_rule ?? "和冻结策略使用同一入场口径与四条退出轨道。")}</Descriptions.Item>
          <Descriptions.Item label="边界说明" span={2}>{String(summary.market_control_scope_note ?? marketControlContract.scope_note ?? "单票分析暂不升入冻结真实跟踪。")}</Descriptions.Item>
        </Descriptions>
        {marketControls.length ? (
          <List
            className="shortpick-track-list"
            size="small"
            dataSource={marketControls}
            renderItem={(control) => (
              <List.Item>
                <Space direction="vertical" size={0}>
                  <Text strong>{String(control.label ?? "市场对照")}</Text>
                  <Text type="secondary">{String(control.selection_rule ?? "")}</Text>
                </Space>
              </List.Item>
            )}
          />
        ) : null}
      </Card>

      <Card
        className="panel-card shortpick-paper-ledger-card"
        title="纸面跟踪记录（正式策略与对照组）"
        extra={(
          <Checkbox checked={showFrozenOnly} onChange={(event) => setShowFrozenOnly(event.target.checked)}>
            仅看冻结规则
          </Checkbox>
        )}
      >
        {displayRows.length ? (
          <>
            <Table
              className="shortpick-paper-ledger-table"
              rowKey="candidate_id"
              size="middle"
              loading={loading}
              columns={columns}
              dataSource={displayRows}
              pagination={{ pageSize: 8 }}
              scroll={{ x: 920 }}
            />
            <List
              className="shortpick-paper-mobile-list"
              dataSource={displayRows}
              renderItem={(item) => (
                <List.Item>
                  <div className="shortpick-paper-mobile-item">
                    <div className="shortpick-paper-mobile-head">
                      <Text strong>{item.name} · {item.symbol}</Text>
                      <Tag color={paperTrackingGroupColor(item.tracking_group)}>{paperTrackingGroupLabel(item.tracking_group)}</Tag>
                    </div>
                    <Text type="secondary">信号 {paperTrackingSignalDate(item)} · 买入 {paperTrackingEntryDate(item)} · {item.selection_label || "纸面对照"}</Text>
                    <Text>{item.entry_rule || "次一交易日收盘买入"}</Text>
                    <Text type="secondary">{item.exit_rule || "机械5日、机械10日、条件检查、10%触达止盈四轨监测"}</Text>
                    {item.thesis ? <Paragraph className="shortpick-paper-mobile-thesis">{item.thesis}</Paragraph> : null}
                  </div>
                </List.Item>
              )}
            />
          </>
        ) : (
          <Empty
            description={loading
              ? "纸面跟踪状态加载中"
              : pendingEntryDate
                ? `尚无已入场纸面记录；最新信号将在 ${pendingEntryDate} 收盘买入后进入跟踪记录。`
                : "尚无已入场纸面记录；等待首个冻结后盘后批次。"}
          />
        )}
      </Card>
    </>
  );
}

function FailureDiagnostics({
  failedRounds,
  failedCandidates,
  selectedBenchmark,
}: {
  failedRounds: ShortpickRoundView[];
  failedCandidates: ShortpickCandidateView[];
  selectedBenchmark: string;
}) {
  const hasOnlyCandidateDiagnostics = !failedRounds.length && failedCandidates.length > 0;
  return (
    <Card className="panel-card" title="对照组可交易性诊断">
      <Alert
        type={hasOnlyCandidateDiagnostics ? "info" : "warning"}
        showIcon
        message={failedRounds.length ? "本批次存在失败轮次" : "部分 LLM 候选等待下个交易日确认可交易性"}
        description={
          failedRounds.length
            ? "失败轮次、解析失败、停牌/缺行情或入场不可成交候选不会进入正常研究池。可重跑失败轮次；可交易性异常需要等待行情或人工复核。"
            : "这通常来自盘后批次的下一交易日入场校验：如果信号日之后还没有真实交易日 K 线，系统会先隔离这些候选，不把它们计入正常研究池。"
        }
      />
      {failedRounds.length ? (
        <Table
          className="shortpick-failure-table"
          rowKey="id"
          size="small"
          columns={[
            {
              title: "轮次",
              key: "round",
              render: (_, item: ShortpickRoundView) => <Text strong>{roundModelLabel(item)}</Text>,
            },
            {
              title: "分类",
              key: "category",
              render: (_, item: ShortpickRoundView) => <Tag color={item.retryable ? "gold" : "red"}>{failureCategoryLabel(item.failure_category)}</Tag>,
            },
            {
              title: "错误",
              dataIndex: "error_message",
              key: "error_message",
              render: (value?: string | null) => <Text>{value || "--"}</Text>,
            },
          ]}
          dataSource={failedRounds}
          pagination={false}
        />
      ) : null}
      {failedCandidates.length ? (
        <Table
          className="shortpick-failure-table"
          rowKey="id"
          size="small"
          columns={[
            {
              title: "标的",
              key: "symbol",
              render: (_, item: ShortpickCandidateView) => <Text strong>{`${item.name} · ${item.symbol}`}</Text>,
            },
            {
              title: "状态",
              key: "status",
              render: (_, item: ShortpickCandidateView) => <Tag color={item.display_bucket === "diagnostic" ? "gold" : "red"}>{validationSummary(item, selectedBenchmark)}</Tag>,
            },
            {
              title: "原因",
              key: "reason",
              render: (_, item: ShortpickCandidateView) => <Text>{item.diagnostic_reason || item.thesis || "--"}</Text>,
            },
          ]}
          dataSource={failedCandidates}
          pagination={false}
        />
      ) : null}
      {failedCandidates.length ? <Text type="secondary">已隔离对照组候选 {failedCandidates.length} 条，等待交易日数据或人工复核后再判断。</Text> : null}
    </Card>
  );
}

function ValidationQueueTab({
  filters,
  onFiltersChange,
  onSearch,
  queue,
  loading,
  columns,
  page,
  onPageChange,
}: {
  filters: { status: string; horizon: string; model: string; symbol: string };
  onFiltersChange: (filters: { status: string; horizon: string; model: string; symbol: string }) => void;
  onSearch: () => void;
  queue: ShortpickValidationQueueResponse | null;
  loading: boolean;
  columns: ColumnsType<ShortpickValidationQueueItem>;
  page: { current: number; pageSize: number };
  onPageChange: (pagination: TablePaginationConfig) => void;
}) {
  return (
    <Card className="panel-card shortpick-validation-card" title="历史验证">
      <Space wrap className="shortpick-filter-bar">
        <Select
          allowClear
          placeholder="验证状态"
          value={filters.status || undefined}
          options={[
            { value: "pending_forward_window", label: "待窗口" },
            { value: "pending_entry_bar", label: "待入场价" },
            { value: "pending_market_data", label: "待行情" },
            { value: "pending_benchmark_data", label: "待基准" },
            { value: "completed", label: "已完成" },
          ]}
          onChange={(value) => onFiltersChange({ ...filters, status: value ?? "" })}
        />
        <Select
          allowClear
          placeholder="周期"
          value={filters.horizon || undefined}
          options={[1, 3, 5, 10, 20].map((value) => ({ value: String(value), label: `${value}日` }))}
          onChange={(value) => onFiltersChange({ ...filters, horizon: value ?? "" })}
        />
        <Input
          className="shortpick-filter-input"
          placeholder="模型"
          value={filters.model}
          onChange={(event) => onFiltersChange({ ...filters, model: event.target.value })}
        />
        <Input
          className="shortpick-filter-input"
          placeholder="股票代码"
          value={filters.symbol}
          onChange={(event) => onFiltersChange({ ...filters, symbol: event.target.value })}
        />
        <Button onClick={onSearch} loading={loading}>查询</Button>
      </Space>
      <Table
        className="shortpick-validation-table"
        rowKey="validation_id"
        size="middle"
        loading={loading}
        columns={columns}
        dataSource={queue?.items ?? []}
        pagination={{
          current: page.current,
          pageSize: page.pageSize,
          total: queue?.total ?? 0,
          showSizeChanger: true,
          pageSizeOptions: [20, 50, 100],
        }}
        onChange={onPageChange}
      />
    </Card>
  );
}

function ModelFeedbackTab({
  feedback,
  loading,
  columns,
  selectedBenchmark,
}: {
  feedback: ShortpickModelFeedbackResponse | null;
  loading: boolean;
  columns: ColumnsType<ShortpickModelFeedbackItem>;
  selectedBenchmark: string;
}) {
  const overall = feedback?.overall ?? {};
  const checkpoints = recordValue<Record<string, unknown>>(overall, "evaluation_checkpoints");
  const checkpointStatus = String(checkpoints?.status ?? "not_ready");
  return (
    <>
      <Row gutter={[16, 16]} className="shortpick-metrics shortpick-feedback-summary">
        <Col xs={24} md={6}>
          <Statistic title="批次数" value={Number(overall.run_count ?? 0)} />
        </Col>
        <Col xs={24} md={6}>
          <Statistic title="模型轮次" value={Number(overall.round_count ?? 0)} />
        </Col>
        <Col xs={24} md={6}>
          <Statistic title="正常候选" value={Number(overall.candidate_count ?? 0)} />
        </Col>
        <Col xs={24} md={6}>
          <Statistic title="验证快照" value={Number(overall.validation_count ?? 0)} />
        </Col>
      </Row>
      <Alert
        className="panel-card"
        type={checkpointStatus === "pass" ? "success" : checkpointStatus === "fail" ? "error" : "warning"}
        showIcon
        message={`能力评估状态：${checkpointStatus === "pass" ? "通过" : checkpointStatus === "fail" ? "未通过" : "样本不足"}`}
        description={`5日正式唯一标的样本 ${Number(checkpoints?.official_5d_unique_symbol_run_count ?? 0)}；样本不足时只适合看趋势，不适合作为模型选股能力结论。`}
      />
      <Card className="panel-card" title="模型反馈">
        <Table
          className="shortpick-feedback-table"
          rowKey={(item) => `${item.provider_name}:${item.model_name}:${item.executor_kind}`}
          size="middle"
          loading={loading}
          columns={columns}
          dataSource={feedback?.models ?? []}
          expandable={{
            expandedRowRender: (item) => <FeedbackDetails item={item} selectedBenchmark={selectedBenchmark} />,
          }}
          pagination={false}
        />
      </Card>
    </>
  );
}

function FeedbackDetails({ item, selectedBenchmark }: { item: ShortpickModelFeedbackItem; selectedBenchmark: string }) {
  return (
    <div className="shortpick-feedback-detail">
      <FeedbackGroupList title="周期表现" groups={item.validation_by_horizon} selectedBenchmark={selectedBenchmark} />
      <FeedbackGroupList title="优先级表现" groups={item.validation_by_priority} selectedBenchmark={selectedBenchmark} />
      <FeedbackGroupList title="题材表现" groups={item.validation_by_theme} selectedBenchmark={selectedBenchmark} />
    </div>
  );
}

function FeedbackGroupList({ title, groups, selectedBenchmark }: { title: string; groups: ShortpickFeedbackGroup[]; selectedBenchmark: string }) {
  return (
    <div>
      <Title level={5}>{title} · {benchmarkLabel(selectedBenchmark)}</Title>
      <List
        size="small"
        dataSource={title === "周期表现" ? sortHorizonGroups(groups) : groups}
        renderItem={(group) => {
          const metric = group.benchmark_metrics?.[selectedBenchmark];
          const meanExcess = metric?.mean_excess_return ?? (selectedBenchmark === "hs300" ? group.mean_excess_return : null);
          const trimmedMean = metric?.trimmed_mean_excess_return ?? (selectedBenchmark === "hs300" ? group.trimmed_mean_excess_return : null);
          const positiveRate = metric?.positive_excess_rate ?? (selectedBenchmark === "hs300" ? group.positive_excess_rate : null);
          const pendingReasons = metric?.pending_reasons ? Object.keys(metric.pending_reasons) : [];
          return (
            <List.Item>
              <Space wrap>
                <Text strong>{group.label}</Text>
                <Text>严格来源 {group.completed_official_sample_count ?? group.completed_validation_count}/{group.official_sample_count ?? group.sample_count}</Text>
                <Text>可交易验证 {group.completed_tradable_sample_count ?? 0}/{group.tradable_sample_count ?? 0}</Text>
                <Text type="secondary">原始 {group.sample_count}</Text>
                {metric && Number(metric.available_count ?? 0) === 0 && selectedBenchmark !== "hs300" ? (
                  <Text type="secondary">{benchmarkPendingText(pendingReasons[0])}</Text>
                ) : (
                  <>
                    <Text className={`value-${valueTone(meanExcess)}`}>平均超额 {formatPercent(meanExcess)}</Text>
                    <Text className={`value-${valueTone(trimmedMean)}`}>去极值 {formatPercent(trimmedMean)}</Text>
                    <Text>正超额 {formatPercent(positiveRate)}</Text>
                  </>
                )}
                <Text type="secondary">最大回撤 {formatPercent(group.max_drawdown)}</Text>
              </Space>
            </List.Item>
          );
        }}
      />
    </div>
  );
}

function HistoricalReplayTab({
  runs,
  selectedRun,
  candidates,
  sources,
  feedback,
  aggregateFeedback,
  feedbackLoading,
  aggregateFeedbackLoading,
  marketStudy,
  marketStudyLoading,
  loading,
  selectedBenchmark,
  onSelectRun,
  onReload,
}: {
  runs: ShortpickRunView[];
  selectedRun: ShortpickRunView | null;
  candidates: ShortpickCandidateView[];
  sources: ShortpickReplaySourceResponse | null;
  feedback: ShortpickReplayFeedbackResponse | null;
  aggregateFeedback: ShortpickReplayFeedbackResponse | null;
  feedbackLoading: boolean;
  aggregateFeedbackLoading: boolean;
  marketStudy: ShortpickMarketFactorStudyResponse | null;
  marketStudyLoading: boolean;
  loading: boolean;
  selectedBenchmark: string;
  onSelectRun: (runId: number) => void;
  onReload: () => void;
}) {
  const universe = sources?.tradable_universe ?? recordValue<Record<string, unknown>>(selectedRun?.summary, "tradable_universe") ?? {};
  const sourcePacket = sources?.source_packet ?? recordValue<Record<string, unknown>>(selectedRun?.summary, "source_packet") ?? {};
  const officialCount = Number(sourcePacket.official_source_count ?? sources?.official_sources.length ?? 0);
  const diagnosticCount = Number(sourcePacket.diagnostic_source_count ?? sources?.diagnostic_sources.length ?? 0);
  const rejectedCount = Number(sourcePacket.rejected_source_count ?? sources?.rejected_sources.length ?? 0);
  const auditFailures = candidates.filter((item) => item.leakage_audit_status === "fail").length;
  const officialSamples = candidates.filter((item) => item.official_sample_eligible).length;
  const baselineFamilies = Array.from(new Set(candidates.map((item) => item.baseline_family || "llm")));
  const anyReplayLoading = loading || aggregateFeedbackLoading || feedbackLoading || marketStudyLoading;
  const runListLoading = loading && runs.length === 0;
  const replayDetailLoading = loading && Boolean(selectedRun);
  const sourcePacketLoading = replayDetailLoading && !sources;
  const candidateDetailLoading = replayDetailLoading && candidates.length === 0;

  const replayColumns: ColumnsType<ShortpickCandidateView> = [
    {
      title: "组别 / 标的",
      key: "family",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Space wrap>
            <Tag color={item.baseline_family === "llm" ? "blue" : "default"}>{baselineFamilyLabel(item.baseline_family)}</Tag>
            <Text strong>{item.name} · {item.symbol}</Text>
          </Space>
          <Text type="secondary">{topicLabel(item)}</Text>
        </Space>
      ),
      filters: baselineFamilies.map((family) => ({ text: baselineFamilyLabel(family), value: family })),
      onFilter: (value, item) => (item.baseline_family || "llm") === value,
    },
    {
      title: "泄漏审计",
      key: "audit",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Space wrap>
            <Tag color={auditStatusColor(item.leakage_audit_status)}>{auditStatusLabel(item.leakage_audit_status)}</Tag>
            {item.official_sample_eligible ? <Tag color="green">正式样本</Tag> : <Tag color="gold">诊断样本</Tag>}
            {item.universe_membership?.is_tradeable ? <Tag color="green">可交易池内</Tag> : <Tag color="red">可交易异常</Tag>}
          </Space>
          {item.leakage_audit_reasons?.length ? (
            <Text type="secondary">{item.leakage_audit_reasons.map(auditReasonLabel).join(" / ")}</Text>
          ) : (
            <Text type="secondary">数据包 {shortHash(item.source_packet_hash)}</Text>
          )}
        </Space>
      ),
    },
    {
	      title: "理由",
	      dataIndex: "thesis",
	      key: "thesis",
	      render: (value?: string | null) => <Text>{value || "暂无理由"}</Text>,
    },
    {
      title: `反馈 · ${benchmarkLabel(selectedBenchmark)}`,
      key: "validation",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Text>{validationSummary(item, selectedBenchmark)}</Text>
          <Text type="secondary">来源 {item.sources.length} · 限制 {item.limitations.length}</Text>
        </Space>
      ),
    },
  ];

  return (
    <>
      {anyReplayLoading ? (
        <Alert
          className="panel-card"
          type="info"
          showIcon
          message="历史回放数据加载中"
          description="批次、候选明细、全局统计和策略收口会分段返回；表格会在对应数据到达后自动更新。"
        />
      ) : null}
      <ReplayStatisticalSummary
        feedback={aggregateFeedback}
        loading={aggregateFeedbackLoading}
        marketStudy={marketStudy}
        marketStudyLoading={marketStudyLoading}
        selectedBenchmark={selectedBenchmark}
      />

      <Collapse
        className="shortpick-replay-diagnostics"
        items={[
          {
            key: "comparison",
            label: "模型与策略对比",
            children: (
              <ReplayFeedbackCards
                feedback={feedback}
                loading={feedbackLoading}
                marketStudy={marketStudy}
                selectedBenchmark={selectedBenchmark}
              />
            ),
          },
          {
            key: "drilldown",
            label: "批次、候选和来源审计",
            children: (
              <>
      <Card
        className="panel-card"
        title="回放批次与下钻"
        extra={<Button icon={<ReloadOutlined />} onClick={onReload} loading={loading}>刷新回放</Button>}
      >
        <Space wrap className="shortpick-filter-bar">
          <Select
            className="shortpick-run-select"
            value={selectedRun?.id}
            placeholder="选择回放批次"
            loading={loading}
            disabled={runListLoading}
            options={runs.map((run) => ({
              value: run.id,
              label: `${run.run_date} · ${statusLabel(operationalStatus(run))} · ${run.run_key}`,
            }))}
            onChange={(runId) => onSelectRun(Number(runId))}
          />
          <Tag color={statusColor(selectedRun ? operationalStatus(selectedRun) : "pending")}>
            {selectedRun ? statusLabel(operationalStatus(selectedRun)) : "无批次"}
          </Tag>
          <Text type="secondary">
            {sourcePacketLoading
              ? "正在读取该批次的封闭数据包。"
              : selectedRun
                ? `${selectedRun.run_date} · ${String(selectedRun.model_config?.rounds_per_model ?? selectedRun.model_config?.rounds ?? 0)} 轮 · 数据包 ${shortHash(sources?.source_packet_hash)}`
                : "生成历史回放后会出现在这里。"}
          </Text>
        </Space>
        {runListLoading ? (
          <Skeleton active paragraph={{ rows: 4 }} />
        ) : runs.length ? (
          <Table
            className="shortpick-replay-run-table"
            rowKey="id"
            size="small"
            loading={loading}
            columns={[
              {
                title: "日期 / 状态",
                key: "date",
                render: (_, run: ShortpickRunView) => (
                  <Space direction="vertical" size={0}>
                    <Text strong>{run.run_date}</Text>
                    <Tag color={statusColor(operationalStatus(run))}>{statusLabel(operationalStatus(run))}</Tag>
                  </Space>
                ),
              },
              {
                title: "模型 / 轮次",
                key: "rounds",
                render: (_, run: ShortpickRunView) => (
                  <Text>{String(run.summary.model_family ?? "封闭数据包模型")} · {Number(run.summary.completed_round_count ?? run.rounds.length ?? 0)} 轮</Text>
                ),
              },
              {
                title: "候选",
                key: "candidates",
                render: (_, run: ShortpickRunView) => (
                  <Space wrap>
                    <Tag>总数 {Number(run.summary.candidate_count ?? 0)}</Tag>
                    <Tag color="green">正式样本 {Number(run.summary.official_sample_count ?? 0)}</Tag>
                    <Tag color="red">泄漏失败 {Number(run.summary.leakage_failed_count ?? 0)}</Tag>
                    <Tag>对照组 {Number(run.summary.baseline_candidate_count ?? 0)}</Tag>
                  </Space>
                ),
              },
              {
                title: "封闭数据包",
                key: "packet",
                render: (_, run: ShortpickRunView) => {
                  const packet = recordValue<Record<string, unknown>>(run.summary, "source_packet") ?? {};
                  return <Text type="secondary">{shortHash(String(packet.source_packet_hash ?? ""))}</Text>;
                },
              },
            ]}
            dataSource={runs}
            pagination={{ pageSize: 6 }}
            onRow={(run) => ({ onClick: () => onSelectRun(run.id) })}
          />
        ) : (
          <Empty description="暂无历史回放批次。" />
        )}
      </Card>

      {selectedRun ? (
        <>
          <Row gutter={[16, 16]} className="shortpick-metrics">
            <Col xs={24} md={6}>
	              <div className="shortpick-metric">
	                <span>当日股票池</span>
	                {loadingAwareStrong(sourcePacketLoading, universe.total_count === undefined ? null : Number(universe.total_count))}
	                <Text type="secondary">可交易 {loadingAwareText(sourcePacketLoading, universe.tradeable_count === undefined ? null : Number(universe.tradeable_count))}</Text>
	              </div>
	            </Col>
	            <Col xs={24} md={6}>
	              <div className="shortpick-metric">
	                <span>排除原因</span>
	                {loadingAwareStrong(sourcePacketLoading, universe.excluded_count === undefined ? null : Number(universe.excluded_count))}
	                <Text type="secondary">
	                  {sourcePacketLoading
	                    ? "明细加载中"
	                    : `ST ${Number(universe.excluded_st ?? 0)} · 停牌/缺行情 ${Number(universe.excluded_missing_bar ?? 0)}`}
	                </Text>
	              </div>
	            </Col>
	            <Col xs={24} md={6}>
	              <div className="shortpick-metric">
	                <span>正式样本</span>
	                {loadingAwareStrong(candidateDetailLoading, officialSamples)}
	                <Text type="secondary">{candidateDetailLoading ? "候选验证加载中" : `泄漏失败 ${auditFailures}`}</Text>
	              </div>
	            </Col>
	            <Col xs={24} md={6}>
	              <div className="shortpick-metric">
	                <span>封闭数据包</span>
	                {loadingAwareStrong(sourcePacketLoading, sources?.source_packet_hash ? shortHash(sources.source_packet_hash) : null)}
	                <Text type="secondary">
	                  {sourcePacketLoading ? "来源清单加载中" : `正式 ${officialCount} · 诊断 ${diagnosticCount} · 剔除 ${rejectedCount}`}
	                </Text>
	              </div>
	            </Col>
	          </Row>

          <Card className="panel-card" title="模型与对照组候选明细">
            <Table
	              rowKey="id"
	              size="middle"
	              loading={loading}
	              columns={replayColumns}
	              dataSource={candidates}
	              pagination={{ pageSize: 12 }}
	              locale={{ emptyText: loading ? "候选明细加载中" : "暂无候选明细" }}
              expandable={{
                expandedRowRender: (item) => (
                  <div className="shortpick-detail-grid">
	                    <div>
	                      <Title level={5}>推荐理由 / 催化 / 风险</Title>
	                      <Paragraph>{item.thesis || "暂无推荐理由"}</Paragraph>
	                      <List size="small" dataSource={[...item.catalysts, ...item.risks, ...item.limitations]} renderItem={(text) => <List.Item>{text}</List.Item>} />
                    </div>
                    <div>
                      <Title level={5}>泄漏审计</Title>
                      <Descriptions size="small" column={1}>
                        <Descriptions.Item label="审计结论">{auditStatusLabel(item.leakage_audit_status)}</Descriptions.Item>
                        <Descriptions.Item label="疑似未来信息">{item.leakage_audit_reasons?.includes("future_leakage_suspected") ? "是" : "否"}</Descriptions.Item>
                        <Descriptions.Item label="来源晚于截点">{item.leakage_audit_reasons?.includes("source_after_cutoff") ? "是" : "否"}</Descriptions.Item>
                        <Descriptions.Item label="包外来源">{item.leakage_audit_reasons?.includes("source_not_in_packet") ? "是" : "否"}</Descriptions.Item>
                        <Descriptions.Item label="事实无来源支持">{item.leakage_audit_reasons?.includes("unsupported_claim") ? "是" : "否"}</Descriptions.Item>
                        <Descriptions.Item label="来源时间未验证">{item.leakage_audit_reasons?.includes("unverified_source_time") ? "是" : "否"}</Descriptions.Item>
                        <Descriptions.Item label="证据映射">{JSON.stringify(item.evidence_mapping ?? {})}</Descriptions.Item>
                      </Descriptions>
                    </div>
                    <div>
                      <Title level={5}>来源与收益验证</Title>
                      <SourceList candidate={item} />
                      <ValidationList items={item.validations} selectedBenchmark={selectedBenchmark} />
                    </div>
                  </div>
                ),
              }}
            />
          </Card>

	          <ReplaySourcePacket sources={sources} loading={sourcePacketLoading} />
        </>
      ) : null}
              </>
            ),
          },
        ]}
      />
    </>
  );
}

function ReplayStrategyCloseout({
  study,
  loading,
}: {
  study: ShortpickMarketFactorStudyResponse | null;
  loading: boolean;
}) {
  if (loading && !study) {
    return (
      <div className="shortpick-strategy-closeout">
        <Space direction="vertical" size={2}>
          <Title level={5}>冻结策略与对照</Title>
          <Text type="secondary">策略收口数据正在后台加载；历史回放主体不依赖这项重计算。</Text>
        </Space>
        <Skeleton active paragraph={{ rows: 4 }} />
      </div>
    );
  }

  if (!study) {
    return (
      <div className="shortpick-strategy-closeout">
        <Space direction="vertical" size={2}>
          <Title level={5}>冻结策略与对照</Title>
          <Text type="secondary">策略收口接口当前没有可展示数据。</Text>
        </Space>
        <Empty description="暂无策略收口数据" image={Empty.PRESENTED_IMAGE_SIMPLE} />
      </div>
    );
  }

  const defaultMetric = marketPortfolioMetric(study, "holdout", "ret10_turnover_cooldown");
  const attackMetric = marketPortfolioMetric(study, "holdout", "ret10_turnover");
  const gateMetric = marketPortfolioMetric(study, "holdout", "ret10_turnover_cooldown_regime_gate");
  const diversifiedMetric = marketPortfolioMetric(study, "holdout", "ret10_turnover_cooldown_diversified");
  const trainGateMetric = marketPortfolioMetric(study, "train", "ret10_turnover_cooldown_regime_gate");
  const costBps = Number(study?.config?.cost_bps ?? 20);
  const poolLimit = Number(study?.config?.pool_limit ?? 40);
  const rankLimit = Number(study?.config?.rank_limit ?? 6);
  const allowedDays = Number(study?.regime_gate?.allowed_signal_day_count ?? 0);
  const frozen = frozenStrategy(study);
  const frozenScope = frozenStrategyDataScope(study);
  const accountEligibility = recordValue<Record<string, unknown>>(frozenScope, "account_eligibility") ?? {};
  const scopeStart = String(frozenScope.signal_date_from ?? study?.data_scope?.signal_date_from ?? "--");
  const scopeEnd = String(frozenScope.signal_date_to ?? study?.data_scope?.signal_date_to ?? "--");
  const sampleNote = String(frozenScope.sample_construction_note ?? accountEligibility.rule_note ?? "已按当前账户可执行范围复核。");
  const frozenSummary = frozenStrategySummary(study);
  const productionEvidence = frozenStrategyProductionEvidence(study);
  const failedChecks = recordValue<string[]>(productionEvidence, "failed_check_ids") ?? [];
  const costStress = recordValue<Record<string, Record<string, unknown>>>(productionEvidence, "cost_stress") ?? {};
  const indexRefs = frozenBenchmarkReferences(study);
  const paperControls = frozenStrategyPaperControls(study);
  const legacySecondControl = paperControls["ret10_turnover_second_market_positive_cooldown_stop8"] ?? {};
  const legacySecondSummary = recordValue<Record<string, unknown>>(legacySecondControl, "summary") ?? {};
  const marketBenchmarkReturn = Number(frozenSummary.benchmark_total_return ?? 0);
  const marketBenchmarkDrawdown = Number(frozenSummary.benchmark_max_drawdown ?? 0);

  return (
    <div className="shortpick-strategy-closeout">
      <Space direction="vertical" size={2}>
        <Title level={5}>冻结策略与对照</Title>
	        <Text type="secondary">
	          {`当前正式进入纸面跟踪的是低换手上升趋势；旧第二候选、LLM自由选股和原动量规则作为对照。账户可执行复核样本范围 ${scopeStart} 至 ${scopeEnd}，收益已扣除单次 ${costBps}bp 成本。`}
	        </Text>
      </Space>
      <Alert
        showIcon
        type="warning"
        message="冻结纸面策略：账户可执行性复核未通过"
        description={`${String(frozen.mode ?? "每日滚动 5x1万；持有天数按交易日计算")}；当前新开户普通账户口径长样本超额 ${formatPercent(Number(frozenSummary.excess_total_return ?? 0))}。${sampleNote} 正式前向仍会记录机械5日、机械10日、条件检查和10%触达止盈四条退出轨道；当前仍处于真实前向观察阶段，尚未形成生产级证明。`}
      />
      <Row gutter={[12, 12]}>
        <Col xs={24} md={12} xl={6}>
          <div className="shortpick-replay-family-summary">
            <span>纸面主策略</span>
            <strong>{String(frozen.label ?? "低换手上升趋势四轨监测").replace("冻结纸面策略：", "")}</strong>
            <Text className={`value-${valueTone(Number(frozenSummary.excess_total_return ?? 0))}`}>长样本超额 {formatPercent(Number(frozenSummary.excess_total_return ?? 0))}</Text>
            <Text type="secondary">交易 {formatNumber(Number(frozenSummary.trade_count ?? 0))} 次 · 最大回撤 {formatPercent(Number(frozenSummary.max_drawdown ?? 0))}</Text>
            <Text type="secondary">100bp成本压力 {formatPercent(Number(costStress["100"]?.excess_total_return ?? 0))}</Text>
          </div>
        </Col>
        <Col xs={24} md={12} xl={6}>
          <div className="shortpick-replay-family-summary">
            <span>旧主线对照</span>
            <strong>第二候选四轨退出监测</strong>
            <Text className={`value-${valueTone(Number(legacySecondSummary.excess_total_return ?? 0))}`}>长样本超额 {formatPercent(Number(legacySecondSummary.excess_total_return ?? 0))}</Text>
            <Text type="secondary">交易 {formatNumber(Number(legacySecondSummary.trade_count ?? 0))} 次 · 最大回撤 {formatPercent(Number(legacySecondSummary.max_drawdown ?? 0))}</Text>
            <Text type="secondary">用于和新冻结主线做真实纸面对比。</Text>
          </div>
        </Col>
        <Col xs={24} md={12} xl={6}>
          <div className="shortpick-replay-family-summary">
            <span>对照一</span>
            <strong>默认动量降追高</strong>
            <Text className={`value-${valueTone(defaultMetric?.mean_net_excess_return)}`}>样本外平均超额 {formatPercent(defaultMetric?.mean_net_excess_return)}</Text>
            <Text type="secondary">去极值 {formatPercent(defaultMetric?.trimmed_mean_net_excess_return)} · 胜率 {formatPercent(defaultMetric?.positive_net_excess_rate)}</Text>
            <Text type="secondary">从每日候选池扩大到 {poolLimit} 只，再选 {rankLimit} 只。</Text>
          </div>
        </Col>
        <Col xs={24} md={12} xl={6}>
          <div className="shortpick-replay-family-summary">
            <span>对照二</span>
            <strong>进攻动量换手</strong>
            <Text className={`value-${valueTone(attackMetric?.mean_net_excess_return)}`}>样本外平均超额 {formatPercent(attackMetric?.mean_net_excess_return)}</Text>
            <Text type="secondary">启用条件允许日 {formatNumber(allowedDays)} · 样本内 {formatPercent(trainGateMetric?.mean_net_excess_return)}</Text>
            <Text type="secondary">用于比较收益，不作为当前纸面主策略。</Text>
          </div>
        </Col>
        <Col xs={24} md={12} xl={6}>
          <div className="shortpick-replay-family-summary">
            <span>市场参照</span>
            <strong>等权市场基准</strong>
            <Text type="secondary">同期收益 {formatPercent(marketBenchmarkReturn)} · 最大回撤 {formatPercent(marketBenchmarkDrawdown)}</Text>
            <Text type="secondary">{indexBenchmarkReferenceText(indexRefs)}</Text>
            <Text type="secondary">行业分散诊断：{formatPercent(diversifiedMetric?.mean_net_excess_return)}</Text>
          </div>
        </Col>
      </Row>
    </div>
  );
}

function ReplayStatisticalSummary({
  feedback,
  loading,
  marketStudy,
  marketStudyLoading,
  selectedBenchmark,
}: {
  feedback: ShortpickReplayFeedbackResponse | null;
  loading: boolean;
  marketStudy: ShortpickMarketFactorStudyResponse | null;
  marketStudyLoading: boolean;
  selectedBenchmark: string;
}) {
  const overall = feedback?.overall ?? {};
  const gate = recordValue<Record<string, unknown>>(overall, "statistical_gate") ?? {};
  const horizonRows = sortHorizonGroups(recordValue<ShortpickFeedbackGroup[]>(overall, "validation_by_horizon") ?? [])
    .map((group) => {
      const metric = group.benchmark_metrics?.[selectedBenchmark];
      return {
        ...group,
        mean_excess_return: metric?.mean_excess_return ?? group.mean_excess_return,
        positive_excess_rate: metric?.positive_excess_rate ?? group.positive_excess_rate,
      };
    });
  const familyRows = replayFamilyDisplayRows(feedback, marketStudy);
  const completedSamples = Number(gate.completed_official_sample_count ?? overall.completed_official_sample_count ?? 0);
  const completedTradableSamples = Number(gate.completed_tradable_sample_count ?? overall.completed_tradable_sample_count ?? 0);
  const completedDates = Number(gate.completed_date_count ?? 0);
  const completedTradableDates = Number(gate.completed_tradable_date_count ?? 0);
  const status = String(gate.status ?? "exploratory");
  const gateReason = replayGateReasonText(gate.reason);
  const horizonByKey = new Map(horizonRows.map((group) => [String(group.group_key), group]));
  const candidateFamilyRows = (feedback?.families ?? []).map((family) => ({
    ...family,
    display_source: "candidate_replay" as const,
  }));
  const portfolioFamilyRows = replayPortfolioControlFamilyRows(marketStudy);
  const familyFiveDayRows = familyRows
    .filter((family) => family.display_source !== "portfolio_backtest")
    .map((family) => {
      const display = replayFamilyMetric(family, selectedBenchmark);
      return {
        family,
        value: display.value,
        sampleCount: display.sampleCount,
      };
    })
    .filter((item) => item.value !== null && item.value !== undefined);
  const topFamily = [...familyFiveDayRows]
    .filter((item) => item.sampleCount >= 10)
    .sort((left, right) => Number(right.value ?? -999) - Number(left.value ?? -999))[0];
  const llmFiveDay = familyFiveDayRows.find((item) => item.family.baseline_family === "llm");
  const defaultFiveDay = familyFiveDayRows.find((item) => item.family.baseline_family === "momentum_10d_turnover_cooldown_rank");
	  const fiveDayGroup = horizonByKey.get("5");
	  const fiveDayMetric = fiveDayGroup ? selectedBenchmarkGroupMetric(fiveDayGroup, selectedBenchmark) : null;
	  const feedbackLoading = loading && !feedback;
	  const feedbackMissing = !loading && !feedback;
	  return (
	    <Card className="panel-card shortpick-replay-readout" title="历史回放核心读数">
	      <Alert
	        showIcon
	        type={feedbackMissing ? "warning" : replayGateAlertType(status)}
	        message={feedbackLoading ? "全局统计加载中" : feedbackMissing ? "当前结论：暂无统计数据" : `当前结论：${replayGateLabel(status)}`}
	        description={
	          feedbackLoading
	            ? "历史回放主体已先加载；全局统计正在后台聚合，完成后会自动补齐这里的读数。"
	            : feedbackMissing
	              ? "全局统计接口当前没有返回可展示数据；这和正在加载不同，刷新后仍为空才代表暂无统计产物。"
	            : `无上下文直接查询能否短投选股：只看模型当时给出的股票，事后按 1 / 3 / 5 / 10 / 20 日验证。当前覆盖 ${Number(overall.unique_replay_date_count ?? 0)} 个历史日期、${Number(overall.run_count ?? 0)} 个回放批次；严格来源样本 ${completedSamples}，可交易验证样本 ${completedTradableSamples}。${gateReason}`
	        }
	      />
	      <div className="shortpick-replay-question-grid">
	        <div>
	          <span>当前能否下结论</span>
	          <strong>{feedbackLoading ? "加载中" : feedbackMissing ? "暂无统计" : status === "ready" ? "可以做初步比较" : "继续补样本"}</strong>
	          <Text type="secondary">{feedbackLoading ? "等待全局统计接口返回。" : feedbackMissing ? "统计产物为空。" : `严格来源 ${completedSamples} 个，覆盖 ${completedDates} 日；可交易验证 ${completedTradableSamples} 个，覆盖 ${completedTradableDates} 日。`}</Text>
	        </div>
	        <div>
	          <span>当前领先组</span>
	          <strong>{feedbackLoading ? "加载中" : topFamily ? baselineFamilyLabel(topFamily.family.baseline_family) : "暂无稳定领先组"}</strong>
	          <Text type="secondary">{feedbackLoading ? "统计完成后显示领先组。" : `严格来源 ${formatPercent(topFamily?.value)}；可交易 ${formatPercent(topFamily?.family ? replayFamilyMetric(topFamily.family, selectedBenchmark).tradableValue : null)}。`}</Text>
	        </div>
	        <div>
	          <span>LLM 原选位置</span>
	          <strong>{feedbackLoading ? "加载中" : formatPercent(llmFiveDay?.value)}</strong>
	          <Text type="secondary">{feedbackLoading ? "等待模型对照统计。" : `严格来源 ${formatPercent(llmFiveDay?.value)}；可交易 ${formatPercent(llmFiveDay?.family ? replayFamilyMetric(llmFiveDay.family, selectedBenchmark).tradableValue : null)}。`}</Text>
	        </div>
	        <div>
	          <span>核心观察周期</span>
	          <strong>{feedbackLoading ? "加载中" : formatPercent(fiveDayMetric?.meanExcessReturn)}</strong>
	          <Text type="secondary">{feedbackLoading ? "等待周期统计。" : `严格来源均值；可交易 ${formatPercent(fiveDayMetric?.tradableMeanExcessReturn)}。`}</Text>
	        </div>
	      </div>
	      <div className="shortpick-replay-horizon-strip">
	        {HORIZON_ORDER.map((horizon) => {
	          const group = horizonByKey.get(String(horizon));
	          const metric = group ? selectedBenchmarkGroupMetric(group, selectedBenchmark) : null;
	          return (
	            <div key={horizon} className="shortpick-replay-horizon-tile">
	              <span>{horizon}日</span>
	              <strong className={`value-${valueTone(metric?.meanExcessReturn)}`}>{feedbackLoading ? "加载中" : formatPercent(metric?.meanExcessReturn)}</strong>
	              <Text type="secondary">
	                {feedbackLoading ? "样本数加载中" : `严格来源 ${Number(group?.completed_official_sample_count ?? 0)}/${Number(group?.official_sample_count ?? 0)}`}
	              </Text>
	              <Text type="secondary">{feedbackLoading ? "可交易统计加载中" : `可交易 ${formatPercent(metric?.tradableMeanExcessReturn)} · ${Number(group?.completed_tradable_sample_count ?? 0)}个`}</Text>
	            </div>
	          );
	        })}
	      </div>
      <Collapse
        className="shortpick-replay-diagnostics"
        items={[
          {
            key: "strategy",
            label: "策略收口和完整统计表",
            children: (
              <>
                <ReplayStrategyCloseout study={marketStudy} loading={marketStudyLoading} />
                <ReplayDualTestMatrix
                  feedback={feedback}
                  marketStudy={marketStudy}
                  selectedBenchmark={selectedBenchmark}
                  loading={(loading && !feedback) || marketStudyLoading}
                />
                <Table
                  className="shortpick-replay-stat-table"
                  rowKey="group_key"
                  size="small"
                  loading={loading && !feedback}
                  pagination={false}
                  columns={[
                    { title: "周期", render: (_, item: ShortpickFeedbackGroup) => `${item.group_key}日` },
                    {
                      title: "样本",
                      render: (_, item: ShortpickFeedbackGroup) => (
                        <Space direction="vertical" size={0}>
                          <Text>严格来源 {Number(item.completed_official_sample_count ?? 0)} / {Number(item.official_sample_count ?? 0)}</Text>
                          <Text type="secondary">可交易验证 {Number(item.completed_tradable_sample_count ?? 0)} / {Number(item.tradable_sample_count ?? 0)}</Text>
                        </Space>
                      ),
                    },
                    {
                      title: `平均超额 · ${benchmarkLabel(selectedBenchmark)}`,
                      render: (_, item: ShortpickFeedbackGroup) => (
                        <Space direction="vertical" size={0}>
                          <Text className={`value-${valueTone(item.mean_excess_return)}`}>严格来源 {formatPercent(item.mean_excess_return)}</Text>
                          <Text className={`value-${valueTone(item.tradable_mean_excess_return)}`}>可交易 {formatPercent(item.tradable_mean_excess_return)}</Text>
                        </Space>
                      ),
                    },
                    {
                      title: "正超额占比",
                      render: (_, item: ShortpickFeedbackGroup) => (
                        <Space direction="vertical" size={0}>
                          <Text>{formatPercent(item.positive_excess_rate)}</Text>
                          <Text type="secondary">可交易 {formatPercent(item.tradable_positive_excess_rate)}</Text>
                        </Space>
                      ),
                    },
                    { title: "状态", render: (_, item: ShortpickFeedbackGroup) => statusCountText(item.status_counts) },
                  ]}
                  dataSource={horizonRows}
                />
                <Space direction="vertical" size={2}>
                  <Title level={5}>候选逐条验证</Title>
                  <Text type="secondary">这里不看资金复利，只看每个入选股票在固定周期后的平均超额、样本数和稳健性。</Text>
                </Space>
                <Table
                  className="shortpick-replay-stat-table"
                  rowKey={(item) => `candidate:${item.baseline_family}`}
                  size="small"
                  loading={loading && !feedback}
                  pagination={false}
                  columns={[
                    { title: "组别", render: (_, item) => item.label ?? baselineFamilyLabel(item.baseline_family) },
                    { title: "口径", render: () => "候选逐条验证" },
                    {
                      title: "样本",
                      render: (_, item) => (
                        <Space direction="vertical" size={0}>
                          <Text>严格来源 {item.completed_official_sample_count} / {item.official_sample_count}</Text>
                          <Text type="secondary">可交易验证 {Number(item.completed_tradable_sample_count ?? 0)} / {Number(item.tradable_sample_count ?? 0)}</Text>
                        </Space>
                      ),
                    },
                    {
                      title: "核心表现",
                      render: (_, item) => {
                        const display = replayFamilyMetric(item, selectedBenchmark);
                        return (
                          <Space direction="vertical" size={0}>
                            <Text className={`value-${valueTone(display.value)}`}>{formatPercent(display.value)}</Text>
                            <Text type="secondary">{display.label}</Text>
                            <Text type="secondary">可交易 {formatPercent(display.tradableValue)}</Text>
                          </Space>
                        );
                      },
                    },
                    {
                      title: "补充信息",
                      render: (_, item) => (
                        <Space direction="vertical" size={0}>
                          <Text>去最佳单票 {formatPercent(recordValue<number>(item.robustness_metrics, "drop_best_symbol_mean_excess_return"))}</Text>
                          <Text type="secondary">去最佳日期 {formatPercent(recordValue<number>(item.robustness_metrics, "drop_best_date_mean_excess_return"))}</Text>
                        </Space>
                      ),
                    },
                    { title: "说明", render: () => "逐只候选统计，用来观察选股池平均质量。" },
                  ]}
                  dataSource={candidateFamilyRows}
                />
                <Space direction="vertical" size={2}>
                  <Title level={5}>组合资金曲线</Title>
                  <Text type="secondary">这里看每日滚动资金部署后的总收益、超额和最大回撤；和候选平均属于不同统计口径。</Text>
                </Space>
                <Table
                  className="shortpick-replay-stat-table"
                  rowKey={(item) => item.display_key ?? `portfolio:${item.baseline_family}`}
                  size="small"
                  loading={marketStudyLoading && !marketStudy}
                  pagination={false}
                  columns={[
                    { title: "组别", render: (_, item) => item.display_label ?? item.label ?? baselineFamilyLabel(item.baseline_family) },
                    { title: "口径", render: () => "组合资金回测" },
                    { title: "样本", render: (_, item) => `${formatNumber(Number(item.display_trade_count ?? 0))} 笔交易` },
                    {
                      title: "核心表现",
                      render: (_, item) => (
                        <Space direction="vertical" size={0}>
                          <Text className={`value-${valueTone(item.display_value)}`}>{formatPercent(item.display_value)}</Text>
                          <Text type="secondary">{item.display_metric_label ?? "长样本超额"}</Text>
                        </Space>
                      ),
                    },
                    {
                      title: "补充信息",
                      render: (_, item) => (
                        <Space direction="vertical" size={0}>
                          <Text>组合总收益 {formatPercent(item.display_total_return)}</Text>
                          <Text type="secondary">最大回撤 {formatPercent(item.display_max_drawdown)}</Text>
                        </Space>
                      ),
                    },
                    { title: "说明", render: (_, item) => item.display_note ?? "组合资金曲线回测" },
                  ]}
                  dataSource={portfolioFamilyRows}
                />
              </>
            ),
          },
        ]}
      />
    </Card>
  );
}

function ReplayFeedbackCards({
  feedback,
  loading,
  marketStudy,
  selectedBenchmark,
}: {
  feedback: ShortpickReplayFeedbackResponse | null;
  loading: boolean;
  marketStudy: ShortpickMarketFactorStudyResponse | null;
  selectedBenchmark: string;
}) {
  const factorGate = recordValue<Record<string, unknown>>(feedback?.overall, "factor_ic_gate") ?? {};
  const newsCalibration = recordValue<Record<string, unknown>>(feedback?.overall, "news_calibration") ?? {};
  const familyRows = replayFamilyDisplayRows(feedback, marketStudy);
  return (
    <Card className="panel-card" title={`模型与对照组比较 · ${benchmarkLabel(selectedBenchmark)}`} loading={loading && !feedback}>
      {familyRows.length ? (
        <Row gutter={[16, 16]} className="shortpick-feedback-summary">
          {familyRows.map((family) => {
            const display = replayFamilyMetric(family, selectedBenchmark);
            const robustness = family.robustness_metrics ?? {};
            return (
              <Col xs={24} md={12} xl={6} key={family.baseline_family}>
                <div className="shortpick-replay-family-summary">
                  <span>{family.display_source === "portfolio_backtest" ? "组合回测组" : "候选回放组"}</span>
                  <strong>{baselineFamilyLabel(family.baseline_family)}</strong>
                  <Text className={`value-${valueTone(display.value)}`}>{display.label} {formatPercent(display.value)}</Text>
                  {family.display_source === "portfolio_backtest" ? (
                    <>
                      <Text type="secondary">组合总收益 {formatPercent(family.display_total_return)} · 交易 {formatNumber(Number(family.display_trade_count ?? 0))} 次</Text>
                      <Text type="secondary">最大回撤 {formatPercent(family.display_max_drawdown)}</Text>
                    </>
                  ) : (
                    <>
                      <Text type="secondary">严格来源 {family.completed_official_sample_count}/{family.official_sample_count}</Text>
                      <Text type="secondary">可交易验证 {Number(family.completed_tradable_sample_count ?? 0)}/{Number(family.tradable_sample_count ?? 0)} · {formatPercent(display.tradableValue)}</Text>
                      <Text type="secondary">去最佳单票 {formatPercent(recordValue<number>(robustness, "drop_best_symbol_mean_excess_return"))}</Text>
                      <Text type="secondary">去最佳日期 {formatPercent(recordValue<number>(robustness, "drop_best_date_mean_excess_return"))}</Text>
                    </>
                  )}
                </div>
              </Col>
            );
          })}
        </Row>
      ) : (
        <Empty description={loading ? "批次统计正在后台加载" : "暂无模型与对照组回放统计"} />
      )}
      <Collapse
        className="shortpick-replay-diagnostics"
        items={[{
          key: "diagnostics",
          label: "补充诊断条件",
          children: (
            <Row gutter={[16, 16]}>
              <Col xs={24} md={12}>
                <Alert
                  type={factorGate.status === "eligible" ? "success" : "warning"}
                  showIcon
                  message={`因子稳定性诊断：${factorDiagnosticStatusLabel(String(factorGate.status ?? "not_ready"))}`}
                  description={`截面股票数 ${Number(factorGate.cross_section_stock_count ?? 0)}；有效窗口 ${Number(factorGate.effective_window_count ?? 0)}；${String(factorGate.reason ?? "小样本只做诊断，不驱动权重。")}`}
                />
              </Col>
              <Col xs={24} md={12}>
                <Alert
                  type={newsCalibration.status === "ready" ? "success" : "warning"}
                  showIcon
                  message={`新闻因子校准：${factorDiagnosticStatusLabel(String(newsCalibration.status ?? "not_ready"))}`}
                  description={`新闻来源 ${Number(newsCalibration.news_count ?? 0)}；${String(newsCalibration.reason ?? "新闻覆盖通过不等于 alpha 显著。")}`}
                />
              </Col>
            </Row>
          ),
        }]}
      />
    </Card>
  );
}

function ReplaySourcePacket({ sources, loading }: { sources: ShortpickReplaySourceResponse | null; loading: boolean }) {
  const sourceRows = [
    ...(sources?.official_sources ?? []),
    ...(sources?.diagnostic_sources ?? []),
    ...(sources?.rejected_sources ?? []),
  ];
  return (
    <Card className="panel-card" title="封闭数据包与来源清单">
      {loading && !sources ? (
        <Skeleton active paragraph={{ rows: 3 }} />
      ) : (
        <Descriptions size="small" column={{ xs: 1, md: 3 }}>
          <Descriptions.Item label="回放截点">{sources?.as_of_cutoff || "暂无数据"}</Descriptions.Item>
          <Descriptions.Item label="数据包指纹">{sources?.source_packet_hash || "暂无数据"}</Descriptions.Item>
          <Descriptions.Item label="数据包编号">{sources?.source_packet_id || "暂无数据"}</Descriptions.Item>
        </Descriptions>
      )}
      <Table
        rowKey={(item, index) => item.source_id || item.url || item.title || `source-${index ?? 0}`}
        size="small"
        loading={loading}
        columns={[
          {
            title: "状态",
            key: "status",
            render: (_, item) => (
              <Space direction="vertical" size={0}>
                <Tag color={item.status === "official" ? "green" : item.status === "diagnostic" ? "gold" : "red"}>
                  {item.status === "diagnostic" ? "诊断" : item.status === "rejected" ? "剔除" : "正式"}
                </Tag>
                {item.reject_reason ? <Text type="secondary">{item.reject_reason}</Text> : null}
              </Space>
            ),
          },
          {
            title: "来源",
            key: "source",
            render: (_, item) => (
              <Space direction="vertical" size={0}>
                <a href={item.url || undefined} target="_blank" rel="noreferrer">{item.title || item.url || item.source_id || "未命名来源"}</a>
                <Text type="secondary">{item.source_id || "无来源编号"} · {item.source_type || "news"}</Text>
              </Space>
            ),
          },
          {
            title: "时间",
            key: "time",
            render: (_, item) => (
              <Space direction="vertical" size={0}>
                <Text>{item.published_at || "发布时间未确认"}</Text>
                <Text type="secondary">抓取时间 {item.fetched_at || "未记录"}</Text>
              </Space>
            ),
          },
          {
            title: "关联",
            key: "linked",
            render: (_, item) => <Text>{item.linked_symbols?.join(" / ") || "暂无关联标的"}</Text>,
          },
        ]}
        dataSource={sourceRows}
        pagination={{ pageSize: 8 }}
        locale={{ emptyText: loading ? "来源清单加载中" : "暂无来源清单" }}
      />
    </Card>
  );
}

function roundColumns(): ColumnsType<ShortpickRoundView> {
  return [
    {
      title: "模型轮次",
      key: "model",
      render: (_, item) => <Text strong>{roundModelLabel(item)}</Text>,
    },
    {
      title: "状态",
      dataIndex: "status",
      key: "status",
      render: (value: string) => <Tag color={statusColor(value)}>{statusLabel(value)}</Tag>,
    },
    {
      title: "推荐",
      key: "pick",
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Text>{item.stock_name && item.symbol ? `${item.stock_name} · ${item.symbol}` : "--"}</Text>
          <Text type="secondary">{item.theme || "未归类"}</Text>
        </Space>
      ),
    },
    {
      title: "理由",
      dataIndex: "thesis",
      key: "thesis",
      render: (value: string | null) => <Text>{value || "--"}</Text>,
    },
  ];
}

function SourceList({ candidate }: { candidate: ShortpickCandidateView }) {
  return (
    <>
      <List
        size="small"
        dataSource={candidate.sources}
        renderItem={(source) => (
          <List.Item>
            <Space direction="vertical" size={0}>
              <Space wrap>
                <a href={source.url || undefined} target="_blank" rel="noreferrer">{source.title || source.url || "未命名来源"}</a>
                <Tag color={sourceCredibilityColor(source.credibility_status)}>
                  {sourceCredibilityLabel(source.credibility_status)}
                  {source.http_status ? ` ${source.http_status}` : ""}
                </Tag>
                <Tag>{sourceAuthorityLabel(source.authority_class)}</Tag>
                <Tag color={source.support_status === "supported_by_source_text" ? "green" : "gold"}>
                  {sourceSupportLabel(source.support_status)}
                </Tag>
              </Space>
              <Text type="secondary">{source.published_at || "发布时间未声明"} · {source.why_it_matters || "未说明"}</Text>
              {source.credibility_reason ? <Text type="secondary">校验：{source.credibility_reason}</Text> : null}
            </Space>
          </List.Item>
        )}
      />
      {candidate.raw_round?.raw_answer ? (
        <Collapse
          className="shortpick-raw-collapse"
          items={[{
            key: "raw",
            label: "原始模型输出",
            children: <pre className="shortpick-raw-answer">{candidate.raw_round?.raw_answer}</pre>,
          }]}
        />
      ) : null}
    </>
  );
}

function ValidationList({ items, selectedBenchmark }: { items: ShortpickValidationView[]; selectedBenchmark: string }) {
  if (!items.length) {
    return <Text type="secondary">暂无验证窗口。</Text>;
  }
  return (
    <List
      size="small"
      dataSource={items}
      renderItem={(item) => {
        const metric = benchmarkMetric(item, selectedBenchmark);
        return (
          <List.Item>
            <Space direction="vertical" size={0}>
              <Space wrap>
                <Tag color={statusColor(item.status)}>{item.horizon_days}日 · {statusLabel(item.status)}</Tag>
                <Text className={`value-${valueTone(item.stock_return)}`}>个股收益 {formatPercent(item.stock_return)}</Text>
                {metric.status === "available" ? (
                  <>
                    <Text className={`value-${valueTone(metric.excess_return)}`}>超额收益 {formatPercent(metric.excess_return)}</Text>
                    <Text type="secondary">{metric.benchmark_label || benchmarkLabel(selectedBenchmark)} {formatPercent(metric.benchmark_return)}</Text>
                  </>
                ) : (
                  <Text type="secondary">{metric.benchmark_label || benchmarkLabel(selectedBenchmark)} · {benchmarkPendingText(metric.status, metric.reason)}</Text>
                )}
                <Text type="secondary">{item.exit_at ? formatDate(item.exit_at) : "等待窗口"}</Text>
                <Text type="secondary">浮盈 {formatPercent(item.max_favorable_return)} / 回撤 {formatPercent(item.max_drawdown)}</Text>
              </Space>
              {validationWindowNote(item) ? <Text type="secondary">{validationWindowNote(item)}</Text> : null}
            </Space>
          </List.Item>
        );
      }}
    />
  );
}
