import type { ShortpickPaperTrackingItem } from "../types";
import { formatDate } from "../utils/format";
import { statusLabel } from "./shortpickLabLabels";
import { paperTrackingSpecialStrategyFilter } from "./shortpickPaperTrackingStrategyGroups";

export type PaperTrackingGroupFilter =
  | ""
  | "frozen_strategy"
  | "frozen_strategy_v2"
  | "llm_paper_control"
  | "market_factor_control"
  | "market_random_control"
  | "同股冷却过滤"
  | "回撤/反转过滤"
  | "重复暴露限制";
export type PaperTrackingEntryStateFilter = "entered" | "pending" | "";
export type PaperTrackingEntryRuleFilter = "" | "next_close" | "next_open" | "same_day_intraday_current";
export type PaperTrackingExitStateFilter = "" | "mechanical_5d_done" | "mechanical_10d_done" | "take_profit_stop_loss_done" | "waiting_exit";
export type FrozenPaperTrackingGroup = "frozen_strategy" | "frozen_strategy_v2";
export type PaperTrackingEffectExitTrackKey = "mechanical_5d" | "mechanical_10d" | "take_profit_stop_loss";

const CURRENT_PAPER_TRACKING_STRATEGY_ROLES = new Set([
  "frozen_paper_primary",
  "market_factor_control_low_turnover_uptrend_next_open_entry",
  "llm_paper_control_primary",
  "market_factor_control_random_pool",
  "market_factor_control_same_symbol_cooldown_low_turnover_uptrend",
  "market_factor_control_drawdown_reversal_low_turnover_uptrend",
  "market_factor_control_repeated_exposure_low_turnover_uptrend",
]);

export interface PaperTrackingEffectObservation {
  rowKey: string;
  strategyLabel: string;
  groupFilter: PaperTrackingGroupFilter;
  exitTrackKey: PaperTrackingEffectExitTrackKey;
  exitTrackLabel: string;
  signalDate: string;
  exitTradeDay: string;
  stockReturn: number;
  evidenceBasis: string;
  retrospective: boolean;
}

export interface PaperTrackingEffectSummary {
  strategyLabel: string;
  groupFilter: PaperTrackingGroupFilter;
  exitTrackKey: PaperTrackingEffectExitTrackKey;
  exitTrackLabel: string;
  count: number;
  meanReturn: number;
  medianReturn: number;
  winRate: number;
}

export const PAPER_TRACKING_EFFECT_EXIT_TRACKS: Array<{ key: PaperTrackingEffectExitTrackKey; label: string; exitStateFilter: PaperTrackingExitStateFilter }> = [
  { key: "mechanical_5d", label: "机械5日", exitStateFilter: "mechanical_5d_done" },
  { key: "mechanical_10d", label: "机械10日", exitStateFilter: "mechanical_10d_done" },
  { key: "take_profit_stop_loss", label: "止盈止损", exitStateFilter: "take_profit_stop_loss_done" },
];

export function paperTrackingStatusLabel(value?: string | null): string {
  if (value === "tracking_active") return "已有正式标的";
  if (value === "waiting_first_frozen_run") return "等待首批";
  if (value === "no_signal") return "本批次未触发";
  if (value === "waiting_signal") return "等待信号";
  return "等待跟踪";
}

export function paperTrackingAlertType(value?: string | null): "success" | "info" | "warning" {
  if (value === "tracking_active") return "success";
  if (value === "waiting_first_frozen_run") return "warning";
  return "info";
}

export function paperTrackingGroupLabel(value?: string | null): string {
  if (value === "llm_paper_control") return "LLM纸面对照";
  if (value === "market_factor_control") return "市场因子对照";
  if (value === "market_random_control") return "同池随机基线";
  if (value === "frozen_strategy_v2") return "冻结候选 v2";
  if (value === "frozen_strategy") return "冻结策略";
  return "纸面跟踪";
}

export function paperTrackingRecordGroupLabel(item: ShortpickPaperTrackingItem): string {
  const strategyFilterKey = paperTrackingStrategyFilterKey(item);
  return strategyFilterKey || paperTrackingGroupLabel(item.tracking_group);
}

