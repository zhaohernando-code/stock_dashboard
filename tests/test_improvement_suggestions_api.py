# ruff: noqa: F403,F405
from __future__ import annotations

from tests.improvement_suggestions_test_support import *


class ImprovementSuggestionApiTests(ImprovementSuggestionTestCase):
    def test_api_permissions_and_degraded_run(self) -> None:
        os.environ["ASHARE_BETA_ACCESS_MODE"] = "allowlist"
        os.environ["ASHARE_BETA_ALLOWLIST"] = "member-token:viewer,operator-token:operator"
        os.environ["ASHARE_BETA_ACCESS_HEADER"] = "X-Ashare-Beta-Key"
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
        self._write_event_analysis()

        client = TestClient(create_app(self.database_url, enable_background_ops_tick=False))
        denied = client.get("/dashboard/improvement-suggestions/summary", headers={"X-Ashare-Beta-Key": "member-token"})
        self.assertEqual(denied.status_code, 403)

        with patch(
            "ashare_evidence.runtime_config.get_builtin_llm_executor_config",
            return_value={"enabled": False},
        ):
            run_response = client.post(
                "/dashboard/improvement-suggestions/run",
                headers={"X-Ashare-Beta-Key": "operator-token"},
            )
        self.assertEqual(run_response.status_code, 200)
        payload = run_response.json()
        self.assertEqual(payload["status"], "degraded_missing_reviewer")
        self.assertGreaterEqual(payload["summary"]["total"], 1)

        detail_response = client.get(
            "/dashboard/improvement-suggestions/details?category=research_validation",
            headers={"X-Ashare-Beta-Key": "operator-token"},
        )
        self.assertEqual(detail_response.status_code, 200)
        self.assertIn("suggestions", detail_response.json())

    def test_accept_plan_endpoint_requires_operator_and_returns_control_task(self) -> None:
        os.environ["ASHARE_BETA_ACCESS_MODE"] = "allowlist"
        os.environ["ASHARE_BETA_ALLOWLIST"] = "member-token:viewer,operator-token:operator"
        os.environ["ASHARE_BETA_ACCESS_HEADER"] = "X-Ashare-Beta-Key"
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
        self._write_event_analysis()
        reviewer = {
            "stance": "support",
            "confidence": 0.72,
            "main_reason": "建议可转成清晰开发任务。",
            "evidence_refs_used": ["event_analysis/600519.SH/20260501T090000_factor_conflict.json"],
            "missing_evidence": [],
            "implementation_notes": ["在 Operations 展示。"],
            "red_flags": [],
            "safe_to_plan": True,
            "safe_to_auto_apply": False,
        }
        with session_scope(self.database_url) as session:
            snapshot = run_improvement_suggestion_review(
                session,
                window_days=30,
                reviewer_overrides={"gpt": reviewer, "deepseek": reviewer},
            )
            first_id = snapshot["suggestions"][0]["suggestion_id"]

        client = TestClient(create_app(self.database_url, enable_background_ops_tick=False))
        denied = client.post(
            f"/dashboard/improvement-suggestions/{first_id}/accept-plan",
            json={"model": "gpt-5.4", "reason": "进入计划池"},
            headers={"X-Ashare-Beta-Key": "member-token"},
        )
        self.assertEqual(denied.status_code, 403)

        with patch(
            "ashare_evidence.improvement_suggestions.urlopen",
            return_value=_FakeResponse(json.dumps({"task": {"id": "task-plan-api", "status": "blocked"}})),
        ):
            accepted = client.post(
                f"/dashboard/improvement-suggestions/{first_id}/accept-plan",
                json={"model": "gpt-5.4", "reason": "进入计划池"},
                headers={"X-Ashare-Beta-Key": "operator-token"},
            )
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json()["control_plane_task"]["id"], "task-plan-api")
