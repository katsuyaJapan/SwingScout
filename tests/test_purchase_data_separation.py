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


if __name__ == "__main__":
    unittest.main()
