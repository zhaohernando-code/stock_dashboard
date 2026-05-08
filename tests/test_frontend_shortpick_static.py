import unittest
from pathlib import Path


class FrontendShortpickStaticTests(unittest.TestCase):
    def test_shortpick_lab_is_independent_research_surface(self) -> None:
        frontend_root = Path(__file__).resolve().parents[1] / "frontend" / "src"
        app_source = (frontend_root / "App.tsx").read_text(encoding="utf-8")
        component_source = (frontend_root / "components" / "ShortpickLabView.tsx").read_text(encoding="utf-8")
        api_source = (frontend_root / "api" / "shortpick.ts").read_text(encoding="utf-8")

        self.assertIn('label: "试验田"', app_source)
        self.assertIn("<ShortpickLabView canTrigger={isRootUser}", app_source)
        self.assertIn("独立研究课题，不进入主推荐评分", component_source)
        self.assertIn("模型一致性只代表研究优先级，不代表交易建议", component_source)
        self.assertIn("后验验证完成前不得显示为已验证能力", component_source)
        self.assertIn("sourceCredibilityLabel", component_source)
        self.assertIn("sourceCredibilityColor", component_source)
        self.assertIn("credibility_status", component_source)
        self.assertIn("校验：", component_source)
        self.assertIn("主基准：", component_source)
        self.assertIn("沪深300", component_source)
        self.assertIn("超额收益", component_source)
        self.assertIn("pending_benchmark_data", component_source)
        self.assertIn("待基准", component_source)
        self.assertIn("前向K线", component_source)
        self.assertIn("重跑接口返回 404", component_source)
        self.assertIn("shortpick-feedback-summary", component_source)
        self.assertIn("shortpick-feedback-table", component_source)
        self.assertIn("shortpick-benchmark-select", component_source)
        self.assertIn("shortpick-validation-card", component_source)
        self.assertIn('label: "历史回放"', component_source)
        self.assertIn('activeKey={latestRun ? activeWorkspaceTab : "replay"}', component_source)
        self.assertIn("loadMarketStudy", component_source)
        self.assertIn("历史回放主体不依赖这项重计算", component_source)
        self.assertIn("暂无 live shortpick 批次；可先查看历史回放。", component_source)
        self.assertIn("历史回放核心读数", component_source)
        self.assertIn("无上下文直接查询能否短投选股", component_source)
        self.assertIn("1 / 3 / 5 / 10 / 20 日", component_source)
        self.assertIn("模型与对照组比较", component_source)
        self.assertIn("封闭数据包与来源清单", component_source)
        self.assertIn("泄漏审计", component_source)
        self.assertIn("random_same_market_cap_bucket", component_source)
        self.assertIn("momentum_volume_baseline", component_source)
        self.assertIn("去最佳单票", component_source)
        self.assertIn("getShortpickReplayRuns", api_source)
        self.assertIn("/shortpick-lab/replay-runs", api_source)
        self.assertNotIn("<Segmented", component_source)
        self.assertIn('align: "center"', component_source)
        self.assertIn("/shortpick-lab/runs", api_source)
        self.assertIn("/shortpick-lab/candidates", api_source)
        self.assertNotIn("addWatchlist", component_source)
        self.assertNotIn("getStockDashboard", component_source)

    def test_local_preview_does_not_fallback_to_vite_origin_for_api(self) -> None:
        frontend_root = Path(__file__).resolve().parents[1] / "frontend" / "src"
        core_source = (frontend_root / "api" / "core.ts").read_text(encoding="utf-8")

        self.assertIn("function isLocalPreviewOrigin()", core_source)
        self.assertIn("window.location.port !== \"8000\"", core_source)
        self.assertIn("isLocalPreviewOrigin() ? [] : [inferOriginBase()]", core_source)
        self.assertIn("!inferLocalBackendBase() && !basesToUse.includes(\"\")", core_source)


if __name__ == "__main__":
    unittest.main()
