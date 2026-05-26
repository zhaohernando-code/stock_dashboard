# ruff: noqa: F403,F405
from __future__ import annotations

from tests.improvement_suggestions_test_support import *


class ImprovementSuggestionTests(ImprovementSuggestionTestCase):
    def test_collects_event_and_validation_suggestions_with_dedupe(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
        self._write_event_analysis()
        self._write_event_analysis(suggestion="首页风险展示应优先解释 RankIC 冲突。")

        with session_scope(self.database_url) as session:
            suggestions = collect_improvement_suggestions(session, window_days=30)

        claims = [item["claim"] for item in suggestions]
        self.assertTrue(any("首页风险展示" in claim for claim in claims))
        ids = [item["suggestion_id"] for item in suggestions]
        self.assertEqual(len(ids), len(set(ids)))

    def test_data_quality_suggestions_are_grouped_by_degraded_sources(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session, symbols=("600519.SH", "300750.SZ"))
            session.execute(delete(FeatureSnapshot))
            for stock in session.scalars(select(Stock).where(Stock.symbol.in_(("600519.SH", "300750.SZ")))):
                stock.listed_date = None
                stock.provider_symbol = ""
                stock.profile_payload = {
                    key: value
                    for key, value in stock.profile_payload.items()
                    if key not in {"financial_snapshot", "board", "market_board", "board_name"}
                }
            session.commit()

        with session_scope(self.database_url) as session:
            suggestions = collect_improvement_suggestions(session, window_days=30)

        data_quality_items = [item for item in suggestions if item["source_type"] == "data_quality"]
        self.assertEqual(len(data_quality_items), 1)
        grouped = data_quality_items[0]
        self.assertIsNone(grouped["symbol"])
        self.assertTrue(grouped["source_ref"].startswith("data_quality/group/"))
        self.assertIn("2 只股票数据质量为 warn", grouped["claim"])
        self.assertIn("共同降级来源：financial_data_stale, profile_incomplete", grouped["claim"])
        self.assertIn("重新运行数据质量与改进建议审计", grouped["proposed_change"])
        self.assertEqual(grouped["raw_source"]["aggregation"], "degraded_source_group")
        self.assertEqual(grouped["raw_source"]["symbol_count"], 2)
        self.assertEqual(grouped["raw_source"]["symbols"], ["300750.SZ", "600519.SH"])
        self.assertEqual(
            sorted(grouped["evidence_refs"]),
            ["data_quality/300750.SZ", "data_quality/600519.SH"],
        )

    def test_legacy_data_quality_snapshot_is_grouped_on_read(self) -> None:
        root = artifact_root_from_database_url(self.database_url)
        suggestions = [
            {
                "suggestion_id": "suggestion:old-a",
                "source_type": "data_quality",
                "source_ref": "data_quality/600519.SH/latest",
                "symbol": "600519.SH",
                "category": "data_quality",
                "claim": "600519.SH 数据质量为 warn，降级来源：financial_data_stale, profile_incomplete。",
                "proposed_change": "优先补齐或突出该股票的数据覆盖缺口。",
                "evidence_refs": ["data_quality/600519.SH"],
                "status": "reviewed",
                "created_at": "2026-05-01T04:00:00+00:00",
                "raw_source": {
                    "symbol": "600519.SH",
                    "status": "warn",
                    "degraded_sources": ["financial_data_stale", "profile_incomplete"],
                },
                "final_confidence": "moderate",
                "reviews": {"gpt": {"status": "completed"}},
            },
            {
                "suggestion_id": "suggestion:old-b",
                "source_type": "data_quality",
                "source_ref": "data_quality/300750.SZ/latest",
                "symbol": "300750.SZ",
                "category": "data_quality",
                "claim": "300750.SZ 数据质量为 warn，降级来源：profile_incomplete, financial_data_stale。",
                "proposed_change": "优先补齐或突出该股票的数据覆盖缺口。",
                "evidence_refs": ["data_quality/300750.SZ"],
                "status": "reviewed",
                "created_at": "2026-05-01T04:01:00+00:00",
                "raw_source": {
                    "symbol": "300750.SZ",
                    "status": "warn",
                    "degraded_sources": ["profile_incomplete", "financial_data_stale"],
                },
                "final_confidence": "low",
                "reviews": {"gpt": {"status": "completed"}},
            },
        ]
        snapshot = {
            "artifact_type": "suggestion_review_snapshot",
            "generated_at": "2026-05-01T04:02:00+00:00",
            "status": "ok",
            "window_days": 7,
            "model_status": {"gpt": "ok", "deepseek": "ok", "overall": "ok"},
            "summary": _snapshot_counts(suggestions),
            "suggestions": suggestions,
        }
        _write_snapshot(root, snapshot)

        with session_scope(self.database_url) as session:
            payload = suggestion_details(session, category="data_quality")

        self.assertEqual(payload["summary"]["total"], 1)
        self.assertEqual(len(payload["suggestions"]), 1)
        grouped = payload["suggestions"][0]
        self.assertIsNone(grouped["symbol"])
        self.assertTrue(grouped["source_ref"].startswith("data_quality/group/"))
        self.assertIn("2 只股票数据质量为 warn", grouped["claim"])
        self.assertIn("共同降级来源：financial_data_stale, profile_incomplete", grouped["claim"])
        self.assertEqual(grouped["raw_source"]["symbols"], ["300750.SZ", "600519.SH"])
        self.assertEqual(
            sorted(grouped["evidence_refs"]),
            ["data_quality/300750.SZ", "data_quality/600519.SH"],
        )

    def test_suggestion_details_refreshes_control_plane_task_status(self) -> None:
        root = artifact_root_from_database_url(self.database_url)
        suggestions = [
            {
                "suggestion_id": "suggestion:control-task",
                "source_type": "launch_gate",
                "source_ref": "launch_gate/建议命中复盘覆盖",
                "symbol": None,
                "category": "operations_workflow",
                "claim": "运营门禁 建议命中复盘覆盖 当前为 warn，需要形成改进计划。",
                "proposed_change": "真实 benchmark 与正式复盘口径完成重建后，才允许恢复该门槛。",
                "evidence_refs": ["launch_gate/建议命中复盘覆盖"],
                "status": "completed",
                "created_at": "2026-05-01T04:00:00+00:00",
                "final_confidence": "moderate",
                "control_plane_task": {
                    "id": "task-live-status",
                    "title": "旧任务标题",
                    "status": "blocked",
                    "model": "gpt-5.5",
                    "project_id": "ashare-dashboard",
                    "plan_mode": True,
                    "api_base": "http://control.test",
                },
            }
        ]
        _write_snapshot(
            root,
            {
                "artifact_type": "suggestion_review_snapshot",
                "generated_at": "2026-05-01T04:02:00+00:00",
                "status": "ok",
                "window_days": 7,
                "model_status": {"gpt": "ok", "deepseek": "ok", "overall": "ok"},
                "summary": _snapshot_counts(suggestions),
                "suggestions": suggestions,
            },
        )

        def fake_urlopen(target, *, timeout: int, disable_proxies: bool = False):
            self.assertEqual(str(target), "http://control.test/api/tasks/task-live-status")
            self.assertEqual(timeout, 2)
            self.assertTrue(disable_proxies)
            return _FakeResponse(
                json.dumps(
                    {
                        "task": {
                            "id": "task-live-status",
                            "status": "succeeded",
                            "rawStatus": "succeeded",
                            "publishStatus": "published",
                            "publishVerified": True,
                            "workflowGates": {"status": "satisfied", "missingEvidence": []},
                            "updatedAt": "2026-05-04T12:00:00.000Z",
                        }
                    }
                )
            )

        with session_scope(self.database_url) as session:
            with patch("ashare_evidence.improvement_suggestions.urlopen", side_effect=fake_urlopen):
                payload = suggestion_details(session, status="completed")

        task = payload["suggestions"][0]["control_plane_task"]
        self.assertEqual(task["status"], "succeeded")
        self.assertEqual(task["publish_status"], "published")
        self.assertTrue(task["publish_verified"])
        self.assertEqual(task["workflow_gates"]["status"], "satisfied")
        self.assertEqual(task["status_source"], "control_plane")
        self.assertFalse(task["status_stale"])
