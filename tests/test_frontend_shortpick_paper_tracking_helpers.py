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
