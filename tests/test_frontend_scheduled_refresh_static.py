import unittest
from pathlib import Path


class FrontendScheduledRefreshStaticTests(unittest.TestCase):
    def test_dashboard_surfaces_scheduled_refresh_status(self) -> None:
        frontend_root = Path(__file__).resolve().parents[1] / "frontend" / "src"
        app_source = (frontend_root / "App.tsx").read_text(encoding="utf-8")
        mobile_home = (frontend_root / "components" / "mobile" / "MobileHome.tsx").read_text(encoding="utf-8")
        api_source = (frontend_root / "api" / "dashboard.ts").read_text(encoding="utf-8")

        self.assertIn("/dashboard/scheduled-refresh-status", api_source)
        self.assertIn("scheduledRefreshStatus", app_source)
        self.assertIn("ashare-dismissed-scheduled-refresh", app_source)
        self.assertIn("dismissScheduledRefreshStatus", app_source)
        self.assertIn("closable", app_source)
        self.assertIn("每日分析", app_source)
        self.assertIn("正在跑", app_source)
        self.assertIn("失败", app_source)
        self.assertIn("待补跑", app_source)
        self.assertIn("components", app_source)
        self.assertIn("试验田", app_source)
        self.assertIn("mobile-refresh-status", mobile_home)
        self.assertIn("props.scheduledRefreshStatus", mobile_home)
        self.assertIn("props.onDismissScheduledRefreshStatus", mobile_home)
        self.assertIn("components", mobile_home)


if __name__ == "__main__":
    unittest.main()
