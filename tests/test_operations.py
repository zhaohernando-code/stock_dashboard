from __future__ import annotations

import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo

from ashare_evidence.operations import (
    _compact_operations_portfolio_payload,
    _portfolio_payload,
    build_operations_detail,
)
from ashare_evidence.operations_projection_compaction import OPERATIONS_NAV_HISTORY_POINT_LIMIT

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


class OperationsTests(unittest.TestCase):
    def test_portfolio_payload_tolerates_benchmark_starting_after_first_trade_day(self) -> None:
        portfolio = SimpleNamespace(
            portfolio_payload={"starting_cash": 1_000.0},
            cash_balance=1_000.0,
            orders=[],
            name="测试组合",
            mode="manual",
            portfolio_key="test-portfolio",
            benchmark_symbol="000300.SH",
            status="active",
        )
        timeline_points = [
            datetime(2026, 1, 2, 15, 0, tzinfo=SHANGHAI_TZ),
            datetime(2026, 1, 5, 15, 0, tzinfo=SHANGHAI_TZ),
            datetime(2026, 1, 6, 15, 0, tzinfo=SHANGHAI_TZ),
        ]
        payload = _portfolio_payload(
            portfolio,
            active_symbols={"600519.SH"},
            stock_names={"600519.SH": "贵州茅台"},
            price_history={
                "600519.SH": [
                    (timeline_points[0], 100.0),
                    (timeline_points[1], 101.0),
                    (timeline_points[2], 102.0),
                ]
            },
            timeline_points=timeline_points,
            benchmark_close_map={
                timeline_points[1].date(): 100.0,
                timeline_points[2].date(): 110.0,
            },
            recommendation_hit_rate=0.0,
            market_data_timeframe="1d",
        )

        benchmark_nav = [point["benchmark_nav"] for point in payload["nav_history"]]
        self.assertEqual(benchmark_nav, [1000.0, 1000.0, 1100.0])

    def test_compact_operations_portfolio_samples_nav_history_with_anchors(self) -> None:
        points = [
            {
                "trade_date": f"2026-01-{index + 1:02d}",
                "nav": float(index),
                "benchmark_nav": float(index),
                "drawdown": 0.0,
                "exposure": 0.0,
            }
            for index in range(OPERATIONS_NAV_HISTORY_POINT_LIMIT + 40)
        ]
        points[37] = {**points[37], "nav": 999.0, "benchmark_nav": 999.0}
        points[73] = {**points[73], "drawdown": -0.42}
        compact = _compact_operations_portfolio_payload({
            "portfolio_key": "manual",
            "nav_history": points,
        })

        self.assertLessEqual(len(compact["nav_history"]), OPERATIONS_NAV_HISTORY_POINT_LIMIT)
        self.assertEqual(compact["nav_history"][0], points[0])
        self.assertEqual(compact["nav_history"][-1], points[-1])
        self.assertIn(points[37], compact["nav_history"])
        self.assertIn(points[73], compact["nav_history"])

    def test_non_portfolio_operation_details_do_not_build_full_dashboard(self) -> None:
        session = SimpleNamespace(get_bind=lambda: None)
        expected_keys = {
            "replay": "recommendation_replay",
            "manual_queue": "manual_research_queue",
            "factor_observation": "factor_observation_summary",
            "sector_exposure": "sector_exposure",
            "policy_governance": "policy_governance",
            "simulation_workspace": "simulation_workspace",
        }

        with (
            patch("ashare_evidence.operations.build_operations_dashboard", side_effect=AssertionError("full dashboard should not build")),
            patch("ashare_evidence.operations.active_watchlist_symbols", return_value=["002475.SZ", "600519.SH"]),
            patch("ashare_evidence.operations._operations_artifact_root", return_value="/tmp/artifacts"),
            patch("ashare_evidence.operations._build_operations_replay_detail", return_value=[{"summary": "复盘"}]),
            patch("ashare_evidence.operations._manual_research_queue_payload", return_value={"focus_symbol": "002475.SZ"}),
            patch("ashare_evidence.operations._factor_observation_summary", return_value={"status": "pass"}),
            patch("ashare_evidence.operations._sector_exposure_snapshot", return_value={"source": "test"}),
            patch("ashare_evidence.operations.build_policy_governance_summary", return_value={"status": "pass"}),
            patch("ashare_evidence.operations.build_policy_audit_report", return_value={"passed": True}),
            patch("ashare_evidence.operations._build_operations_simulation_workspace_detail", return_value={"spaces": []}),
        ):
            for section, payload_key in expected_keys.items():
                with self.subTest(section=section):
                    payload = build_operations_detail(
                        session,
                        section=section,
                        sample_symbol="002475.SZ",
                        target_login="root",
                    )

                    self.assertEqual(payload["section"], section)
                    self.assertIn("generated_at", payload)
                    self.assertIn(payload_key, payload)


if __name__ == "__main__":
    unittest.main()
