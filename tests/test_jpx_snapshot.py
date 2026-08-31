import importlib.util
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build-jpx-snapshot.py"
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


if __name__ == "__main__":
    unittest.main()
