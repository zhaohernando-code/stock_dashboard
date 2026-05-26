import type {
  ShortpickFeedbackGroup,
  ShortpickMarketFactorStudyResponse,
  ShortpickMarketPortfolioMetric,
  ShortpickReplayFeedbackFamily,
  ShortpickReplayFeedbackResponse,
  ShortpickRunView,
} from "../types";
import { formatNumber, formatPercent } from "../utils/format";
import { HORIZON_ORDER, statusLabel } from "./shortpickLabLabels";

export function recordValue<T>(record: Record<string, unknown> | undefined, key: string): T | undefined {
  return record?.[key] as T | undefined;
}

function horizonSortValue(value: string | number): number {
  const horizon = Number(value);
  if (!Number.isFinite(horizon)) return Number.MAX_SAFE_INTEGER;
  const index = HORIZON_ORDER.indexOf(horizon);
  return index >= 0 ? index : HORIZON_ORDER.length + horizon;
}

export function sortHorizonGroups<T extends { group_key: string | number }>(groups: T[]): T[] {
  return [...groups].sort((left, right) => horizonSortValue(left.group_key) - horizonSortValue(right.group_key));
}

export function sortHorizons(values: number[]): number[] {
  return [...values].sort((left, right) => horizonSortValue(left) - horizonSortValue(right));
}

export function validationCoverage(run: ShortpickRunView): string {
  const completed = Number(run.summary.validation_completed_count ?? run.summary.completed_validation_count ?? 0);
  const total = Number(run.summary.validation_total_count ?? 0);
  if (total) return `${completed} / ${total}`;
  const counts = recordValue<Record<string, number>>(run.summary, "validation_status_counts") ?? {};
  const derivedTotal = Object.values(counts).reduce((sum, value) => sum + Number(value || 0), 0);
  return `${completed} / ${derivedTotal}`;
}

export function primaryBenchmarkLabel(run: ShortpickRunView): string {
  const primary = recordValue<Record<string, string>>(run.summary, "primary_benchmark");
  return primary?.label || "沪深300";
}

export function selectedBenchmarkGroupMetric(group: ShortpickFeedbackGroup, selectedBenchmark: string) {
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

export function marketPortfolioMetric(
  study: ShortpickMarketFactorStudyResponse | null,
  period: "train" | "holdout" | "replay_window" | "all",
  strategy: string,
): ShortpickMarketPortfolioMetric | null {
  return study?.portfolio_summary?.[period]?.[strategy] ?? null;
}

export function frozenStrategy(study: ShortpickMarketFactorStudyResponse | null): Record<string, unknown> {
  return recordValue<Record<string, unknown>>(study ? (study as unknown as Record<string, unknown>) : undefined, "frozen_paper_strategy") ?? {};
}

function frozenStrategyEvidence(study: ShortpickMarketFactorStudyResponse | null): Record<string, unknown> {
  return recordValue<Record<string, unknown>>(frozenStrategy(study), "evidence") ?? {};
}

export function frozenStrategySummary(study: ShortpickMarketFactorStudyResponse | null): Record<string, unknown> {
  return recordValue<Record<string, unknown>>(frozenStrategyEvidence(study), "summary") ?? {};
}

export function frozenStrategyDataScope(study: ShortpickMarketFactorStudyResponse | null): Record<string, unknown> {
  return recordValue<Record<string, unknown>>(frozenStrategyEvidence(study), "data_scope") ?? {};
}

export function frozenStrategyProductionEvidence(study: ShortpickMarketFactorStudyResponse | null): Record<string, unknown> {
  return recordValue<Record<string, unknown>>(frozenStrategyEvidence(study), "production_evidence") ?? {};
}

export function frozenStrategyPaperControls(study: ShortpickMarketFactorStudyResponse | null): Record<string, Record<string, unknown>> {
  return recordValue<Record<string, Record<string, unknown>>>(frozenStrategyEvidence(study), "paper_control_summaries") ?? {};
}

export function frozenBenchmarkReferences(study: ShortpickMarketFactorStudyResponse | null): Record<string, Record<string, unknown>> {
  return recordValue<Record<string, Record<string, unknown>>>(frozenStrategyEvidence(study), "benchmark_references") ?? {};
}

export function indexBenchmarkReferenceText(indexRefs: Record<string, Record<string, unknown>>): string {
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

export type ReplayFamilyDisplayRow = ShortpickReplayFeedbackFamily & {
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

export function replayPortfolioControlFamilyRows(study: ShortpickMarketFactorStudyResponse | null): ReplayFamilyDisplayRow[] {
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

export function replayFamilyDisplayRows(
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

export function replayFamilyMetric(
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

export type StrategyMetricDisplay = {
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

type StrategyDualTestConfig = {
  key: string;
  label: string;
  replayFamily?: string;
  marketStrategy?: string;
  portfolioStrategy?: string;
  note: string;
};

export const STRATEGY_DUAL_TEST_CONFIGS: StrategyDualTestConfig[] = [
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

export function marketStudyPeriodMetric(
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

export function marketStudyPortfolioMetricDisplay(
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

export function replayCandidateMetricDisplay(
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

export function rollingPortfolioMetricDisplay(
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

export function statusCountText(counts?: Record<string, number> | null): string {
  const entries = Object.entries(counts ?? {}).filter(([, value]) => Number(value) > 0);
  return entries.length ? entries.map(([key, value]) => `${statusLabel(key)} ${value}`).join(" · ") : "--";
}

export function concentrationText(metric?: ShortpickMarketPortfolioMetric | null): string {
  const concentration = metric?.concentration;
  const share = recordValue<number>(concentration, "top_industry_share");
  return `最高行业占比 ${formatPercent(share)}`;
}

export function shortHash(value?: string | null): string {
  return value ? value.slice(0, 12) : "--";
}
