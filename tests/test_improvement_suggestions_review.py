# ruff: noqa: F403,F405
from __future__ import annotations

from tests.improvement_suggestions_test_support import *


class ImprovementSuggestionReviewTests(ImprovementSuggestionTestCase):
    def test_review_summary_caps_missing_evidence_and_experiment_actions(self) -> None:
        suggestion = {
            "suggestion_id": "suggestion:test",
            "category": "factor_weight_experiment",
            "claim": "权重需要调整。",
            "proposed_change": "新增权重实验。",
            "evidence_refs": ["validation-metrics:test"],
        }
        reviews = {
            "gpt": {
                "status": "completed",
                "stance": "support",
                "confidence": 0.9,
                "missing_evidence": [],
            },
            "deepseek": {
                "status": "completed",
                "stance": "support",
                "confidence": 0.9,
                "missing_evidence": [],
            },
        }

        result = summarize_suggestion_review(suggestion, reviews)

        self.assertEqual(result["final_confidence"], "high")
        self.assertEqual(result["recommended_action"], "create_experiment")

        reviews["deepseek"]["missing_evidence"] = ["样本外验证"]
        capped = summarize_suggestion_review(suggestion, reviews)
        self.assertEqual(capped["final_confidence"], "moderate")

    def test_non_json_reviewer_output_is_recorded_as_failed(self) -> None:
        parsed = parse_reviewer_json("这不是 JSON", reviewer="gpt")

        self.assertEqual(parsed["status"], "review_failed")
        self.assertEqual(parsed["stance"], "insufficient_evidence")
        self.assertFalse(parsed["safe_to_plan"])

    def test_deepseek_key_uses_openai_compatible_transport_by_default(self) -> None:
        deepseek_key = ModelApiKey(
            name="deepseek",
            provider_name="deepseek",
            model_name="deepseek-v4-pro",
            base_url="https://api.deepseek.com",
            api_key="secret",
            metadata_payload={},
        )
        anthropic_path_key = ModelApiKey(
            name="deepseek-anthropic",
            provider_name="deepseek",
            model_name="deepseek-v4-pro",
            base_url="https://api.deepseek.com/anthropic",
            api_key="secret",
            metadata_payload={},
        )

        self.assertIsInstance(_transport_for_model_key(deepseek_key), OpenAICompatibleTransport)
        self.assertIsInstance(_transport_for_model_key(anthropic_path_key), AnthropicCompatibleTransport)

    def test_gpt_reviewer_falls_back_to_builtin_codex_when_key_missing(self) -> None:
        suggestion = {
            "suggestion_id": "suggestion:test",
            "category": "operations_workflow",
            "claim": "需要优化 Operations 首屏。",
            "proposed_change": "新增轻量 summary。",
            "evidence_refs": ["launch_gate/test"],
        }
        builtin = {
            "enabled": True,
            "transport_kind": "codex_cli",
            "codex_bin": "/usr/local/bin/codex",
            "model_name": "gpt-5.5",
            "base_url": "codex-cli://local",
            "api_key": "",
        }
        answer = json.dumps(
            {
                "reviewer": "gpt",
                "stance": "support",
                "confidence": 0.7,
                "main_reason": "可转成明确任务。",
                "evidence_refs_used": ["launch_gate/test"],
                "missing_evidence": [],
                "implementation_notes": ["加 summary endpoint"],
                "red_flags": [],
                "safe_to_plan": True,
                "safe_to_auto_apply": False,
            }
        )

        with session_scope(self.database_url) as session:
            with patch("ashare_evidence.runtime_config.get_builtin_llm_executor_config", return_value=builtin), patch(
                "ashare_evidence.manual_research_workflow._run_builtin_codex_completion",
                return_value=answer,
            ) as codex:
                result = _run_reviewer(session, suggestion, "gpt")

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["transport_source"], "builtin_codex_gpt")
        codex.assert_called_once()

    def test_runner_writes_snapshot_and_status_update_requires_reason(self) -> None:
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
            with self.assertRaises(ValueError):
                update_suggestion_status(session, suggestion_id=first_id, status="monitoring", reason="")
            updated = update_suggestion_status(session, suggestion_id=first_id, status="monitoring", reason="观察一周")

        self.assertEqual(snapshot["status"], "ok")
        self.assertEqual(updated["status"], "monitoring")
        self.assertEqual(updated["status_history"][-1]["reason"], "观察一周")

    def test_accept_suggestion_for_plan_creates_control_plane_plan_task(self) -> None:
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
        captured: dict[str, object] = {}

        def fake_urlopen(target, *, timeout: int, disable_proxies: bool = False):
            captured["url"] = target.full_url
            captured["timeout"] = timeout
            captured["disable_proxies"] = disable_proxies
            captured["payload"] = json.loads(target.data.decode("utf-8"))
            return _FakeResponse(
                json.dumps(
                    {
                        "task": {
                            "id": "task-plan-1",
                            "title": "[股票看板计划池] 首页风险展示应优先解释 RankIC 冲突。",
                            "status": "blocked",
                        }
                    }
                )
            )

        with session_scope(self.database_url) as session:
            snapshot = run_improvement_suggestion_review(
                session,
                window_days=30,
                reviewer_overrides={"gpt": reviewer, "deepseek": reviewer},
            )
            first_id = snapshot["suggestions"][0]["suggestion_id"]
            with patch("ashare_evidence.improvement_suggestions.urlopen", side_effect=fake_urlopen):
                accepted = accept_suggestion_for_plan(
                    session,
                    suggestion_id=first_id,
                    model="gpt-5.5",
                    reason="进入计划池",
                    api_base="http://control.test",
                )

        payload = captured["payload"]
        self.assertEqual(captured["url"], "http://control.test/api/tasks")
        self.assertEqual(payload["projectId"], "ashare-dashboard")
        self.assertEqual(payload["model"], "gpt-5.5")
        self.assertNotIn("provider", payload)
        self.assertTrue(payload["planMode"])
        self.assertTrue(payload["approvalRequired"])
        self.assertIn("计划只面向业务结果、风险边界、验收方式", payload["description"])
        self.assertIn("文件、字段、接口、测试命令等实现细节由 AI 自行判断", payload["description"])
        self.assertIn("不要求用户选择代码路径、数据字段、测试文件或实现方案", payload["description"])
        self.assertEqual(accepted["status"], "accepted_for_plan")
        self.assertEqual(accepted["control_plane_task"]["id"], "task-plan-1")
        self.assertEqual(accepted["status_history"][-1]["model"], "gpt-5.5")
