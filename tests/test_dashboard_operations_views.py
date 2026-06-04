# ruff: noqa: F403,F405
from __future__ import annotations

from tests.dashboard_views_test_support import *


class DashboardOperationsViewTests(DashboardViewTestCase):
    def test_operations_dashboard_contains_portfolios_replay_and_launch_gates(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)

        with session_scope(self.database_url) as session:
            operations = build_operations_dashboard(
                session,
                sample_symbol="600519.SH",
                include_simulation_workspace=True,
            )

        self.assertEqual(operations["market_data_timeframe"], "5min")
        self.assertEqual(operations["intraday_source_status"]["timeframe"], "5min")
        self.assertEqual(operations["overview"]["manual_portfolio_count"], 1)
        self.assertEqual(operations["overview"]["auto_portfolio_count"], 1)
        self.assertEqual(operations["overview"]["research_validation"]["status"], "pending_rebuild")
        self.assertEqual(operations["overview"]["run_health"]["market_data_timeframe"], "5min")
        self.assertGreaterEqual(operations["overview"]["launch_readiness"]["warning_gate_count"], 1)
        self.assertIsNone(operations["overview"]["recommendation_replay_hit_rate"])
        self.assertGreaterEqual(operations["overview"]["research_validation"]["manifest_bound_count"], 1)
        self.assertGreaterEqual(operations["overview"]["research_validation"]["metrics_artifact_count"], 1)
        self.assertGreaterEqual(operations["overview"]["research_validation"]["artifact_sample_count"], 1)
        self.assertEqual(
            operations["overview"]["research_validation"]["phase5_horizon_selection"]["approval_state"],
            "insufficient_phase5_evidence",
        )
        self.assertEqual(
            operations["overview"]["research_validation"]["phase5_holding_policy_study"]["approval_state"],
            "research_candidate_only",
        )
        self.assertEqual(
            operations["overview"]["research_validation"]["phase5_holding_policy_study"]["gate_status"],
            "draft_gate_blocked",
        )
        self.assertEqual(
            operations["overview"]["research_validation"]["phase5_holding_policy_study"]["governance_status"],
            "maintain_non_promotion_until_gate_passes",
        )
        self.assertEqual(
            operations["overview"]["research_validation"]["phase5_holding_policy_study"]["governance_action"],
            "continue_gate_research_without_promotion",
        )
        self.assertEqual(
            operations["overview"]["research_validation"]["phase5_holding_policy_study"]["redesign_status"],
            "no_structured_redesign_signal",
        )
        self.assertEqual(
            operations["overview"]["research_validation"]["phase5_holding_policy_study"][
                "redesign_primary_experiment_ids"
            ],
            [],
        )
        self.assertEqual(
            operations["overview"]["research_validation"]["phase5_holding_policy_study"]["redesign_focus_areas"],
            [],
        )
        self.assertEqual(
            operations["overview"]["research_validation"]["phase5_holding_policy_study"][
                "redesign_triggered_signal_ids"
            ],
            [],
        )
        self.assertIn(
            "included_portfolio_count",
            operations["overview"]["research_validation"]["phase5_holding_policy_study"]["failing_gate_ids"],
        )
        self.assertFalse(
            operations["overview"]["research_validation"]["phase5_horizon_selection"]["artifact_available"]
        )
        self.assertFalse(
            operations["overview"]["research_validation"]["phase5_holding_policy_study"]["artifact_available"]
        )
        self.assertEqual(
            operations["overview"]["research_validation"]["phase5_holding_policy_study"]["included_portfolio_count"],
            1,
        )
        self.assertIsNotNone(
            operations["overview"]["research_validation"]["phase5_holding_policy_study"]["mean_turnover"]
        )
        self.assertEqual(
            operations["overview"]["research_validation"]["replay_artifact_bound_count"],
            len(operations["recommendation_replay"]),
        )
        self.assertEqual(
            operations["overview"]["research_validation"]["replay_artifact_manifest_count"],
            len(operations["recommendation_replay"]),
        )
        self.assertEqual(
            operations["overview"]["research_validation"]["replay_artifact_nonverified_count"],
            len(operations["recommendation_replay"]),
        )
        self.assertEqual(
            operations["overview"]["research_validation"]["replay_artifact_backed_projection_count"],
            len(operations["recommendation_replay"]),
        )
        self.assertEqual(
            operations["overview"]["research_validation"]["replay_migration_placeholder_count"],
            len(operations["recommendation_replay"]),
        )
        self.assertEqual(operations["overview"]["research_validation"]["portfolio_backtest_bound_count"], 2)
        self.assertEqual(operations["overview"]["research_validation"]["portfolio_backtest_manifest_count"], 2)
        self.assertEqual(operations["overview"]["research_validation"]["portfolio_backtest_verified_count"], 0)
        self.assertEqual(operations["overview"]["research_validation"]["portfolio_backtest_pending_rebuild_count"], 2)
        self.assertEqual(operations["overview"]["research_validation"]["portfolio_backtest_artifact_backed_projection_count"], 2)
        self.assertEqual(operations["overview"]["research_validation"]["portfolio_backtest_migration_placeholder_count"], 2)
        self.assertEqual(len(operations["portfolios"]), 2)
        self.assertGreaterEqual(len(operations["recommendation_replay"]), 4)
        self.assertGreaterEqual(len(operations["launch_gates"]), 6)
        self.assertTrue(all(portfolio["nav_history"] for portfolio in operations["portfolios"]))
        self.assertTrue(all(portfolio["recent_orders"] for portfolio in operations["portfolios"]))
        self.assertTrue(all(portfolio["rules"] for portfolio in operations["portfolios"]))
        self.assertTrue(all(portfolio["market_data_timeframe"] == "5min" for portfolio in operations["portfolios"]))
        first_portfolio = operations["portfolios"][0]
        self.assertEqual(first_portfolio["validation_status"], "pending_rebuild")
        self.assertEqual(first_portfolio["execution_policy"]["status"], "research_candidate")
        self.assertEqual(first_portfolio["execution_policy"]["policy_type"], "phase5_simulation_topk_equal_weight_v1")
        self.assertEqual(first_portfolio["benchmark_context"]["status"], "pending_rebuild")
        self.assertEqual(first_portfolio["benchmark_note"], first_portfolio["benchmark_context"]["note"])
        self.assertEqual(first_portfolio["benchmark_context"]["source_classification"], "artifact_backed")
        self.assertIsNone(first_portfolio["recommendation_hit_rate"])
        self.assertTrue(first_portfolio["validation_artifact_id"])
        self.assertTrue(first_portfolio["validation_manifest_id"])
        self.assertEqual(first_portfolio["benchmark_context"]["source"], "portfolio_backtest_artifact")
        self.assertEqual(first_portfolio["benchmark_context"]["artifact_id"], first_portfolio["validation_artifact_id"])
        self.assertEqual(first_portfolio["benchmark_context"]["manifest_id"], first_portfolio["validation_manifest_id"])
        self.assertEqual(first_portfolio["benchmark_context"]["benchmark_definition"], "active_watchlist_equal_weight_proxy")
        self.assertIsNotNone(first_portfolio["performance"]["annualized_return"])
        self.assertIsNotNone(first_portfolio["performance"]["annualized_excess_return"])
        self.assertIsNotNone(first_portfolio["performance"]["turnover"])
        self.assertTrue(first_portfolio["performance"]["win_rate_definition"])
        self.assertEqual(first_portfolio["performance"]["artifact_id"], first_portfolio["validation_artifact_id"])
        self.assertEqual(first_portfolio["performance"]["validation_mode"], "migration_placeholder")
        self.assertEqual(first_portfolio["performance"]["benchmark_definition"], "active_watchlist_equal_weight_proxy")
        self.assertEqual(first_portfolio["performance"]["cost_source"], "artifact_backed")
        first_replay = operations["recommendation_replay"][0]
        self.assertEqual(first_replay["source"], "replay_alignment_artifact")
        self.assertEqual(first_replay["source_classification"], "artifact_backed")
        self.assertEqual(first_replay["artifact_type"], "replay_alignment")
        self.assertTrue(first_replay["artifact_id"])
        self.assertTrue(first_replay["recommendation_key"])
        self.assertEqual(first_replay["label_definition"], "migration_directional_replay_pending")
        self.assertEqual(
            first_replay["review_window_definition"],
            "migration_latest_available_close_vs_watchlist_equal_weight_proxy",
        )
        self.assertEqual(first_replay["benchmark_definition"], "active_watchlist_equal_weight_proxy")
        self.assertEqual(first_replay["benchmark_source"], "artifact_backed")
        self.assertEqual(first_replay["validation_mode"], "migration_placeholder")
        self.assertTrue(first_replay["hit_definition"])
        self.assertLessEqual(first_replay["entry_time"], first_replay["exit_time"])
        launch_gates = {gate["gate"]: gate for gate in operations["launch_gates"]}
        first_gate = set(launch_gates)
        self.assertIn("分离式模拟交易", first_gate)
        self.assertIn("组合回测产物绑定", first_gate)
        self.assertIn("A 股规则合规", first_gate)
        self.assertEqual(launch_gates["组合回测产物绑定"]["status"], "warn")
        self.assertIn("verified=0", launch_gates["组合回测产物绑定"]["current_value"])

    def test_completed_improvement_plan_does_not_pass_replay_gate_without_formal_evidence(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            root = artifact_root_from_database_url(self.database_url)

        suggestions = [
            {
                "suggestion_id": "suggestion:coverage-plan",
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
                    "id": "task-coverage-plan",
                    "status": "succeeded",
                    "model": "gpt-5.5",
                    "project_id": "ashare-dashboard",
                    "plan_mode": True,
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

        with session_scope(self.database_url) as session:
            operations = build_operations_dashboard(session)

        launch_gates = {gate["gate"]: gate for gate in operations["launch_gates"]}
        coverage_gate = launch_gates["建议命中复盘覆盖"]
        self.assertEqual(coverage_gate["status"], "warn")
        self.assertIn("治理计划已完成（task-coverage-plan）", coverage_gate["current_value"])
        self.assertIn("正式复盘口径仍待验证", coverage_gate["current_value"])

    def test_operations_dashboard_can_embed_simulation_workspace(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)

        with session_scope(self.database_url) as session:
            operations = build_operations_dashboard(
                session,
                sample_symbol="600519.SH",
                include_simulation_workspace=True,
            )

        workspace = operations["simulation_workspace"]
        self.assertIsNotNone(workspace)
        assert workspace is not None
        self.assertEqual(workspace["session"]["status"], "draft")
        self.assertEqual(workspace["session"]["market_data_timeframe"], "5min")
        self.assertEqual(workspace["session"]["market_data_interval_seconds"], 300)
        self.assertTrue(workspace["controls"]["can_start"])
        self.assertGreaterEqual(len(workspace["kline"]["points"]), 24)
        self.assertEqual(workspace["manual_track"]["label"], "用户轨道")
        self.assertEqual(workspace["model_track"]["label"], "模型轨道")
        self.assertEqual(workspace["manual_track"]["portfolio"]["starting_cash"], workspace["session"]["initial_cash"])

    def test_operations_dashboard_user_visible_projection_blocks_migration_terms(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)

        with session_scope(self.database_url) as session:
            operations = build_operations_dashboard(
                session,
                sample_symbol="600519.SH",
                include_simulation_workspace=True,
            )

        audit = audit_user_visible_operations_text(operations)

        self.assertTrue(audit["passed"])
        self.assertIn("用户轨道", audit["combined_text"])
        self.assertIn("模型轨道", audit["combined_text"])
        self.assertNotIn("Phase 5 baseline", audit["combined_text"])
        self.assertNotIn("research contract", audit["combined_text"])
        self.assertNotIn("运营复盘口径仍在迁移", audit["combined_text"])

    def test_operations_dashboard_audit_sanitizes_manual_review_internal_terms(self) -> None:
        with session_scope(self.database_url) as session:
            seed_watchlist_fixture(session)
            request = create_manual_research_request(
                session,
                symbol="600519.SH",
                question="请解释当前建议为什么需要人工研究。",
                trigger_source="manual_research_ui",
                requested_by="operator:test",
                executor_kind=EXECUTOR_KIND_BUILTIN_GPT,
            )
            complete_manual_research_request(
                session,
                request_id=int(request["id"]),
                summary="pending_rebuild：research contract 仍引用 Phase 5 baseline。",
                review_verdict="mixed",
                risks=[
                    "manual-review:case-1 仍写着 pending_rebuild。",
                    "validation-metrics:case-1 需要和 research contract 对齐。",
                ],
                disagreements=["rolling-validation:case-1 仍在 Phase 5 baseline 口径。"],
                decision_note="建议把 pending_rebuild 改成面向用户的说明。",
                citations=["portfolio-backtest:case-1"],
                answer="当前结论引用了 forward_excess_return_20d 与 14-56 trade days。",
            )

        with session_scope(self.database_url) as session:
            operations = build_operations_dashboard(
                session,
                sample_symbol="600519.SH",
                include_simulation_workspace=True,
            )

        audit = audit_user_visible_operations_text(operations)
        review = operations["manual_research_queue"]["recent_items"][0]["manual_llm_review"]

        self.assertTrue(audit["passed"])
        self.assertEqual(audit["banned_hits"], [])
        self.assertIn("口径校准中", review["summary"])
        self.assertIn("研究口径", review["summary"])
        self.assertIn("等权组合研究策略", review["summary"])
        self.assertIn("人工研究记录", review["risks"][0])
        self.assertIn("验证指标记录", review["risks"][1])
        self.assertIn("滚动验证记录", review["disagreements"][0])
        self.assertEqual(review["citations"], ["组合回测记录"])
        self.assertIn("20日超额收益", review["raw_answer"])
        self.assertIn("the window under rolling validation", review["raw_answer"])

    def test_operations_dashboard_audit_blocks_placeholder_professionalism_terms(self) -> None:
        audit = audit_user_visible_operations_text(
            {
                "overview": {
                    "title": "用户轨道",
                    "summary": "模型轨道",
                    "note": "用于汇总价格、事件与降级状态的融合层。",
                    "risk_flags": ["event_conflict_high", "missing_news_evidence"],
                }
            }
        )

        self.assertFalse(audit["passed"])
        self.assertIn("event_conflict_high", audit["banned_hits"])
        self.assertIn("missing_news_evidence", audit["banned_hits"])
        self.assertIn("用于汇总价格、事件与降级状态的融合层", audit["banned_hits"])

    def test_frontend_manual_research_projection_sanitizes_user_visible_fields(self) -> None:
        source = (
            Path(__file__).resolve().parents[1] / "frontend" / "src" / "App.tsx"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "description={sanitizeDisplayText(dashboard.recommendation.manual_llm_review.stale_reason)}",
            source,
        )
        self.assertIn(
            "sanitizeDisplayText(dashboard.recommendation.manual_llm_review.summary)",
            source,
        )
        self.assertIn(
            "sanitizeDisplayText(dashboard.recommendation.manual_llm_review.decision_note)",
            source,
        )
        self.assertIn(
            "<li key={item}>{sanitizeDisplayText(item)}</li>",
            source,
        )
        self.assertIn(
            '<Tag color="blue">已生成研究记录</Tag>',
            source,
        )
        self.assertNotIn(
            "description={dashboard.recommendation.manual_llm_review.stale_reason}",
            source,
        )
        self.assertNotIn(
            "<Tag>{analysisAnswer.artifact_id}</Tag>",
            source,
        )

    def test_frontend_manual_research_display_fallback_sanitizes_timeout_related_internal_terms(self) -> None:
        source = (
            Path(__file__).resolve().parents[1] / "frontend" / "src" / "utils" / "labels.ts"
        ).read_text(encoding="utf-8")

        self.assertIn('.replace(/pending_rebuild/g, "口径校准中")', source)
        self.assertIn('.replace(/research_rebuild_pending/g, "滚动验证口径校准中")', source)
        self.assertIn('.replace(/forward_excess_return_(\\d+)d/g, "$1日超额收益")', source)
        self.assertIn('.replace(/14-56 trade days/g, "the window under rolling validation")', source)
        self.assertIn('.replace(/missing_news_evidence/g, "近期缺少新增事件证据，当前更多依赖价格趋势观察")', source)
        self.assertIn('.replace(/event_conflict_high/g, "价格与事件方向冲突较高，系统已主动下调对外表达")', source)
        self.assertIn('.replace(/market_data_stale/g, "最新行情刷新偏旧，短线结论需要谨慎使用")', source)
        self.assertIn('.replace(/用于汇总价格、事件与降级状态的融合层。?/g, "价格与事件综合后，当前先看趋势是否得到新增证据确认")', source)

    def test_frontend_operations_track_tables_keep_overflow_scoped_to_card(self) -> None:
        frontend_root = Path(__file__).resolve().parents[1] / "frontend" / "src"
        app_source = (frontend_root / "App.tsx").read_text(encoding="utf-8")
        track_table_source = (frontend_root / "components" / "TrackHoldingsTable.tsx").read_text(encoding="utf-8")
        track_card_source = (frontend_root / "components" / "SimulationTrackCard.tsx").read_text(encoding="utf-8")
        style_source = (frontend_root / "styles.css").read_text(encoding="utf-8")
        focus_change_section = app_source.split("async function handleSimulationFocusChange(symbol: string) {", 1)[1]
        focus_change_body = focus_change_section.split("function openManualOrderModal", 1)[0]

        self.assertIn('const [operationsFocusSymbol, setOperationsFocusSymbol] = useState<string | null>(null);', app_source)
        self.assertIn("const response = await api.updateSimulationConfig({", app_source)
        self.assertIn("setOperationsFocusSymbol(nextFocusSymbol);", app_source)
        self.assertNotIn("setSelectedSymbol(symbol);", focus_change_body)
        self.assertIn('<div className="track-holdings-shell">', track_table_source)
        self.assertIn('className="track-holdings-table"', track_table_source)
        self.assertIn('scroll={{ x: "max-content" }}', track_table_source)
        self.assertIn("event.stopPropagation();", track_table_source)
        self.assertIn('className="panel-card simulation-track-card"', track_card_source)
        self.assertNotIn('scroll={{ x: 980 }}', app_source)
        self.assertEqual(app_source.count("<Col xs={24} xxl={12}>"), 2)
        self.assertIn('<Col xs={24} xxl={12}>\n                        <SimulationTrackCard', app_source)
        self.assertIn("当前表格默认展示当前模拟股票池。", app_source)
        self.assertIn('`模拟池 ${simulation.session.watch_symbols.length} 只`', app_source)

        self.assertIn(".track-holdings-shell {", style_source)
        self.assertIn(".track-holdings-table .ant-table-content {", style_source)
        self.assertIn("overflow-x: auto !important;", style_source)
        self.assertIn("overscroll-behavior-x: contain;", style_source)
        self.assertIn(".simulation-track-card .ant-card-extra {", style_source)
        self.assertIn(".panel-card > .ant-card-body > *,", style_source)
        self.assertIn("min-width: 0;", style_source)

    def test_frontend_candidate_return_color_and_operations_report_button_follow_current_contract(self) -> None:
        frontend_root = Path(__file__).resolve().parents[1] / "frontend" / "src"
        app_source = (frontend_root / "App.tsx").read_text(encoding="utf-8")
        candidate_columns_source = (frontend_root / "components" / "CandidateColumns.tsx").read_text(encoding="utf-8")
        mobile_stock_row_source = (frontend_root / "components" / "mobile" / "MobileStockRow.tsx").read_text(encoding="utf-8")

        self.assertIn('className={`value-${valueTone(record.candidate.price_return_20d)}`}', candidate_columns_source)
        self.assertIn('className={`value-${valueTone(candidate?.price_return_20d)}`}', mobile_stock_row_source)
        self.assertNotIn('type={record.candidate.price_return_20d >= 0 ? "success" : "danger"}', candidate_columns_source)
        self.assertIn("运营复盘分析报告", app_source)
        self.assertIn("onOpenReport={(symbol) => void openAnalysisReportModal(symbol)}", app_source)

    def test_frontend_manual_research_entry_exposes_visible_jump_to_workspace(self) -> None:
        frontend_root = Path(__file__).resolve().parents[1] / "frontend" / "src"
        app_source = (frontend_root / "App.tsx").read_text(encoding="utf-8")
        style_source = (frontend_root / "styles.css").read_text(encoding="utf-8")

        self.assertIn('const [stockActiveTab, setStockActiveTab] = useState<StockTabKey>(() => initialStockTabFromUrl());', app_source)
        self.assertIn("function openManualResearchWorkspace()", app_source)
        self.assertIn('writeWorkbenchRoute({ view: "stock", stockTab: "followup" }, "push");', app_source)
        self.assertIn('setStockActiveTab("followup");', app_source)
        self.assertIn('<Button type="primary" size="small" onClick={openManualResearchWorkspace}>', app_source)
        self.assertIn("发起人工研究", app_source)
        self.assertIn('入口在下方"追问与模拟"标签。', app_source)
        self.assertIn("选择模型 Key 后会立即执行外部模型研究；不选择时使用本机默认模型。", app_source)
        self.assertIn('<Tabs activeKey={stockActiveTab} onChange={(key) => routeStockTab(key)} items={visibleStockTabItems} />', app_source)
        self.assertIn(".manual-research-entry-actions {", style_source)
