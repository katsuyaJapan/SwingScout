import importlib.util
import unittest
import sys
import tempfile
from unittest.mock import patch
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build-jpx-snapshot.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("build_jpx_snapshot", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
parse_day = MODULE.parse_day


class JpxSnapshotTest(unittest.TestCase):
    def test_daily_ohlcv_columns(self):
        line = "1333 100 Ｕｍｉｏｓ 1,302.50 1,310.00 1,297.00 1,301.50 1,302.50 1,314.00 1,301.50 1,311.00 － 9.50 1,307.5257 670.3 876,434.450"
        row = parse_day(line, "https://example.test/stq_20260821.pdf")[0]
        self.assertEqual(row[0:3], ("20260821", "1333", "Ｕｍｉｏｓ"))
        self.assertEqual(row[3:7], (1302.5, 1314.0, 1297.0, 1311.0))
        self.assertEqual(row[7:], (670300, 876434450))

    def test_daily_ex_rights_marker(self):
        line = "1407 D 100 ウエストＨＤ 2,723.00 2,785.00 2,684.00 2,743.00 2,739.00 2,770.00 2,730.00 2,760.00 － 33.00 2,741.3780 372.5 1,021,163.300"
        row = parse_day(line, "https://example.test/stq_20260828.pdf")[0]
        self.assertEqual(row[0:3], ("20260828", "1407", "ウエストＨＤ"))
        self.assertEqual(row[3:7], (2723.0, 2785.0, 2684.0, 2760.0))
        self.assertEqual(row[7:], (372500, 1021163300))

    def test_preferred_share_does_not_overwrite_ordinary_share(self):
        tail = "100 name 1 2 1 2 1 2 1 2 － 1 2 10 20"
        rows = parse_day("2593 " + tail + "\n25935 " + tail,
                         "https://example.test/stq_20261015.pdf")
        self.assertEqual([row[1] for row in rows], ["2593", "25935"])

    def test_alphanumeric_code_is_preserved(self):
        rows = parse_day("285A 100 name 1 2 1 2 1 2 1 2 － 1 2 10 20",
                         "https://example.test/stq_20261015.pdf")
        self.assertEqual(rows[0][1], "285A")

    def test_failed_download_preserves_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "snapshot.json"
            target.write_text("last-good")
            with patch.object(MODULE, "OUT", target), patch.object(MODULE, "discover_daily_links", return_value=[
                ("20261015", "https://www.jpx.co.jp/stq_20261015.pdf")
            ]), patch.object(MODULE, "load", side_effect=RuntimeError("download failed")):
                with self.assertRaisesRegex(RuntimeError, "history incomplete"):
                    MODULE.main()
            self.assertEqual(target.read_text(), "last-good")

    def test_invalid_day_or_duplicate_codes_preserves_snapshot(self):
        url = "https://www.jpx.co.jp/stq_20261015.pdf"
        for wrong_day, duplicate in ((True, False), (False, True)):
            with self.subTest(wrong_day=wrong_day, duplicate=duplicate), tempfile.TemporaryDirectory() as directory:
                target = Path(directory) / "snapshot.json"
                target.write_text("last-good")
                rows = [("20261014" if wrong_day else "20261015", "1000" if duplicate else str(1000+i),
                         "name", 1, 2, 1, 2, 100, 200) for i in range(1000)]
                with patch.object(MODULE, "OUT", target), patch.object(MODULE, "discover_daily_links", return_value=[
                    ("20261015", url)
                ]), patch.object(MODULE, "load", return_value=(url, rows)):
                    with self.assertRaisesRegex(RuntimeError, "history incomplete"):
                        MODULE.main()
                self.assertEqual(target.read_text(), "last-good")


if __name__ == "__main__":
    unittest.main()
