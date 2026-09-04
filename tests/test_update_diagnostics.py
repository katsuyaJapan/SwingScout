import json
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("generate_static_data", SCRIPTS / "generate-static-data.py")
static_data = importlib.util.module_from_spec(spec)
spec.loader.exec_module(static_data)


class UpdateDiagnosticsTest(unittest.TestCase):
    def test_auxiliary_failure_does_not_fail_price_gate(self):
        seed = {
            "asOf": "20260903", "latestCoverage": 3900, "historyReady": 3800, "failures": [],
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


if __name__ == "__main__":
    unittest.main()