export function paperTrackingGroupColor(value?: string | null): string {
  if (value === "llm_paper_control") return "blue";
  if (value === "market_factor_control") return "cyan";
  if (value === "market_random_control") return "default";
  if (value === "frozen_strategy_v2") return "geekblue";
  if (value === "frozen_strategy") return "purple";
  return "default";
}

export function paperTrackingDisplayRank(item: ShortpickPaperTrackingItem): number {
  if (item.tracking_group === "frozen_strategy") return 0;
  if (item.tracking_group === "frozen_strategy_v2") return 1;
  if (item.tracking_group === "llm_paper_control") return 2;
  if (item.tracking_group === "market_factor_control") return 3;
  if (item.tracking_group === "market_random_control") return 4;
  return 5;
}

export function paperTrackingGovernanceViewSection(item: ShortpickPaperTrackingItem): "primary" | "deprecated" {
  if (item.governance_view_section === "deprecated") return "deprecated";
  if (item.governance_status === "retire_candidate" || item.governance_status === "retired" || item.governance_status === "inventory_archived") return "deprecated";
  return "primary";
}

export function primaryPaperTrackingRows(rows: ShortpickPaperTrackingItem[]): ShortpickPaperTrackingItem[] {
  return rows.filter((item) => paperTrackingGovernanceViewSection(item) === "primary");
}

export function deprecatedPaperTrackingRows(rows: ShortpickPaperTrackingItem[]): ShortpickPaperTrackingItem[] {
  return rows.filter((item) => paperTrackingGovernanceViewSection(item) === "deprecated");
}

export function isCurrentPaperTrackingStrategyRow(item: ShortpickPaperTrackingItem): boolean {
  if (paperTrackingGovernanceViewSection(item) === "deprecated") return false;
  if (item.tracking_role && CURRENT_PAPER_TRACKING_STRATEGY_ROLES.has(item.tracking_role)) return true;
  return item.tracking_group === "frozen_strategy"
    || item.tracking_group === "frozen_strategy_v2"
    || item.tracking_group === "llm_paper_control"
    || item.tracking_group === "market_random_control";
}

