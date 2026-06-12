# ruff: noqa: F403,F405
from __future__ import annotations

from tests.dashboard_views_test_support import *


class DashboardFrontendAndWatchlistTests(DashboardViewTestCase):
    def test_frontend_stock_page_exposes_event_deep_analysis(self) -> None:
        frontend_root = Path(__file__).resolve().parents[1] / "frontend" / "src"
        app_source = (frontend_root / "App.tsx").read_text(encoding="utf-8")
        mobile_source = (frontend_root / "components" / "mobile" / "MobileStockDetail.tsx").read_text(encoding="utf-8")
        type_source = (frontend_root / "types" / "stock.ts").read_text(encoding="utf-8")
        label_source = (frontend_root / "utils" / "labels.ts").read_text(encoding="utf-8")

        self.assertIn('title="事件深度分析"', app_source)
        self.assertIn("dashboard.event_analyses", app_source)
        self.assertIn("eventEvidenceText(item.key_evidence[0])", mobile_source)
        self.assertIn("export interface EventAnalysisView", type_source)
        self.assertIn("event_analyses: EventAnalysisView[];", type_source)
        self.assertIn('if (trigger === "weekly_review") return "周度例行复盘";', label_source)
        self.assertIn('if (direction === "disagree") return "独立判断不一致";', label_source)

    def test_frontend_promotes_validation_conflict_before_generic_risk(self) -> None:
        frontend_root = Path(__file__).resolve().parents[1] / "frontend" / "src"
        app_source = (frontend_root / "App.tsx").read_text(encoding="utf-8")
        compact_source = (frontend_root / "components" / "CompactAnalysisReport.tsx").read_text(encoding="utf-8")
        mobile_source = (frontend_root / "components" / "mobile" / "MobileStockDetail.tsx").read_text(encoding="utf-8")
        type_source = (frontend_root / "types" / "stock.ts").read_text(encoding="utf-8")

        self.assertIn("validation_conflict?: string | null;", type_source)
        self.assertIn('message="验证冲突"', app_source)
        self.assertIn("dashboard.follow_up.research_packet.validation_conflict", app_source)
        self.assertIn("const validationConflict", compact_source)
        self.assertLess(compact_source.index("validationConflict"), compact_source.index("dashboard?.recommendation.risk.invalidators[0]"))
        self.assertIn("...(validationConflict ? [validationConflict] : [])", mobile_source)

    def test_frontend_operations_exposes_improvement_suggestion_audit_without_auto_apply(self) -> None:
        frontend_root = Path(__file__).resolve().parents[1] / "frontend" / "src"
        app_source = (frontend_root / "App.tsx").read_text(encoding="utf-8")
        operations_source = (frontend_root / "components" / "OperationsTabs.tsx").read_text(encoding="utf-8")
        api_source = (frontend_root / "api" / "dashboard.ts").read_text(encoding="utf-8")
        type_source = (frontend_root / "types" / "operations.ts").read_text(encoding="utf-8")

        self.assertIn("改进建议审计台", operations_source)
        self.assertIn("GPT", operations_source)
        self.assertIn("DeepSeek", operations_source)
        self.assertIn("进入计划池", operations_source)
        self.assertIn("选择执行模型", operations_source)
        self.assertIn("GPT-5.5 高级审计 / 仲裁", operations_source)
        self.assertIn("进入计划池并创建中台任务", operations_source)
        self.assertIn("Plan 模式", operations_source)
        self.assertIn("中台任务", operations_source)
        self.assertIn("标记观察", operations_source)
        self.assertIn("重新审计", operations_source)
        self.assertIn("improvementSuggestionReviewNotice", operations_source)
        self.assertIn("improvementSuggestionReviewRunning", operations_source)
        self.assertIn('message={improvementSuggestionReviewNotice.message}', operations_source)
        self.assertIn("正在重新审计", app_source)
        self.assertIn("系统正在调用双模型重新审计改进建议", app_source)
        self.assertIn("重新审计完成", app_source)
        self.assertIn("longRunningRequestBehavior", api_source)
        self.assertIn("suggestion-stat-button", operations_source)
        self.assertIn("filterImprovementSuggestions", operations_source)
        self.assertIn("当前筛选", operations_source)
        self.assertIn("暂无可审计建议", operations_source)
        self.assertNotIn("自动实现", operations_source)
        self.assertNotIn("自动发布", operations_source)
        self.assertIn("getImprovementSuggestionDetails", api_source)
        self.assertIn("runImprovementSuggestionReview", api_source)
        self.assertIn("acceptImprovementSuggestionForPlan", api_source)
        self.assertIn("export interface ImprovementSuggestionView", type_source)
        self.assertIn("ImprovementSuggestionControlTask", type_source)

    def test_frontend_manual_research_default_submit_executes_builtin_codex(self) -> None:
        frontend_root = Path(__file__).resolve().parents[1] / "frontend" / "src"
        app_source = (frontend_root / "App.tsx").read_text(encoding="utf-8")
        api_core_source = (frontend_root / "api" / "core.ts").read_text(encoding="utf-8")
        api_manual_research_source = (frontend_root / "api" / "manual-research.ts").read_text(encoding="utf-8")
        submit_section = app_source.split("async function handleSubmitManualResearch()", 1)[1]
        submit_body = submit_section.split("async function handleExecuteManualResearch", 1)[0]

        self.assertIn("const created = await api.createManualResearchRequest({", submit_body)
        self.assertIn("const result = await api.executeManualResearchRequest(created.id, {", submit_body)
        self.assertNotIn("? await api.executeManualResearchRequest", submit_body)
        self.assertIn("const longRunningRequestTimeoutMs = 180000;", api_core_source)
        self.assertIn("const longRunningRequestAttemptTimeoutMs = 60000;", api_core_source)
        self.assertIn("export const longRunningRequestBehavior: RequestBehavior = {", api_core_source)
        self.assertIn("export const manualResearchRequestBehavior: RequestBehavior = longRunningRequestBehavior;", api_core_source)
        self.assertIn("timeoutMs: longRunningRequestTimeoutMs,", api_core_source)
        self.assertIn("attemptTimeoutMs: longRunningRequestAttemptTimeoutMs,", api_core_source)
        self.assertIn("}, manualResearchRequestBehavior);", api_manual_research_source)
        self.assertIn('placeholder="可选：选择要执行的模型 Key；留空使用本机默认模型"', app_source)
        self.assertIn('{analysisKeyId ? "提交并执行" : "使用默认模型执行"}', app_source)
        self.assertIn(
            "选择模型 Key 后会立即执行外部模型研究；不选择时使用本机默认模型。若模型暂不可用，请求会保留在人工研究记录中。",
            app_source,
        )
        self.assertIn('executor_kind: analysisKeyId ? "configured_api_key" : "builtin_gpt"', app_source)

    def test_frontend_base_entrypoint_checks_for_new_release_without_cache_buster(self) -> None:
        frontend_root = Path(__file__).resolve().parents[1] / "frontend"
        index_source = (frontend_root / "index.html").read_text(encoding="utf-8")
        main_source = (frontend_root / "src" / "main.tsx").read_text(encoding="utf-8")

        self.assertIn('<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate" />', index_source)
        self.assertIn('<meta http-equiv="Pragma" content="no-cache" />', index_source)
        self.assertIn('<meta http-equiv="Expires" content="0" />', index_source)
        self.assertIn('const releaseReloadMarkerKey = "ashare-dashboard-release-reload";', main_source)
        self.assertIn('const releaseCheckIntervalMs = 60_000;', main_source)
        self.assertIn('const response = await fetch(window.location.href, {', main_source)
        self.assertIn('cache: "no-store",', main_source)
        self.assertIn('window.location.reload();', main_source)
        self.assertIn('window.addEventListener("focus", handleFocus);', main_source)
        self.assertIn('document.addEventListener("visibilitychange", handleVisibilityChange);', main_source)

    def test_frontend_watchlist_remove_is_not_blocked_by_shell_reload_timeout(self) -> None:
        frontend_root = Path(__file__).resolve().parents[1] / "frontend" / "src"
        app_source = (frontend_root / "App.tsx").read_text(encoding="utf-8")
        api_core_source = (frontend_root / "api" / "core.ts").read_text(encoding="utf-8")
        api_watchlist_source = (frontend_root / "api" / "watchlist.ts").read_text(encoding="utf-8")
        remove_body = app_source.split("async function handleConfirmRemoveWatchlist()", 1)[1].split(
            "async function refreshManualResearchContext", 1,
        )[0]

        self.assertIn("function applyWatchlistRemoval(symbol: string): string | null", app_source)
        self.assertIn("const nextWatchlist = watchlist.filter((item) => item.symbol !== symbol);", app_source)
        self.assertIn("const nextSymbol = applyWatchlistRemoval(symbol);", remove_body)
        self.assertIn("void loadShellData(nextSymbol, { throwOnError: true }).catch((refreshError) => {", remove_body)
        self.assertNotIn("await reloadEverything(nextSymbol);", remove_body)
        self.assertIn("watchlistMutationRequestBehavior", api_watchlist_source)
        self.assertIn("attemptTimeoutMs: operationsDashboardTimeoutMs,", api_core_source)
        self.assertIn("本次连接等待超过 ${formatSeconds(attemptTimeout)}s", api_core_source)

    def test_operations_dashboard_exposes_manual_research_queue(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            queued = create_manual_research_request(
                session,
                symbol="600519.SH",
                question="请解释当前建议最容易失效的条件。",
                trigger_source="manual_research_ui",
                requested_by="operator:test",
                executor_kind=EXECUTOR_KIND_BUILTIN_GPT,
            )

        with session_scope(self.database_url) as session:
            operations = build_operations_dashboard(session, sample_symbol="600519.SH")

        queue = operations["manual_research_queue"]
        self.assertEqual(queue["focus_symbol"], "600519.SH")
        self.assertEqual(queue["counts"]["queued"], 1)
        self.assertEqual(queue["counts"]["in_progress"], 0)
        self.assertEqual(queue["focus_request"]["id"], queued["id"])
        self.assertEqual(queue["focus_request"]["symbol"], "600519.SH")
        self.assertEqual(queue["focus_request"]["status"], "queued")
        self.assertEqual(queue["recent_items"][0]["request_key"], queued["request_key"])
        self.assertEqual(
            queue["recent_items"][0]["manual_llm_review"]["request_key"],
            queued["request_key"],
        )

    def test_operations_dashboard_classifies_manual_research_terminal_states(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            completed_request = create_manual_research_request(
                session,
                symbol="600519.SH",
                question="请人工完成当前建议复核。",
                trigger_source="manual_research_ui",
                requested_by="operator:test",
                executor_kind=EXECUTOR_KIND_BUILTIN_GPT,
            )
            complete_manual_research_request(
                session,
                request_id=int(completed_request["id"]),
                summary="人工研究已完成。",
                review_verdict="supports_current_recommendation",
            )
            failed_request = create_manual_research_request(
                session,
                symbol="300750.SZ",
                question="请解释当前建议为什么需要回退。",
                trigger_source="manual_research_ui",
                requested_by="operator:test",
                executor_kind=EXECUTOR_KIND_BUILTIN_GPT,
            )
            fail_manual_research_request(
                session,
                request_id=int(failed_request["id"]),
                failure_reason="外部证据暂时不完整。",
            )

        with session_scope(self.database_url) as session:
            operations = build_operations_dashboard(session, sample_symbol="600519.SH")

        queue = operations["manual_research_queue"]
        self.assertEqual(queue["counts"]["queued"], 0)
        self.assertEqual(queue["counts"]["failed"], 1)
        self.assertEqual(queue["counts"]["completed_current"], 1)
        self.assertEqual(queue["focus_request"]["id"], completed_request["id"])
        recent_by_symbol = {item["symbol"]: item for item in queue["recent_items"]}
        self.assertEqual(recent_by_symbol["600519.SH"]["status"], "completed")
        self.assertEqual(recent_by_symbol["300750.SZ"]["status"], "failed")

    def test_operations_dashboard_scopes_simulation_to_active_watchlist(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            seed_recommendation_fixture(session, "688981.SH")
            add_watchlist_symbol(session, "688981", stock_name="中芯国际")
            remove_watchlist_symbol(session, "600519")

        with session_scope(self.database_url) as session:
            operations = build_operations_dashboard(session, sample_symbol="688981.SH")

        active_watchlist_symbols = {"300750.SZ", "601318.SH", "002594.SZ", "688981.SH"}
        replay_symbols = {item["symbol"] for item in operations["recommendation_replay"]}
        portfolio_symbols = {
            item["symbol"]
            for portfolio in operations["portfolios"]
            for item in [*portfolio["holdings"], *portfolio["recent_orders"]]
        }

        self.assertIn("688981.SH", replay_symbols)
        self.assertNotIn("600519.SH", replay_symbols)
        self.assertTrue(replay_symbols.issubset(active_watchlist_symbols))
        self.assertNotIn("600519.SH", portfolio_symbols)
        self.assertTrue(portfolio_symbols.issubset(active_watchlist_symbols))

    def test_operations_dashboard_tolerates_missing_sample_symbol(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            seed_recommendation_fixture(session, "688981.SH")
            add_watchlist_symbol(session, "688981", stock_name="中芯国际")
            remove_watchlist_symbol(session, "600519")

        with session_scope(self.database_url) as session:
            operations = build_operations_dashboard(session, sample_symbol="000001.SZ")

        replay_symbols = {item["symbol"] for item in operations["recommendation_replay"]}
        portfolio_symbols = {
            item["symbol"]
            for portfolio in operations["portfolios"]
            for item in [*portfolio["holdings"], *portfolio["recent_orders"]]
        }
        self.assertIn("688981.SH", replay_symbols)
        self.assertNotIn("600519.SH", replay_symbols)
        self.assertNotIn("600519.SH", portfolio_symbols)
        self.assertEqual(len(operations["portfolios"]), 2)

    def test_glossary_entries_cover_key_user_terms(self) -> None:
        glossary = get_glossary_entries()
        terms = {item["term"] for item in glossary}
        self.assertIn("滚动验证", terms)
        self.assertIn("降级条件", terms)
        self.assertIn("人工研究层", terms)

    def test_watchlist_can_add_custom_symbol_and_remove_it(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            seed_recommendation_fixture(session, "688981.SH")
            item = add_watchlist_symbol(session, "688981", stock_name="中芯国际")

        self.assertEqual(item["symbol"], "688981.SH")
        self.assertEqual(item["name"], "中芯国际")

        with session_scope(self.database_url) as session:
            watchlist = list_watchlist_entries(session)
            candidates = list_candidate_recommendations(session, limit=10)
            dashboard = get_stock_dashboard(session, "688981.SH")

        self.assertIn("688981.SH", {entry["symbol"] for entry in watchlist["items"]})
        self.assertIn("688981.SH", {entry["symbol"] for entry in candidates["items"]})
        self.assertEqual(dashboard["stock"]["name"], "中芯国际")
        self.assertGreaterEqual(len(dashboard["price_chart"]), 24)

        with session_scope(self.database_url) as session:
            removal = remove_watchlist_symbol(session, "688981")

        self.assertTrue(removal["removed"])

        with session_scope(self.database_url) as session:
            candidates = list_candidate_recommendations(session, limit=10)

        self.assertNotIn("688981.SH", {entry["symbol"] for entry in candidates["items"]})

    def test_watchlist_resolves_known_stock_name_and_sector(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            seed_recommendation_fixture(session, "002028.SZ")
            item = add_watchlist_symbol(session, "002028")

        self.assertEqual(item["symbol"], "002028.SZ")
        self.assertEqual(item["name"], "思源电气")

        with session_scope(self.database_url) as session:
            candidates = list_candidate_recommendations(session, limit=10)
            dashboard = get_stock_dashboard(session, "002028.SZ")

        candidate = next(entry for entry in candidates["items"] if entry["symbol"] == "002028.SZ")
        self.assertEqual(candidate["name"], "思源电气")
        self.assertEqual(candidate["sector"], "电力设备")
        self.assertEqual(dashboard["stock"]["name"], "思源电气")
        self.assertIn("电力设备", dashboard["hero"]["sector_tags"])
        self.assertNotIn("医药生物", dashboard["hero"]["sector_tags"])

    def test_refresh_watchlist_rebuilds_real_analysis_when_sources_are_available(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            seed_recommendation_fixture(session, "002028.SZ")
            added = add_watchlist_symbol(session, "002028")
            latest_before = added["latest_generated_at"]

        with session_scope(self.database_url) as session:
            refreshed = refresh_watchlist_symbol(session, "002028")
        self.assertEqual(refreshed["name"], "思源电气")
        self.assertGreaterEqual(refreshed["latest_generated_at"], latest_before)
        self.assertEqual(refreshed["analysis_status"], "ready")

    def test_refresh_watchlist_repairs_profile_snapshot_when_full_rebuild_fails(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            seed_recommendation_fixture(session, "002028.SZ")
            add_watchlist_symbol(session, "002028")

        with session_scope(self.database_url) as session:
            with patch("ashare_evidence.watchlist.refresh_real_analysis", side_effect=RuntimeError("缺少足够日线")):
                with patch("ashare_evidence.watchlist.repair_stock_profile_snapshot") as repair_mock:
                    refreshed = refresh_watchlist_symbol(session, "002028")

        repair_mock.assert_called_once()
        self.assertEqual(refreshed["analysis_status"], "ready")
        self.assertIn("真实数据刷新失败", refreshed["last_error"] or "")


if __name__ == "__main__":
    unittest.main()
