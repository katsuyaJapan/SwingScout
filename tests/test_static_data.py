import json
import unittest
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "public" / "data"


class StaticDataTest(unittest.TestCase):
    def test_latest_contract(self):
        latest = json.loads((DATA / "latest.json").read_text())
        self.assertRegex(latest["asOf"], r"^\d{8}$")
        self.assertLessEqual(len(latest["finalCandidates"]), 3)
        sectors = [row.get("sector") for row in latest["finalCandidates"]]
        self.assertEqual(len(sectors), len(set(sectors)))
        for row in latest["finalCandidates"]:
            self.assertFalse(set(row.get("riskFlags", [])) & {
                "EARNINGS_WITHIN_3_DAYS", "EARNINGS_DATE_UNDECIDED",
                "EARNINGS_DATE_CONFLICT", "EARNINGS_UNCONFIRMED",
                "EX_RIGHTS_WITHIN_3_DAYS", "RIGHTS_DATE_CONFLICT",
                "RIGHTS_RECENT_DISCLOSURE", "LOW_LIQUIDITY",
                "ENTRY_RISK_TOO_WIDE", "RISK_REWARD_LOW",
            })
            self.assertLessEqual(row["targetPrice1"], row["targetPrice2"])
            if "relativeVolume" in row:
                self.assertGreaterEqual(row["relativeVolume"], 0)
                self.assertIn(row["volumeSignal"], {"GREEN", "YELLOW", "RED"})
                self.assertGreaterEqual(row["closeLocation"], 0)
                self.assertLessEqual(row["closeLocation"], 1)

    def test_status_and_history_contract(self):
        status = json.loads((DATA / "status.json").read_text())
        history = json.loads((DATA / "history.json").read_text())
        self.assertIn(status["lastAttemptStatus"], {"success", "failed"})
        self.assertLessEqual(len(history["history"]), 30)


if __name__ == "__main__":
    unittest.main()
