from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


class FrontendShortpickPaperTrackingHelperTests(unittest.TestCase):
    def test_latest_simulated_trade_helpers_keep_frozen_strategy_first(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        frontend_root = repo_root / "frontend"
        tsc = frontend_root / "node_modules" / ".bin" / "tsc"
        node = shutil.which("node")
        if not tsc.exists() or not node:
            self.skipTest("frontend TypeScript runtime is not installed")

        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(
                [
                    str(tsc),
                    "--target",
                    "ES2020",
                    "--module",
                    "CommonJS",
                    "--moduleResolution",
                    "node",
                    "--jsx",
                    "react-jsx",
                    "--esModuleInterop",
                    "--skipLibCheck",
                    "--outDir",
                    tmp,
                    "frontend/src/components/shortpickLabPaperTracking.ts",
                ],
                cwd=repo_root,
                check=True,
                capture_output=True,
                text=True,
            )
            helper_path = Path(tmp) / "components" / "shortpickLabPaperTracking.js"
            script = textwrap.dedent(
                """
                const helpers = require(process.argv[1]);
                const rows = [
                  {
                    run_id: 1,
                    run_date: "2026-06-01",
                    tracking_group: "frozen_strategy",
                    signal_date: "2026-06-01",
                    entry_date: "2026-06-02",
                    source_rank: 1,
                    name: "旧冻结",
                    symbol: "000001.SZ",
                  },
                  {
                    run_id: 2,
                    run_date: "2026-06-02",
                    tracking_group: "frozen_strategy",
                    signal_date: "2026-06-02",
                    entry_date: "2026-06-03",
                    source_rank: 1,
                    name: "新冻结",
                    symbol: "600183.SH",
                  },
                  {
                    run_id: 2,
                    run_date: "2026-06-02",
                    tracking_group: "frozen_strategy_v2",
                    signal_date: "2026-06-02",
                    entry_date: "2026-06-03",
                    entry_rule: "次一交易日开盘买入",
                    source_rank: 1,
                    name: "新冻结开盘",
                    symbol: "600183.SH",
                  },
                  {
                    run_id: 3,
                    run_date: "2026-06-03",
                    tracking_group: "llm_paper_control",
                    signal_date: "2026-06-03",
                    entry_date: "2026-06-04",
                    source_rank: 1,
                    name: "今日LLM",
                    symbol: "002896.SZ",
                  },
                ];
                const sameDateRows = [
                  "market_random_control",
                  "market_factor_control",
                  "llm_paper_control",
                  "frozen_strategy_v2",
                  "frozen_strategy",
                ].map((tracking_group, index) => ({
                  run_id: 9,
                  run_date: "2026-06-03",
                  tracking_group,
                  signal_date: "2026-06-03",
                  entry_date: "2026-06-04",
                  source_rank: 1,
                  name: `排序${index}`,
                  symbol: `00000${index}.SZ`,
                }));
                const frozen = helpers.latestFrozenPaperTrackingChoices(rows);
                const latestRunChoices = helpers.latestPaperTrackingChoices(rows, { id: 3, run_date: "2026-06-03" });
                const ranked = helpers.latestPaperTrackingChoices(sameDateRows, { id: 9, run_date: "2026-06-03" });
                const governanceRows = [
                  { candidate_id: 1, governance_view_section: "primary", governance_status: "active", name: "主表", symbol: "000001.SZ" },
                  { candidate_id: 2, governance_view_section: "deprecated", governance_status: "retire_candidate", name: "归档", symbol: "000002.SZ" },
                  { candidate_id: 3, governance_status: "observe", name: "旧字段", symbol: "000003.SZ" },
                  { candidate_id: 4, governance_status: "retired", name: "仅状态归档", symbol: "000004.SZ" },
                  { candidate_id: 5, governance_status: "inventory_archived", name: "库存归档", symbol: "000005.SZ" },
                ];
                const latestRows = [
                  {
                    run_id: 20,
                    run_date: "2026-06-20",
                    tracking_group: "frozen_strategy",
                    signal_date: "2026-06-20",
                    governance_status: "retire_candidate",
                    name: "不应显示",
                    symbol: "300001.SZ",
                  },
                  {
                    run_id: 19,
                    run_date: "2026-06-19",
                    tracking_group: "frozen_strategy",
                    signal_date: "2026-06-19",
                    governance_status: "active",
                    name: "仍可显示",
                    symbol: "300002.SZ",
                  },
                ];
                const currentRoundRows = [
                  {
                    run_id: 30,
                    run_date: "2026-06-30",
                    tracking_group: "frozen_strategy",
                    tracking_role: "frozen_paper_primary",
                    signal_date: "2026-06-30",
                    source_rank: 1,
                    name: "冻结",
                    symbol: "600001.SH",
                  },
                  {
                    run_id: 30,
                    run_date: "2026-06-30",
                    tracking_group: "market_factor_control",
                    tracking_role: "market_factor_control_offensive_top1",
                    selection_label: "动量换手第1名",
                    signal_date: "2026-06-30",
                    source_rank: 1,
                    name: "旧动量",
                    symbol: "600002.SH",
                  },
                  {
                    run_id: 30,
                    run_date: "2026-06-30",
                    tracking_group: "market_factor_control",
                    tracking_role: "market_factor_control_top3_equal_weight",
                    selection_label: "前三名等权组合",
                    signal_date: "2026-06-30",
                    source_rank: 2,
                    name: "旧Top3",
                    symbol: "600003.SH",
                  },
                  {
                    run_id: 30,
                    run_date: "2026-06-30",
                    tracking_group: "market_factor_control",
                    tracking_role: "market_factor_control_same_symbol_cooldown_low_turnover_uptrend",
                    selection_label: "同股亏损冷却版",
                    signal_date: "2026-06-30",
                    source_rank: 1,
                    name: "冷却",
                    symbol: "600004.SH",
                  },
                  {
                    run_id: 30,
                    run_date: "2026-06-30",
                    tracking_group: "market_factor_control",
                    tracking_role: "market_factor_control_drawdown_reversal_low_turnover_uptrend",
                    selection_label: "回撤反转过滤版",
                    signal_date: "2026-06-30",
                    source_rank: 2,
                    name: "回撤",
                    symbol: "600007.SH",
                  },
                  {
                    run_id: 30,
                    run_date: "2026-06-30",
                    tracking_group: "market_factor_control",
                    tracking_role: "market_factor_control_repeated_exposure_low_turnover_uptrend",
                    selection_label: "重复暴露限制版",
                    signal_date: "2026-06-30",
                    source_rank: 3,
                    name: "重复",
                    symbol: "600008.SH",
                  },
                  {
                    run_id: 30,
                    run_date: "2026-06-30",
                    tracking_group: "market_factor_control",
                    tracking_role: "market_factor_control_cooldown_top1",
                    control_label: "同股冷却过滤",
                    signal_date: "2026-06-30",
                    source_rank: 1,
                    name: "旧冷却误标",
                    symbol: "600006.SH",
                  },
                  {
                    run_id: 30,
                    run_date: "2026-06-30",
                    tracking_group: "market_random_control",
                    tracking_role: "market_factor_control_random_pool",
                    selection_label: "同池随机基线",
                    signal_date: "2026-06-30",
                    source_rank: 13,
                    name: "随机",
                    symbol: "600005.SH",
                  },
                ];
                const replayRow = {
                  tracking_group: "market_factor_control",
                  control_label: "同股冷却过滤",
                  selection_label: "后验前向回放：同股冷却过滤",
                  name: "回放",
                  symbol: "600183.SH",
                };
                const activeSameSymbolCooldownRow = {
                  tracking_group: "market_factor_control",
                  tracking_role: "market_factor_control_same_symbol_cooldown_low_turnover_uptrend",
                  selection_label: "同股亏损冷却版",
                  name: "真前向冷却",
                  symbol: "600183.SH",
                };
                const legacyCooldownTop1Row = {
                  tracking_group: "market_factor_control",
                  tracking_role: "market_factor_control_cooldown_top1",
                  control_label: "同股冷却过滤",
                  name: "旧降追高",
                  symbol: "600183.SH",
                };
                const immatureReplayRow = {
                  tracking_group: "market_factor_control",
                  control_label: "同股冷却过滤",
                  evidence_basis: "retrospective_forward_replay",
                  retrospective: true,
                  validation_status: "completed",
                  validation_horizon_days: 3,
                  exit_at: "2026-06-10T08:00:00Z",
                  stock_return: 0.069,
                  paper_tracking_exit_tracks: [],
                  name: "未成熟回放",
                  symbol: "600183.SH",
                };
                const ordinaryCompletedRow = {
                  tracking_group: "frozen_strategy",
                  validation_status: "completed",
                  validation_horizon_days: 3,
                  exit_at: "2026-06-10T08:00:00Z",
                  stock_return: 0.069,
                  paper_tracking_exit_tracks: [],
                  name: "普通完成行",
                  symbol: "600183.SH",
                };
                const effectRows = [
                  {
                    candidate_id: 101,
                    tracking_group: "market_factor_control",
                    control_label: "同股冷却过滤",
                    evidence_basis: "retrospective_forward_replay",
                    retrospective: true,
                    signal_date: "2026-06-01",
                    name: "回放A",
                    symbol: "600183.SH",
                    paper_tracking_exit_tracks: [
                      { key: "mechanical_3d", label: "机械3日", exit_trade_day: "2026-06-04", stock_return: 0.12 },
                      { key: "mechanical_5d", label: "机械5日", exit_trade_day: "2026-06-08", stock_return: 0.05 },
                      { key: "mechanical_10d", label: "机械10日", exit_trade_day: "2026-06-15", stock_return: 0.08 },
                      { key: "take_profit_stop_loss", label: "止盈止损", exit_trade_day: "2026-06-09", stock_return: 0.10 },
                    ],
                  },
                  {
                    candidate_id: 102,
                    tracking_group: "frozen_strategy",
                    signal_date: "2026-06-02",
                    name: "冻结B",
                    symbol: "600184.SH",
                    paper_tracking_exit_tracks: [
                      { key: "mechanical_5d", label: "机械5日", exit_trade_day: "2026-06-09", stock_return: -0.03 },
                    ],
                  },
                ];
                const effectObservations = helpers.paperTrackingEffectObservations(effectRows);
                const effectSummaries = helpers.paperTrackingEffectSummaries(effectRows);
                console.log(JSON.stringify({
                  frozenGroups: frozen.map((item) => item.tracking_group),
                  frozenNames: frozen.map((item) => item.name),
                  frozenSignalDates: frozen.map((item) => item.signal_date),
                  latestRunChoiceGroups: latestRunChoices.map((item) => item.tracking_group),
                  latestRunChoiceSignalDates: latestRunChoices.map((item) => item.signal_date),
                  rankedGroups: ranked.map((item) => item.tracking_group),
                  primaryIds: helpers.primaryPaperTrackingRows(governanceRows).map((item) => item.candidate_id),
                  deprecatedIds: helpers.deprecatedPaperTrackingRows(governanceRows).map((item) => item.candidate_id),
                  latestVisibleNames: helpers.latestPaperTrackingChoices(latestRows, { id: 20, run_date: "2026-06-20" }).map((item) => item.name),
                  frozenVisibleNames: helpers.latestFrozenPaperTrackingChoices(latestRows).map((item) => item.name),
                  allArchivedChoices: helpers.latestPaperTrackingChoices([{ ...latestRows[0], governance_status: "inventory_archived" }], { id: 20, run_date: "2026-06-20" }).length,
                  currentRoundNames: helpers.latestCurrentPaperTrackingRoundRows(currentRoundRows, { id: 30, run_date: "2026-06-30" }).map((item) => item.name),
                  currentRoundLabels: helpers.latestCurrentPaperTrackingRoundRows(currentRoundRows, { id: 30, run_date: "2026-06-30" }).map((item) => helpers.paperTrackingRecordGroupLabel(item)),
                  replayRecordGroupLabel: helpers.paperTrackingRecordGroupLabel(replayRow),
                  replayGroupFilterMatches: helpers.paperTrackingGroupFilterMatches(replayRow, "同股冷却过滤"),
                  activeSameSymbolRecordGroupLabel: helpers.paperTrackingRecordGroupLabel(activeSameSymbolCooldownRow),
                  activeSameSymbolGroupFilterMatches: helpers.paperTrackingGroupFilterMatches(activeSameSymbolCooldownRow, "同股冷却过滤"),
                  legacyCooldownTop1RecordGroupLabel: helpers.paperTrackingRecordGroupLabel(legacyCooldownTop1Row),
                  legacyCooldownTop1GroupFilterMatches: helpers.paperTrackingGroupFilterMatches(legacyCooldownTop1Row, "同股冷却过滤"),
                  immatureReplayExitText: helpers.paperTrackingExitText(immatureReplayRow),
                  immatureReplayExitReturn: helpers.paperTrackingExitReturn(immatureReplayRow),
                  ordinaryCompletedExitText: helpers.paperTrackingExitText(ordinaryCompletedRow),
                  ordinaryCompletedExitReturn: helpers.paperTrackingExitReturn(ordinaryCompletedRow),
                  effectObservationKeys: effectObservations.map((item) => item.exitTrackKey).sort(),
                  effectObservationFilters: effectObservations.map((item) => item.groupFilter).sort(),
                  effectSummaryLabels: effectSummaries.map((item) => `${item.strategyLabel}:${item.exitTrackLabel}:${item.count}`).sort(),
                  effectExitStateFilter: helpers.paperTrackingEffectExitStateFilter("take_profit_stop_loss"),
                }));
                """
            )
            result = subprocess.run(
                [node, "-e", script, str(helper_path)],
                cwd=repo_root,
                check=True,
                capture_output=True,
                text=True,
            )

        payload = json.loads(result.stdout)
        self.assertEqual(payload["frozenGroups"], ["frozen_strategy", "frozen_strategy_v2"])
        self.assertEqual(payload["frozenNames"], ["新冻结", "新冻结开盘"])
        self.assertEqual(payload["frozenSignalDates"], ["2026-06-02", "2026-06-02"])
        self.assertEqual(payload["latestRunChoiceGroups"], ["llm_paper_control"])
        self.assertEqual(payload["latestRunChoiceSignalDates"], ["2026-06-03"])
        self.assertEqual(
            payload["rankedGroups"],
            [
                "frozen_strategy",
                "frozen_strategy_v2",
                "llm_paper_control",
                "market_factor_control",
                "market_random_control",
            ],
        )
        self.assertEqual(payload["primaryIds"], [1, 3])
        self.assertEqual(payload["deprecatedIds"], [2, 4, 5])
        self.assertEqual(payload["latestVisibleNames"], ["仍可显示"])
        self.assertEqual(payload["frozenVisibleNames"], ["仍可显示"])
        self.assertEqual(payload["allArchivedChoices"], 0)
        self.assertEqual(payload["currentRoundNames"], ["冻结", "冷却", "回撤", "重复", "随机"])
        self.assertEqual(
            payload["currentRoundLabels"],
            ["冻结策略", "同股冷却过滤", "回撤/反转过滤", "重复暴露限制", "同池随机基线"],
        )
        self.assertEqual(payload["replayRecordGroupLabel"], "同股冷却过滤")
        self.assertTrue(payload["replayGroupFilterMatches"])
        self.assertEqual(payload["activeSameSymbolRecordGroupLabel"], "同股冷却过滤")
        self.assertTrue(payload["activeSameSymbolGroupFilterMatches"])
        self.assertEqual(payload["legacyCooldownTop1RecordGroupLabel"], "市场因子对照")
        self.assertFalse(payload["legacyCooldownTop1GroupFilterMatches"])
        self.assertEqual(payload["immatureReplayExitText"], "等待窗口")
        self.assertIsNone(payload["immatureReplayExitReturn"])
        self.assertEqual(payload["ordinaryCompletedExitText"], "3日 06/10 16:00")
        self.assertEqual(payload["ordinaryCompletedExitReturn"], 0.069)
        self.assertEqual(
            payload["effectObservationKeys"],
            ["mechanical_10d", "mechanical_5d", "mechanical_5d", "take_profit_stop_loss"],
        )
        self.assertEqual(
            payload["effectObservationFilters"],
            ["frozen_strategy", "同股冷却过滤", "同股冷却过滤", "同股冷却过滤"],
        )
        self.assertIn("同股冷却过滤:止盈止损:1", payload["effectSummaryLabels"])
        self.assertEqual(payload["effectExitStateFilter"], "take_profit_stop_loss_done")
