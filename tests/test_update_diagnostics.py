import json
import datetime as dt
import importlib.util
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
import copy

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

    def test_retains_healthy_provisional_snapshot_but_rejects_quality_failures(self):
        seed = {
            "asOf": "20261029", "sectorOutflowAsOf": "2026-10-29",
            "latestCoverage": 4152, "historyReady": 4021, "failures": [],
            "technicalCandidates": [],
            "supplementalQuotes": {"1332": {"date": "20261030", "close": 1000}},
            "earningsQuality": {"secondaryCoverage": 30, "secondaryTotal": 30},
            "rightsQuality": {"jpxRows": 150, "secondaryCoverage": 30,
                              "disclosureCoverage": 30, "secondaryTotal": 30},
        }
        previous = {"asOf": "20261030", "officialAsOf": "20261029",
                    "priceStatus": "PROVISIONAL", "status": "READY",
                    "quality": {"pricePassed": True}, "finalCandidates": []}
        status = {"dataAsOf": "20261030", "lastSuccessfulAt": "original-success"}
        history = {"currentAsOf": "20261030", "history": [{"asOf": "20261030", "candidates": []}]}
        cases = ("healthy", "coverage", "snapshot", "sector", "unhealthy_previous", "history_mismatch", "stale", "quotes_outage")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                data = Path(directory)
                trial = copy.deepcopy(seed)
                old = copy.deepcopy(previous)
                old_history = copy.deepcopy(history)
                if case == "coverage": trial["latestCoverage"] = 100
                if case == "snapshot": trial["failures"] = ["download"]
                if case == "sector": trial["sectorOutflowAsOf"] = "2026-10-28"
                if case == "quotes_outage": trial["supplementalQuotes"] = {"1332": None}
                if case == "unhealthy_previous": old["quality"]["pricePassed"] = False
                if case == "history_mismatch": old_history["currentAsOf"] = "20261029"
                for name, payload in (("latest", old), ("history", old_history), ("status", status)):
                    (data / (name + ".json")).write_text(json.dumps(payload))
                before = [(data / (name + ".json")).read_bytes() for name in ("latest", "history")]
                with patch.multiple(static_data, SEED=trial, DATA=data,
                                    LATEST_PATH=data / "latest.json", HISTORY_PATH=data / "history.json",
                                    STATUS_PATH=data / "status.json", DIAGNOSTICS_PATH=data / "diagnostic.json",
                                    market_regime=lambda: {}), \
                     patch.object(static_data, "data_age", return_value={"isStale": case == "stale"}):
                    if case == "healthy":
                        static_data.main()
                        result = json.loads((data / "status.json").read_text())
                        self.assertEqual(result["lastAttemptStatus"], "waiting")
                        self.assertEqual(result["dataAsOf"], "20261030")
                        self.assertEqual(result["lastSuccessfulAt"], "original-success")
                        self.assertIn("lastAttemptAt", result)
                        diagnostic = json.loads((data / "diagnostic.json").read_text())
                        self.assertEqual(diagnostic["failure_reasons"], [])
                        self.assertFalse(diagnostic["checks"]["no_date_regression"])
                    else:
                        with self.assertRaises(RuntimeError): static_data.main()
                self.assertEqual(before, [(data / (name + ".json")).read_bytes() for name in ("latest", "history")])

    def test_supplemental_prices_respect_session_close_and_midnight(self):
        seed = {"asOf": "20261029", "supplementalDate": "20261030",
                "technicalCandidates": [{"code": "1332"}],
                "supplementalQuotes": {"1332": {"date": "20261030", "close": 1000}}}
        jst = dt.timezone(dt.timedelta(hours=9))
        self.assertFalse(static_data.supplemental_complete(seed, dt.datetime(2026, 10, 30, 10, tzinfo=jst)))
        self.assertTrue(static_data.supplemental_complete(seed, dt.datetime(2026, 10, 30, 15, 30, tzinfo=jst)))
        self.assertTrue(static_data.supplemental_complete(seed, dt.datetime(2026, 10, 31, 0, 5, tzinfo=jst)))
        for close in (0, -1, float("nan"), float("inf"), None):
            seed["supplementalQuotes"]["1332"]["close"] = close
            self.assertFalse(static_data.supplemental_complete(seed, dt.datetime(2026, 10, 31, tzinfo=jst)))
        seed["supplementalQuotes"]["1332"] = {"date": "20261102", "close": 1000}
        seed["supplementalDate"] = "20261102"
        self.assertFalse(static_data.supplemental_complete(seed, dt.datetime(2026, 10, 31, tzinfo=jst)))

    def test_same_day_official_prices_replace_provisional_snapshot(self):
        seed = {"asOf": "20261030", "sectorOutflowAsOf": "2026-10-30",
                "latestCoverage": 4152, "historyReady": 4021, "failures": [],
                "earningsQuality": {"secondaryCoverage": 30, "secondaryTotal": 30},
                "rightsQuality": {"jpxRows": 150, "secondaryCoverage": 30,
                                  "disclosureCoverage": 30, "secondaryTotal": 30}}
        with tempfile.TemporaryDirectory() as directory:
            data = Path(directory)
            (data / "latest.json").write_text(json.dumps({"asOf": "20261030", "priceStatus": "PROVISIONAL"}))
            (data / "history.json").write_text(json.dumps({"currentAsOf": "20261030", "history": [
                {"asOf": "20261030", "candidates": []}]}))
            (data / "sector-data.json").write_text("{}")
            with patch.multiple(static_data, SEED=seed, SNAPSHOT={"securities": []}, DATA=data,
                                LATEST_PATH=data / "latest.json", HISTORY_PATH=data / "history.json",
                                STATUS_PATH=data / "status.json", DIAGNOSTICS_PATH=data / "diagnostic.json",
                                market_regime=lambda: {"level": "NORMAL"}):
                static_data.main()
            latest = json.loads((data / "latest.json").read_text())
            self.assertEqual(latest["asOf"], "20261030")
            self.assertEqual(latest["priceStatus"], "JPX_CONFIRMED")
            self.assertEqual(json.loads((data / "status.json").read_text())["lastAttemptStatus"], "success")
            history = json.loads((data / "history.json").read_text())
            self.assertEqual(len(history["history"]), 1)

    def test_missing_rights_source_marks_candidate_unconfirmed(self):
        row = {"score": 60, "riskFlags": [], "rightsCheckedSources": ["JPX"]}
        result = static_data.apply_swing_risk(row, "20261015")
        self.assertIn("RIGHTS_UNCONFIRMED", result["riskFlags"])
        row["rightsCheckedSources"] += ["Yahoo!ファイナンス株主優待", "TDnet掲載一覧"]
        result = static_data.apply_swing_risk(row, "20261015")
        self.assertNotIn("RIGHTS_UNCONFIRMED", result["riskFlags"])


if __name__ == "__main__":
    unittest.main()
