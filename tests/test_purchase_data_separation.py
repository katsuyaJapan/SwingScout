import unittest
from pathlib import Path


class PurchaseDataSeparationTest(unittest.TestCase):
    def test_exit_panel_does_not_use_personal_purchase_values(self):
        app = (Path(__file__).resolve().parents[1] / "src" / "App.tsx").read_text()
        panel = app.split("function ExitStrategyPanel", 1)[1].split("function PurchasePanel", 1)[0]
        self.assertNotIn("record.price", panel)
        self.assertNotIn("record.purchasedAt", panel)
        self.assertIn("candidate.entry_price ?? candidate.close", panel)
        self.assertIn("個人購入データは使用しません", panel)
        self.assertIn('candidate.profit_protection_signal &&', panel)

    def test_missing_exit_data_is_not_shown_as_hold(self):
        app = (Path(__file__).resolve().parents[1] / "src" / "App.tsx").read_text()
        display = app.split("const exitDisplay", 1)[1].split("const healthIcon", 1)[0]
        self.assertIn('label: "判定保留"', display)
        self.assertNotIn('status ?? "HOLD"', display)


if __name__ == "__main__":
    unittest.main()
