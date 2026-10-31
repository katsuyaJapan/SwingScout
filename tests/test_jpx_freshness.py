import argparse
import importlib.util
import unittest
import sys
from unittest.mock import patch
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_jpx_freshness.py"
sys.path.insert(0, str(MODULE_PATH.parent))
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

    def test_main_uses_publication_feed_date(self):
        with patch.object(MODULE.argparse.ArgumentParser, "parse_args", return_value=argparse.Namespace(mark_waiting=False)), \
             patch.object(MODULE, "read_status", return_value={"dataAsOf": "20261014"}), \
             patch.object(MODULE, "latest_publication_date", return_value="20261015"), \
             patch.object(MODULE, "write_output") as output:
            MODULE.main()
        output.assert_any_call("jpx_date", "20261015")
        output.assert_any_call("refresh_required", "true")

    def test_same_day_official_confirmation_runs_once(self):
        for price_status, official, expected in (
            ("PROVISIONAL", "20261029", "true"),
            ("JPX_CONFIRMED", "20261030", "false"),
            ("PROVISIONAL", "20261029", "false"),
        ):
            publication = "20261029" if expected == "false" and price_status == "PROVISIONAL" else "20261030"
            with self.subTest(price_status=price_status, publication=publication), \
                 patch.object(MODULE.argparse.ArgumentParser, "parse_args", return_value=argparse.Namespace(mark_waiting=False)), \
                 patch.object(MODULE, "read_status", return_value={"dataAsOf": "20261030"}), \
                 patch.object(MODULE, "read_json", return_value={"priceStatus": price_status, "officialAsOf": official}), \
                 patch.object(MODULE, "latest_publication_date", return_value=publication), \
                 patch.object(MODULE, "write_output") as output:
                MODULE.main()
            output.assert_any_call("refresh_required", expected)


if __name__ == "__main__":
    unittest.main()
