import json
import datetime as dt
import importlib.util
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("generate_static_data", SCRIPTS / "generate-static-data.py")
static_data = importlib.util.module_from_spec(spec)
# These unit tests exercise explicit seed arguments, not generated local inputs.
original_read_text = Path.read_text

def read_test_input(path, *args, **kwargs):
    if path.name == "analysis-seed.json":
        return "{}"
    return original_read_text(path, *args, **kwargs)

with patch.object(Path, "read_text", read_test_input):
    spec.loader.exec_module(static_data)


class UpdateDiagnosticsTest(unittest.TestCase):
    def test_auxiliary_failure_does_not_fail_price_gate(self):
        seed = {
            "asOf": "20260903", "sectorOutflowAsOf": "2026-09-03", "latestCoverage": 3900, "historyReady": 3800, "failures": [],
            "earningsQuality": {"secondaryCoverage": 2, "secondaryTotal": 10},
            "rightsQuality": {"jpxRows": 40, "secondaryCoverage": 2, "disclosureCoverage": 2, "secondaryTotal": 10},
        }
        result = static_data.quality_diagnostics(seed, "20260903", False)
        self.assertTrue(all(result["checks"][key] for key in ("snapshot_failures", "price_coverage", "history_ready", "price_date")))
        self.assertIn("earnings_coverage", result["failure_reasons"])
        self.assertIn("rights_coverage", result["failure_reasons"])

    def test_price_failure_is_reported(self):
        seed = {"asOf": "20260903", "latestCoverage": 100, "historyReady": 100, "failures": ["download"], "earningsQuality": {}, "rightsQuality": {}}
        result = static_data.quality_diagnostics(seed, "20260902", False)
        self.assertEqual(result["failure_stage"], "quality_gate")
        self.assertIn("price_coverage", result["failure_reasons"])
        self.assertIn("price_date", result["failure_reasons"])

    def test_old_sector_data_blocks_core_gate(self):
        seed = {"asOf": "20261015", "sectorOutflowAsOf": "2026-09-30", "latestCoverage": 4193,
                "historyReady": 4097, "failures": []}
        result = static_data.quality_diagnostics(seed, "20261015", False)
        self.assertFalse(result["checks"]["sector_date"])
        self.assertIn("sector_date", result["failure_reasons"])

    def test_old_or_incomplete_supplemental_quotes_cannot_replace_official_prices(self):
        seed = {"asOf": "20261015", "supplementalDate": "20260930", "technicalCandidates": [{"code": "1332"}],
                "supplementalQuotes": {"1332": {"date": "20260930", "close": 1000}}}
        now = dt.datetime(2026, 10, 18)
        self.assertFalse(static_data.supplemental_complete(seed, now))
        seed["supplementalDate"] = "20261016"
        seed["supplementalQuotes"]["1332"]["date"] = "20261016"
        self.assertTrue(static_data.supplemental_complete(seed, now))
        seed["technicalCandidates"].append({"code": "1333"})
        self.assertFalse(static_data.supplemental_complete(seed, now))

    def test_previous_published_date_cannot_move_backwards(self):
        seed = {"asOf": "20261015", "sectorOutflowAsOf": "2026-10-15", "latestCoverage": 4193,
                "historyReady": 4097, "failures": []}
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            latest = data / "latest.json"
            latest.write_text(json.dumps({"asOf": "20261016"}))
            before = latest.read_text()
            with patch.multiple(static_data, SEED=seed, DATA=data, LATEST_PATH=latest,
                                HISTORY_PATH=data / "history.json", DIAGNOSTICS_PATH=data / "diagnostic.json",
                                market_regime=lambda: {}):
                with self.assertRaises(RuntimeError):
                    static_data.main()
            self.assertEqual(latest.read_text(), before)
            diagnostic = json.loads((data / "diagnostic.json").read_text())
            self.assertIn("no_date_regression", diagnostic["failure_reasons"])

    def test_missing_rights_source_marks_candidate_unconfirmed(self):
        row = {"score": 60, "riskFlags": [], "rightsCheckedSources": ["JPX"]}
        result = static_data.apply_swing_risk(row, "20261015")
        self.assertIn("RIGHTS_UNCONFIRMED", result["riskFlags"])
        row["rightsCheckedSources"] += ["Yahoo!ファイナンス株主優待", "TDnet掲載一覧"]
        result = static_data.apply_swing_risk(row, "20261015")
        self.assertNotIn("RIGHTS_UNCONFIRMED", result["riskFlags"])


if __name__ == "__main__":
    unittest.main()
