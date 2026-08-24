import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from rights_sources import parse_recent_rights_disclosures, parse_yahoo_incentive_dates


class RightsSourcesTest(unittest.TestCase):
    def test_yahoo_incentive_exact_dates(self):
        page = """
        <table><tr><th>権利付き最終日</th>
        <td>2026年8月27日、2027年2月24日</td></tr></table>
        """
        events = parse_yahoo_incentive_dates(page, "20260820")
        self.assertEqual(events[0], {
            "rightsExitDeadline": "20260827",
            "exRightsDate": "20260828",
            "rightsRecordDate": "20260831",
        })
        self.assertEqual(len(events), 2)

    def test_past_incentive_date_is_ignored(self):
        page = "権利付き最終日 2026年2月25日"
        self.assertEqual(parse_yahoo_incentive_dates(page, "20260820"), [])

    def test_recent_tdnet_rights_change_is_flagged(self):
        page = "株主優待制度の変更に関するお知らせ 8/14 15:30 TDnet PDF"
        titles = parse_recent_rights_disclosures(page, "20260820")
        self.assertEqual(titles, ["株主優待制度の変更"])

    def test_old_tdnet_rights_change_is_not_flagged(self):
        page = "株主優待制度の変更に関するお知らせ 6/1 15:30 TDnet PDF"
        self.assertEqual(parse_recent_rights_disclosures(page, "20260820"), [])


if __name__ == "__main__":
    unittest.main()
