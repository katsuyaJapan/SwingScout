import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from volume_signals import analyze_volume_supply_demand, close_location_value


class VolumeSignalsTest(unittest.TestCase):
    def test_close_location(self):
        self.assertEqual(close_location_value(109, 110, 100), .9)
        self.assertEqual(close_location_value(100, 100, 100), .5)

    def test_down_on_heavy_volume_is_red(self):
        closes = [100.0] * 21 + [97.0]
        volumes = [1000] * 21 + [1800]
        result = analyze_volume_supply_demand(closes, volumes, [101] * 21 + [100], [99] * 21 + [96], 100)
        self.assertEqual(result["volumeSignal"], "RED")
        self.assertEqual(result["volumePhase"], "SELLING_PRESSURE")
        self.assertLessEqual(result["volumeScore"], 2)

    def test_down_on_low_volume_can_be_selling_exhaustion(self):
        closes = [100.0] * 21 + [99.5]
        volumes = [1000] * 21 + [600]
        result = analyze_volume_supply_demand(closes, volumes, [101] * 22, [99] * 22, 100)
        self.assertEqual(result["volumeSignal"], "GREEN")
        self.assertEqual(result["volumePhase"], "SELLING_EXHAUSTION")

    def test_dry_up_then_reacceleration_has_priority(self):
        closes = [100.0] * 25
        volumes = [1000] * 19 + [800, 760, 700, 650, 750, 900]
        result = analyze_volume_supply_demand(closes, volumes, [101] * 25, [99] * 25, 100)
        self.assertEqual(result["volumeSignal"], "GREEN")
        self.assertEqual(result["volumePhase"], "DRY_UP_REACCELERATION")
        self.assertGreaterEqual(result["volumeScore"], 12)

    def test_high_rvol_is_not_required(self):
        closes = [100.0] * 25
        volumes = [1000] * 19 + [800, 760, 700, 650, 750, 900]
        result = analyze_volume_supply_demand(closes, volumes, [101] * 25, [99] * 25, 100)
        self.assertLess(result["relativeVolume"], 1.5)
        self.assertEqual(result["volumePhase"], "DRY_UP_REACCELERATION")


if __name__ == "__main__":
    unittest.main()
