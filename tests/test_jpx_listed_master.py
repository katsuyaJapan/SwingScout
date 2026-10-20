import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import jpx_listed_master as master


class ListedMasterTest(unittest.TestCase):
    def workbook(self, count=3000, headers=None, duplicate=False):
        book = openpyxl.Workbook()
        sheet = book.active
        sheet.append(headers or list(master.REQUIRED_COLUMNS))
        for number in range(count):
            code = "130A" if number == 0 else ("25935" if number == 1 else str(1000 + number))
            if duplicate:
                code = "130A"
            sheet.append([20260930, code, "水産・農林業", "プライム（内国株式）"])
        output = io.BytesIO()
        book.save(output)
        book.close()
        return output.getvalue()

    def test_discovers_current_relative_xlsx(self):
        url = master.discover_url('<a href="./new-id/data_j.xlsx?version=2">Excel</a>')
        self.assertEqual(url, "https://www.jpx.co.jp/markets/statistics-equities/misc/new-id/data_j.xlsx?version=2")

    def test_rejects_missing_ambiguous_and_external_links(self):
        for html in ('<a href="/other.xls">x</a>',
                     '<a href="https://example.com/data_j.xlsx">x</a>',
                     '<a href="/a/data_j.xlsx">x</a><a href="/b/data_j.xls">x</a>'):
            with self.subTest(html=html), self.assertRaises(master.MasterError):
                master.discover_url(html)

    def test_reads_xlsx_and_preserves_alphanumeric_code(self):
        rows, date = master.parse_master(self.workbook(), "https://www.jpx.co.jp/data_j.xlsx")
        self.assertEqual(len(rows), 3000)
        self.assertEqual(date, "20260930")
        self.assertIn("25935", rows)
        self.assertEqual(rows["130A"], ("水産・農林業", "プライム（内国株式）"))

    def test_rejects_invalid_content_missing_columns_short_and_duplicate_data(self):
        for data in (b'<html>Error</html>', self.workbook(count=1),
                     self.workbook(headers=["invalid"] * 4), self.workbook(duplicate=True)):
            with self.subTest(size=len(data)), self.assertRaises(master.MasterError):
                master.parse_master(data, "https://www.jpx.co.jp/data_j.xlsx")

    def test_download_error_identifies_url_and_status(self):
        from urllib.error import HTTPError
        url = "https://www.jpx.co.jp/data_j.xlsx"
        with patch.object(master, "urlopen", side_effect=HTTPError(url, 404, "Not Found", {}, None)):
            with self.assertRaisesRegex(master.MasterError, "url=.*data_j.xlsx.*404"):
                master.download(url)

    def test_legacy_xls_uses_xlrd(self):
        from unittest.mock import Mock
        sheet = Mock(nrows=3001)
        sheet.row_values.side_effect = [list(master.REQUIRED_COLUMNS)] + [
            [20260930.0, float(1000 + i), "水産・農林業", "プライム（内国株式）"] for i in range(3000)
        ]
        book = Mock()
        book.sheet_by_index.return_value = sheet
        with patch.object(master.xlrd, "open_workbook", return_value=book):
            rows, date = master.parse_master(b"xls", "https://www.jpx.co.jp/data_j.xls")
        self.assertIn("1000", rows)
        self.assertEqual(date, "20260930")

    def test_delisted_or_missing_latest_quote_is_not_a_candidate(self):
        listed = {"1332": ("水産・農林業", "プライム（内国株式）")}
        current = {"code": "1332", "c": [100, 101], "v": [1000, 1000], "t": [100000, 101000]}
        self.assertTrue(master.has_current_listing_and_price(current, listed))
        self.assertFalse(master.has_current_listing_and_price({**current, "code": "5202"}, listed))
        self.assertFalse(master.has_current_listing_and_price({**current, "c": [100, None]}, listed))


if __name__ == "__main__":
    unittest.main()
