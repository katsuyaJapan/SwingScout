import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import jpx_daily_sources as sources


def feed(days):
    return json.dumps({"TableDatas": [{"TradeDate": day, "Stocks": f"/automation/files/stq_{day}.pdf"} for day in days]})


class DailySourcesTest(unittest.TestCase):
    def test_migration_json_and_old_html_are_combined(self):
        documents = {
            sources.MONTHS_URL: json.dumps({"TableDatas": [{"Month": "202610"}, {"Month": "202609"}]}),
            sources.FEED + "tsedaily_report_202610.json": feed(["20261015"]),
            sources.FEED + "tsedaily_report_202609.json": feed(["20260930"]),
            sources.FEED + "tsedaily_report_202608.html": '<a href="/old/stq_20260831.pdf">stock</a><a href="/old/boq_20260831.pdf">bond</a>',
        }
        links = sources.discover_daily_links(documents.__getitem__, days=3)
        self.assertEqual([day for day, _ in links], ["20260831", "20260930", "20261015"])
        self.assertEqual(sources.latest_publication_date(documents.__getitem__), "20261015")

    def test_rolls_back_across_years(self):
        self.assertEqual(sources.previous_month("202601", 1), "202512")
        self.assertEqual(sources.previous_month("202601", 13), "202412")

    def test_missing_month_is_not_silently_skipped(self):
        documents = {
            sources.MONTHS_URL: json.dumps({"TableDatas": [{"Month": "202610"}, {"Month": "202608"}]}),
            sources.FEED + "tsedaily_report_202610.json": feed(["20261015"]),
        }
        with self.assertRaisesRegex(ValueError, "Missing JPX month"):
            sources.discover_daily_links(documents.__getitem__, days=2)

    def test_rejects_empty_month_and_date_mismatch(self):
        with self.assertRaisesRegex(ValueError, "date mismatch"):
            sources.json_stock_links(feed(["20260930"]), "202610")
        documents = {
            sources.MONTHS_URL: json.dumps({"TableDatas": [{"Month": "202610"}]}),
            sources.FEED + "tsedaily_report_202610.json": feed([]),
        }
        with self.assertRaisesRegex(ValueError, "no stock PDFs"):
            sources.discover_daily_links(documents.__getitem__)

    def test_rejects_external_urls(self):
        with self.assertRaisesRegex(ValueError, "Invalid JPX"):
            sources.stock_url("https://example.com/stq_20261015.pdf")

    def test_ignores_unpublished_stock_rows(self):
        data = json.dumps({"TableDatas": [{"TradeDate": "20261016", "Stocks": "-"}]})
        self.assertEqual(sources.json_stock_links(data, "202610"), {})

    def test_takes_only_requested_latest_days_and_deduplicates(self):
        documents = {
            sources.MONTHS_URL: json.dumps({"TableDatas": [{"Month": "202610"}]}),
            sources.FEED + "tsedaily_report_202610.json": feed(["20261001", "20261015", "20261014", "20261015"]),
        }
        links = sources.discover_daily_links(documents.__getitem__, days=2)
        self.assertEqual([day for day, _ in links], ["20261014", "20261015"])