export function paperTrackingChoiceLabel(latestRun?: Record<string, unknown> | null): "跟踪中" | "待入场" {
  const now = new Date();
  const day = now.getDay();
  const minutes = now.getHours() * 60 + now.getMinutes();
  const isTradingDaytime = day >= 1 && day <= 5 && minutes >= 9 * 60 + 30 && minutes <= 15 * 60;
  if (isTradingDaytime) return "跟踪中";
  const runDate = typeof latestRun?.run_date === "string" ? latestRun.run_date : "";
  const today = localDateString(now);
  const isAfterClose = day >= 1 && day <= 5 && minutes > 15 * 60;
  if (isAfterClose && runDate !== today) return "跟踪中";
  return "待入场";
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

export function paperTrackingSignalDate(item: ShortpickPaperTrackingItem): string {
  return item.signal_date || item.run_date;
}

export function paperTrackingEntryDate(item: ShortpickPaperTrackingItem): string {
  return item.entry_date || nextWeekdayAfter(paperTrackingSignalDate(item));
}

export function paperTrackingExpectedEntryText(item: ShortpickPaperTrackingItem): string {
  const isIntraday = Boolean(item.entry_rule?.includes("盘中") || item.entry_rule?.includes("当前价"));
  const session = isIntraday ? "盘中" : item.entry_rule?.includes("开盘") ? "开盘" : "收盘";
  return `预计买入 ${paperTrackingEntryDate(item)} ${session}`;
}

export function hasPaperTrackingEntered(item: ShortpickPaperTrackingItem, today = localDateString()): boolean {
  const entryDate = paperTrackingEntryDate(item);
  return /^\d{4}-\d{2}-\d{2}$/.test(entryDate) && entryDate <= today;
}

export function paperTrackingChoiceTimingText(
  choiceLabel: "跟踪中" | "待入场",
  choiceRows: ShortpickPaperTrackingItem[],
  latestRun?: Record<string, unknown> | null,
): string {
  const runDate = typeof latestRun?.run_date === "string" ? latestRun.run_date : "";
  const signalDate = choiceRows[0] ? paperTrackingSignalDate(choiceRows[0]) : runDate;
  const entryDate = choiceRows[0] ? paperTrackingEntryDate(choiceRows[0]) : runDate ? nextWeekdayAfter(runDate) : "";
  const hasOpenEntry = choiceRows.some((item) => item.entry_rule?.includes("开盘"));
  const hasIntradayEntry = choiceRows.some((item) => item.entry_rule?.includes("盘中") || item.entry_rule?.includes("当前价"));
  if (!signalDate) return choiceLabel === "待入场" ? "信号日待确认 · 次一交易日收盘买入" : "当前跟踪信号待确认";
  if (hasIntradayEntry) {
    return `信号日 ${signalDate} · 含同日盘中当前价买入对照`;
  }
  if (hasOpenEntry) {
    return `信号日 ${signalDate} · 预计买入日 ${entryDate}，不同对照按各自入场规则执行`;
  }
  if (choiceLabel === "待入场") {
    return `信号日 ${signalDate} · 预计买入 ${entryDate} 收盘`;
  }
  return `当前跟踪 · 信号日 ${signalDate} · 入场口径为次一交易日收盘买入`;
}

export function latestPaperTrackingChoices(rows: ShortpickPaperTrackingItem[], latestRun?: Record<string, unknown> | null): ShortpickPaperTrackingItem[] {
  const primaryRows = primaryPaperTrackingRows(rows);
  if (!primaryRows.length) return [];
  const latestRunId = Number(latestRun?.id ?? 0);
  const latestRunDate = typeof latestRun?.run_date === "string" ? latestRun.run_date : "";
  const scoped = primaryRows.filter((item) => (
    latestRunId ? Number(item.run_id) === latestRunId : latestRunDate ? item.run_date === latestRunDate : false
  ));
  const source = scoped.length ? scoped : primaryRows;
  const latestDate = source.reduce((value, item) => (paperTrackingSignalDate(item) > value ? paperTrackingSignalDate(item) : value), "");
  return source
    .filter((item) => paperTrackingSignalDate(item) === latestDate)
    .sort((left, right) => (
      paperTrackingDisplayRank(left) - paperTrackingDisplayRank(right)
      || Number(left.source_rank ?? 99) - Number(right.source_rank ?? 99)
      || left.name.localeCompare(right.name, "zh-Hans-CN")
    ));
}

export function latestCurrentPaperTrackingRoundRows(
  rows: ShortpickPaperTrackingItem[],
  latestRun?: Record<string, unknown> | null,
): ShortpickPaperTrackingItem[] {
  const currentRows = primaryPaperTrackingRows(rows).filter(isCurrentPaperTrackingStrategyRow);
  if (!currentRows.length) return [];
  const latestRunId = Number(latestRun?.id ?? 0);
  const latestRunDate = typeof latestRun?.run_date === "string" ? latestRun.run_date : "";
  const scoped = currentRows.filter((item) => (
    latestRunId ? Number(item.run_id) === latestRunId : latestRunDate ? item.run_date === latestRunDate : false
  ));
  const source = scoped.length ? scoped : latestPaperTrackingChoices(currentRows, latestRun);
  return source
    .slice()
    .sort((left, right) => (
      paperTrackingDisplayRank(left) - paperTrackingDisplayRank(right)
      || Number(left.source_rank ?? 99) - Number(right.source_rank ?? 99)
      || left.name.localeCompare(right.name, "zh-Hans-CN")
    ));
}

export function latestPaperTrackingChoiceForGroup(
  rows: ShortpickPaperTrackingItem[],
  group: FrozenPaperTrackingGroup,
): ShortpickPaperTrackingItem | null {
  return primaryPaperTrackingRows(rows)
    .filter((item) => item.tracking_group === group)
    .sort((left, right) => (
      paperTrackingSignalDate(right).localeCompare(paperTrackingSignalDate(left))
      || paperTrackingEntryDate(right).localeCompare(paperTrackingEntryDate(left))
      || Number(left.source_rank ?? 99) - Number(right.source_rank ?? 99)
      || left.name.localeCompare(right.name, "zh-Hans-CN")
    ))[0] ?? null;
}

export function latestFrozenPaperTrackingChoices(rows: ShortpickPaperTrackingItem[]): ShortpickPaperTrackingItem[] {
  return [
    latestPaperTrackingChoiceForGroup(rows, "frozen_strategy"),
    latestPaperTrackingChoiceForGroup(rows, "frozen_strategy_v2"),
  ].filter((item): item is ShortpickPaperTrackingItem => Boolean(item));
}

export function latestPaperTrackingSignalDate(rows: ShortpickPaperTrackingItem[], latestRun?: Record<string, unknown> | null): string {
  const choices = latestPaperTrackingChoices(rows, latestRun);
  return choices[0] ? paperTrackingSignalDate(choices[0]) : typeof latestRun?.run_date === "string" ? latestRun.run_date : "";
}

export function nextPendingEntryDate(rows: ShortpickPaperTrackingItem[]): string {
  const today = localDateString();
  return rows
    .map((item) => paperTrackingEntryDate(item))
    .filter((value) => /^\d{4}-\d{2}-\d{2}$/.test(value) && value > today)
    .sort()[0] ?? "";
}

export function paperTrackingEntryRuleKey(item: ShortpickPaperTrackingItem): PaperTrackingEntryRuleFilter {
  const entryRule = item.entry_rule ?? "";
  if (entryRule.includes("开盘")) return "next_open";
  if (entryRule.includes("盘中") || entryRule.includes("当前价")) return "same_day_intraday_current";
  return "next_close";
}

export function paperTrackingStrategyFilterKey(item: ShortpickPaperTrackingItem): PaperTrackingGroupFilter {
  return paperTrackingSpecialStrategyFilter(item);
}

export function paperTrackingGroupFilterMatches(item: ShortpickPaperTrackingItem, filter: PaperTrackingGroupFilter): boolean {
  if (!filter) return true;
  if (filter === "同股冷却过滤" || filter === "回撤/反转过滤" || filter === "重复暴露限制") {
    return paperTrackingStrategyFilterKey(item) === filter;
  }
  return item.tracking_group === filter;
}

export function paperTrackingSearchText(item: ShortpickPaperTrackingItem): string {
  return [
    item.symbol,
    item.name,
    paperTrackingSignalDate(item),
    paperTrackingEntryDate(item),
    paperTrackingGroupLabel(item.tracking_group),
    item.selection_label,
    item.control_label,
    item.entry_rule,
    item.exit_rule,
    item.thesis,
    item.evidence_basis,
    item.governance_status,
    item.governance_strategy_id,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function paperTrackingExitTracks(item: ShortpickPaperTrackingItem): Record<string, unknown>[] {
  return Array.isArray(item.paper_tracking_exit_tracks) ? item.paper_tracking_exit_tracks : [];
}

function isRetrospectiveReplayPaperTrackingRow(item: ShortpickPaperTrackingItem): boolean {
  return item.retrospective === true || item.evidence_basis === "retrospective_forward_replay";
}

export function paperTrackingPrimaryExitTrack(item: ShortpickPaperTrackingItem): Record<string, unknown> | null {
  const tracks = paperTrackingExitTracks(item);
  return tracks.find((track) => track.key === "mechanical_5d") ?? tracks[0] ?? null;
}

function paperTrackingExitTrackSortValue(track: Record<string, unknown>): number {
  const key = String(track.key ?? "");
  if (key === "mechanical_5d") return 0;
  if (key === "mechanical_10d") return 1;
  if (key === "take_profit_stop_loss") return 2;
  if (key === "conditional_5_to_10d") return 3;
  if (key === "take_profit_10pct") return 4;
  return 5;
}

export function paperTrackingDisplayExitTracks(item: ShortpickPaperTrackingItem): Record<string, unknown>[] {
  return [...paperTrackingExitTracks(item)]
    .filter((track) => track.exit_trade_day || typeof track.stock_return === "number")
    .sort((left, right) => paperTrackingExitTrackSortValue(left) - paperTrackingExitTrackSortValue(right));
}

export function paperTrackingEffectExitTrackLabel(key: string): string {
  return PAPER_TRACKING_EFFECT_EXIT_TRACKS.find((track) => track.key === key)?.label ?? String(key || "退出");
}

export function paperTrackingEffectExitStateFilter(key: string): PaperTrackingExitStateFilter {
  return PAPER_TRACKING_EFFECT_EXIT_TRACKS.find((track) => track.key === key)?.exitStateFilter ?? "";
}

function isPaperTrackingEffectExitTrackKey(value: unknown): value is PaperTrackingEffectExitTrackKey {
  return PAPER_TRACKING_EFFECT_EXIT_TRACKS.some((track) => track.key === value);
}

function paperTrackingMean(values: number[]): number {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : 0;
}

function paperTrackingMedian(values: number[]): number {
  if (!values.length) return 0;
  const sorted = [...values].sort((left, right) => left - right);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

export function paperTrackingEffectObservations(rows: ShortpickPaperTrackingItem[]): PaperTrackingEffectObservation[] {
  return rows.flatMap((item) => {
    const groupFilter = (paperTrackingStrategyFilterKey(item) || item.tracking_group || "") as PaperTrackingGroupFilter;
    const strategyLabel = paperTrackingRecordGroupLabel(item);
    const signalDate = paperTrackingSignalDate(item);
    const rowKey = String(item.combined_ledger_row_id || item.candidate_id || `${item.symbol}:${signalDate}`);
    return paperTrackingDisplayExitTracks(item)
      .filter((track) => isPaperTrackingEffectExitTrackKey(track.key) && typeof track.stock_return === "number")
      .map((track) => ({
        rowKey,
        strategyLabel,
        groupFilter,
        exitTrackKey: track.key as PaperTrackingEffectExitTrackKey,
        exitTrackLabel: paperTrackingEffectExitTrackLabel(String(track.key)),
        signalDate,
        exitTradeDay: String(track.exit_trade_day ?? item.exit_at ?? ""),
        stockReturn: Number(track.stock_return),
        evidenceBasis: String(item.evidence_basis || "true_forward_tracking"),
        retrospective: item.retrospective === true,
      }));
  });
}

export function paperTrackingEffectSummaries(rows: ShortpickPaperTrackingItem[]): PaperTrackingEffectSummary[] {
  const groups = new Map<string, PaperTrackingEffectObservation[]>();
  for (const observation of paperTrackingEffectObservations(rows)) {
    const key = `${observation.strategyLabel}\u0000${observation.exitTrackKey}`;
    groups.set(key, [...(groups.get(key) ?? []), observation]);
  }
  return [...groups.values()]
    .map((observations) => {
      const first = observations[0];
      const values = observations.map((item) => item.stockReturn);
      return {
        strategyLabel: first.strategyLabel,
        groupFilter: first.groupFilter,
        exitTrackKey: first.exitTrackKey,
        exitTrackLabel: first.exitTrackLabel,
        count: values.length,
        meanReturn: paperTrackingMean(values),
        medianReturn: paperTrackingMedian(values),
        winRate: values.filter((value) => value > 0).length / values.length,
      };
    })
    .sort((left, right) => (
      left.strategyLabel.localeCompare(right.strategyLabel, "zh-Hans-CN")
      || PAPER_TRACKING_EFFECT_EXIT_TRACKS.findIndex((track) => track.key === left.exitTrackKey)
        - PAPER_TRACKING_EFFECT_EXIT_TRACKS.findIndex((track) => track.key === right.exitTrackKey)
    ));
}

function paperTrackingMechanical5dExitTrack(item: ShortpickPaperTrackingItem): Record<string, unknown> | null {
  return paperTrackingExitTracks(item).find((track) => track.key === "mechanical_5d") ?? null;
}

export function hasPaperTrackingMechanical5dExit(item: ShortpickPaperTrackingItem): boolean {
  return paperTrackingMechanical5dExitTrack(item) !== null;
}

export function paperTrackingMechanical10dExitTrack(item: ShortpickPaperTrackingItem): Record<string, unknown> | null {
  return paperTrackingExitTracks(item).find((track) => track.key === "mechanical_10d") ?? null;
}

export function hasPaperTrackingMechanical10dExit(item: ShortpickPaperTrackingItem): boolean {
  return paperTrackingMechanical10dExitTrack(item) !== null;
}

function paperTrackingRiskExitTrack(item: ShortpickPaperTrackingItem): Record<string, unknown> | null {
  return paperTrackingExitTracks(item).find((track) => track.key === "take_profit_stop_loss") ?? null;
}

export function hasPaperTrackingRiskExit(item: ShortpickPaperTrackingItem): boolean {
  return paperTrackingRiskExitTrack(item) !== null;
}

export function paperTrackingTrackExitDay(track: Record<string, unknown> | null | undefined, fallback: ShortpickPaperTrackingItem): string {
  return String(track?.exit_trade_day ?? fallback.exit_at ?? "");
}

export function paperTrackingTrackReturn(track: Record<string, unknown> | null | undefined, fallback: ShortpickPaperTrackingItem): number | null {
  if (track && typeof track.stock_return === "number") return track.stock_return;
  return typeof fallback.stock_return === "number" ? fallback.stock_return : null;
}

function paperTrackingPriorityExitTrack(item: ShortpickPaperTrackingItem): Record<string, unknown> | null {
  return paperTrackingMechanical10dExitTrack(item) ?? paperTrackingMechanical5dExitTrack(item) ?? paperTrackingPrimaryExitTrack(item);
}

export function paperTrackingExitDay(item: ShortpickPaperTrackingItem): string {
  const track = paperTrackingPrimaryExitTrack(item);
  return paperTrackingTrackExitDay(track, item);
}

export function paperTrackingExitText(item: ShortpickPaperTrackingItem): string {
  const track = paperTrackingPrimaryExitTrack(item);
  if (track) {
    const label = String(track.label ?? "退出");
    const exitDay = String(track.exit_trade_day ?? item.exit_at ?? "");
    return `${label}${exitDay ? ` ${exitDay}` : ""}`;
  }
  if (isRetrospectiveReplayPaperTrackingRow(item)) return "等待窗口";
  if (item.validation_status === "completed" && item.exit_at) {
    return `${Number(item.validation_horizon_days ?? 0) || "--"}日 ${formatDate(item.exit_at)}`;
  }
  if (item.validation_status && item.validation_status !== "not_started") return statusLabel(item.validation_status);
  return "等待窗口";
}

export function paperTrackingTrackExitText(track: Record<string, unknown>, fallback: ShortpickPaperTrackingItem): string {
  const label = String(track.label ?? "退出");
  const exitDay = paperTrackingTrackExitDay(track, fallback);
  return `${label}${exitDay ? ` ${exitDay}` : ""}`;
}

export function paperTrackingExitReturn(item: ShortpickPaperTrackingItem): number | null {
  const track = paperTrackingPrimaryExitTrack(item);
  if (!track && isRetrospectiveReplayPaperTrackingRow(item)) return null;
  return paperTrackingTrackReturn(track, item);
}

export function comparePaperTrackingRows(left: ShortpickPaperTrackingItem, right: ShortpickPaperTrackingItem): number {
  const leftExitPriority = hasPaperTrackingMechanical10dExit(left) ? 2 : hasPaperTrackingMechanical5dExit(left) ? 1 : 0;
  const rightExitPriority = hasPaperTrackingMechanical10dExit(right) ? 2 : hasPaperTrackingMechanical5dExit(right) ? 1 : 0;
  if (leftExitPriority !== rightExitPriority) return rightExitPriority - leftExitPriority;
  const leftExitDay = paperTrackingTrackExitDay(paperTrackingPriorityExitTrack(left), left);
  const rightExitDay = paperTrackingTrackExitDay(paperTrackingPriorityExitTrack(right), right);
  if (leftExitDay !== rightExitDay) return rightExitDay.localeCompare(leftExitDay);
  const leftSignal = paperTrackingSignalDate(left);
  const rightSignal = paperTrackingSignalDate(right);
  if (leftSignal !== rightSignal) return rightSignal.localeCompare(leftSignal);
  return paperTrackingDisplayRank(left) - paperTrackingDisplayRank(right);
}

export function comparePaperTrackingSignalEntryRows(left: ShortpickPaperTrackingItem, right: ShortpickPaperTrackingItem): number {
  const leftSignal = paperTrackingSignalDate(left);
  const rightSignal = paperTrackingSignalDate(right);
  if (leftSignal !== rightSignal) return leftSignal.localeCompare(rightSignal);
  const leftEntry = paperTrackingEntryDate(left);
  const rightEntry = paperTrackingEntryDate(right);
  if (leftEntry !== rightEntry) return leftEntry.localeCompare(rightEntry);
  return paperTrackingDisplayRank(left) - paperTrackingDisplayRank(right);
}
