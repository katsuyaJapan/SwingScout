import sys
import unittest
from pathlib import Path
from statistics import median

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from volume_signals import (
    analyze_volume_supply_demand,
    close_location_value,
    low_trend_3d_value,
    price_hold_evaluation,
    relative_volume_value,
)


def series(latest_close=100.0, latest_volume=1000, latest_low=99.0, latest_high=101.0):
    closes = [100.0] * 21 + [latest_close]
    volumes = [1000] * 21 + [latest_volume]
    lows = [99.0] * 21 + [latest_low]
    highs = [101.0] * 21 + [latest_high]
    return closes, volumes, highs, lows


class VolumeSignalsTest(unittest.TestCase):
    def test_relative_volume_uses_preceding_median(self):
        volumes = [100] * 10 + [200] * 10 + [300]
        self.assertEqual(median(volumes[-21:-1]), 150)
        self.assertEqual(relative_volume_value(volumes), 2.0)

    def test_close_location_and_flat_range_fallback(self):
        self.assertEqual(close_location_value(109, 110, 100), .9)
        self.assertEqual(close_location_value(100, 100, 100), .5)

    def test_low_trend_3d(self):
        self.assertEqual(low_trend_3d_value([98, 99, 100])["signal"], "RISING")
        self.assertEqual(low_trend_3d_value([100, 99.7, 99.4])["signal"], "FLAT")
        self.assertEqual(low_trend_3d_value([100, 98.8, 97.5])["signal"], "FALLING")

    def test_price_hold_requires_stable_lows_and_ma25(self):
        closes = [100.0] * 22
        self.assertEqual(price_hold_evaluation(closes, [99, 99.2, 99.1], 100)["signal"], "STRONG")
        falling = [100.0] * 19 + [99, 97.5, 96]
        self.assertEqual(price_hold_evaluation(falling, [98.5, 97, 95.5], 100)["signal"], "NONE")

    def test_down_on_heavy_volume_is_penalized(self):
        closes, volumes, highs, lows = series(97, 1800, 96, 100)
        result = analyze_volume_supply_demand(closes, volumes, highs, lows, 100)
        self.assertEqual(result["volumeSignal"], "RED")
        self.assertEqual(result["volumePhase"], "SELLING_PRESSURE")
        self.assertLessEqual(result["volumeScore"], 2)

    def test_down_low_volume_with_price_hold_is_exhaustion(self):
        closes, volumes, highs, lows = series(99.5, 600, 99, 101)
        result = analyze_volume_supply_demand(closes, volumes, highs, lows, 100)
        self.assertEqual(result["priceHoldSignal"], "STRONG")
        self.assertEqual(result["volumeSignal"], "GREEN")
        self.assertEqual(result["volumePhase"], "SELLING_EXHAUSTION")

    def test_down_low_volume_with_falling_lows_is_not_exhaustion(self):
        closes = [100.0] * 19 + [99, 98, 96.2]
        volumes = [1000] * 21 + [600]
        highs = [101.0] * 19 + [100, 99, 98]
        lows = [99.0] * 19 + [98.5, 97.2, 96]
        result = analyze_volume_supply_demand(closes, volumes, highs, lows, 100)
        self.assertEqual(result["lowTrend3dSignal"], "FALLING")
        self.assertEqual(result["volumeSignal"], "RED")
        self.assertEqual(result["volumePhase"], "FALLING_ON_LOW_VOLUME")

    def test_dry_up_then_reacceleration_requires_price_structure(self):
        closes = [100.0] * 25
        volumes = [1000] * 19 + [800, 760, 700, 650, 750, 900]
        lows = [99.0] * 22 + [98.9, 99.0, 99.2]
        result = analyze_volume_supply_demand(closes, volumes, [101] * 25, lows, 100)
        self.assertEqual(result["volumeSignal"], "GREEN")
        self.assertEqual(result["volumePhase"], "DRY_UP_REACCELERATION")
        self.assertGreater(result["relativeVolume"], result["relativeVolumePrev"])
        self.assertGreaterEqual(result["volumeScore"], 11)

    def test_high_rvol_is_not_required_for_reacceleration(self):
        closes = [100.0] * 25
        volumes = [1000] * 19 + [800, 760, 700, 650, 750, 900]
        result = analyze_volume_supply_demand(closes, volumes, [101] * 25, [99] * 25, 100)
        self.assertLess(result["relativeVolume"], 1.5)
        self.assertEqual(result["volumePhase"], "DRY_UP_REACCELERATION")

    def test_overheated_rise_is_suppressed(self):
        closes = [100.0] * 16 + [101, 102, 103, 104, 105, 106]
        volumes = [1000] * 21 + [1500]
        result = analyze_volume_supply_demand(closes, volumes, [x * 1.01 for x in closes], [x * .99 for x in closes], 100)
        self.assertTrue(result["overheatSuppressed"])
        self.assertEqual(result["volumeSignal"], "YELLOW")
        self.assertLessEqual(result["volumeScore"], 7)

    def test_insufficient_data_falls_back_to_neutral(self):
        result = analyze_volume_supply_demand([100] * 10, [1000] * 10)
        self.assertEqual(result["volumeSignal"], "YELLOW")
        self.assertEqual(result["volumePhase"], "INSUFFICIENT_DATA")
        self.assertIsNone(result["relativeVolume"])


if __name__ == "__main__":
    unittest.main()
