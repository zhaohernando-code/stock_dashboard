import type { ShortpickPaperTrackingItem } from "../types";

export type PaperTrackingSpecialStrategyFilter = "同股冷却过滤" | "回撤/反转过滤" | "重复暴露限制";

const SPECIAL_STRATEGY_ROLES: Record<string, PaperTrackingSpecialStrategyFilter> = {
  market_factor_control_same_symbol_cooldown_low_turnover_uptrend: "同股冷却过滤",
  market_factor_control_drawdown_reversal_low_turnover_uptrend: "回撤/反转过滤",
  market_factor_control_repeated_exposure_low_turnover_uptrend: "重复暴露限制",
};

const SPECIAL_STRATEGY_LABELS: Record<string, PaperTrackingSpecialStrategyFilter> = {
  "同股冷却过滤": "同股冷却过滤",
  "同股亏损冷却版": "同股冷却过滤",
  "回撤/反转过滤": "回撤/反转过滤",
  "回撤反转过滤版": "回撤/反转过滤",
  "重复暴露限制": "重复暴露限制",
  "重复暴露限制版": "重复暴露限制",
};

const LEGACY_CONTROL_ROLES = new Set([
  "market_factor_control_cooldown_top1",
  "market_factor_control_offensive_top1",
  "market_factor_control_top3_equal_weight",
  "market_factor_control_no_limit_chase_low_turnover_uptrend",
]);

export function paperTrackingSpecialStrategyFilter(item: ShortpickPaperTrackingItem): PaperTrackingSpecialStrategyFilter | "" {
  const role = item.tracking_role ?? "";
  if (SPECIAL_STRATEGY_ROLES[role]) return SPECIAL_STRATEGY_ROLES[role];
  if (LEGACY_CONTROL_ROLES.has(role)) return "";
  const label = item.control_label || item.selection_label?.replace(/^后验前向回放：/, "");
  return label ? SPECIAL_STRATEGY_LABELS[label] ?? "" : "";
}
