import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_jpx_freshness.py"
SPEC = importlib.util.spec_from_file_location("check_jpx_freshness", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


class JpxFreshnessTests(unittest.TestCase):
    def test_extracts_latest_date(self):
        html = "<td>2026/08/19</td><td>2026/08/20</td><td>2026/08/18</td>"
        self.assertEqual(MODULE.extract_latest_date(html), "20260820")

    def test_rejects_page_without_dates(self):
        with self.assertRaises(ValueError):
            MODULE.extract_latest_date("<html>maintenance</html>")


if __name__ == "__main__":
    unittest.main()
