import unittest
from pathlib import Path


class FrontendThemeStaticTests(unittest.TestCase):
    def test_ant_design_modal_and_message_use_theme_context(self) -> None:
        frontend_root = Path(__file__).resolve().parents[1] / "frontend" / "src"
        main_source = (frontend_root / "main.tsx").read_text(encoding="utf-8")
        app_source = (frontend_root / "App.tsx").read_text(encoding="utf-8")
        operations_source = (frontend_root / "components" / "OperationsTabs.tsx").read_text(encoding="utf-8")
        settings_source = (frontend_root / "components" / "SettingsView.tsx").read_text(encoding="utf-8")
        combined_source = "\n".join([app_source, operations_source, settings_source])

        self.assertIn("App as AntdApp", main_source)
        self.assertIn("<AntdApp>", main_source)
        self.assertIn("AntdApp.useApp()", app_source)
        self.assertNotIn("message.useMessage", app_source)
        self.assertNotIn("Modal.confirm(", combined_source)
        self.assertIn("modal.confirm({", app_source)
        self.assertIn("modalApi.confirm({", operations_source)
        self.assertIn("modalApi.confirm({", settings_source)
        self.assertIn("modalApi: modal", app_source)
        self.assertIn("选择执行模型", operations_source)
        self.assertIn("进入计划池并创建中台任务", operations_source)

    def test_dark_theme_relies_on_antd_tokens_not_select_modal_hacks(self) -> None:
        style_source = (Path(__file__).resolve().parents[1] / "frontend" / "src" / "styles.css").read_text(
            encoding="utf-8"
        )

        self.assertNotIn(".ant-select-dropdown", style_source)
        self.assertNotIn("body[data-theme=\"dark\"] .ant-modal-content", style_source)
        self.assertNotIn(".app-theme-shell[data-theme=\"dark\"] .ant-modal-content", style_source)
        self.assertNotIn("body[data-theme=\"dark\"] .ant-popover-inner", style_source)
        self.assertNotIn(".app-theme-shell[data-theme=\"dark\"] .ant-popover-inner", style_source)
        self.assertNotIn("body[data-theme=\"dark\"] .ant-select-selector", style_source)
        self.assertNotIn(".app-theme-shell[data-theme=\"dark\"] .ant-select-selector", style_source)


if __name__ == "__main__":
    unittest.main()
