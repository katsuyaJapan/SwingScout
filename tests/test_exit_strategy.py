import copy
import unittest

from scripts.exit_strategy import evaluate_exit_strategy, neutral_exit


def market_data(close=100.0):
    closes = [close + (i % 3) * .1 for i in range(40)]
    lows = [x - 1 for x in closes]
    highs = [x + 1 for x in closes]
    volumes = [1000] * 40
    benchmark = [100 + i * .05 for i in range(40)]
    return closes, lows, highs, volumes, benchmark


def evaluate(**changes):
    closes, lows, highs, volumes, benchmark = market_data()
    values = dict(closes=closes, lows=lows, highs=highs, volumes=volumes,
                  entry_price=100, target_price=115, stop_price=92,
                  holding_days=5, topix=benchmark, sector=benchmark)
    values.update(changes)
    return evaluate_exit_strategy(**values)


class ExitStrategyV1Test(unittest.TestCase):
    def test_price_breakdown_and_three_day_low(self):
        closes, lows, highs, volumes, benchmark = market_data()
        closes[-3:] = [99, 97.5, 95]
        lows[-4:] = [99, 98, 96.5, 94]
        result = evaluate(closes=closes, lows=lows, highs=highs, volumes=volumes,
                          topix=benchmark, sector=benchmark)
        self.assertEqual(result["price_breakdown_signal"], "CLEAR")
        self.assertIn("3日安値を明確割れ", result["exit_reasons"])

    def test_ma25_downward_deviation(self):
        closes, lows, highs, volumes, benchmark = market_data(105)
        closes[-3:] = [101, 99, 97]
        lows[-3:] = [100, 98, 96]
        result = evaluate(closes=closes, lows=lows, highs=highs, volumes=volumes,
                          topix=benchmark, sector=benchmark)
        self.assertLess(result["ma25_deviation_pct"], -2)

    def test_relative_volume_exit_bands_and_single_day_guard(self):
        closes, lows, highs, volumes, benchmark = market_data()
        closes[-1] = 98
        lows[-1], highs[-1], volumes[-1] = 97.5, 101, 1600
        result = evaluate(closes=closes, lows=lows, highs=highs, volumes=volumes,
                          topix=benchmark, sector=benchmark)
        self.assertEqual(result["relative_volume_exit"], 1.6)
        self.assertNotEqual(result["exit_status"], "EXIT_CANDIDATE")

    def test_down_day_volume_bias(self):
        closes, lows, highs, volumes, benchmark = market_data()
        closes[-6:] = [100, 102, 101, 103, 101, 100]
        volumes[-5:] = [800, 1400, 800, 1500, 1600]
        result = evaluate(closes=closes, lows=lows, highs=highs, volumes=volumes,
                          topix=benchmark, sector=benchmark)
        self.assertGreater(result["down_up_volume_ratio_5d"], 1.2)

    def test_topix_relative_strength(self):
        closes, lows, highs, volumes, benchmark = market_data()
        closes[-2:] = [100, 97]
        benchmark[-2:] = [100, 101]
        result = evaluate(closes=closes, lows=lows, highs=highs, volumes=volumes,
                          topix=benchmark, sector=[])
        self.assertLess(result["relative_strength_topix_1d"], -3)
        self.assertEqual(result["relative_strength_health"], "BAD")

    def test_sector_priority_and_topix_fallback(self):
        base = evaluate(sector=[])
        self.assertEqual(base["relative_strength_source"], "TOPIX")
        self.assertEqual(evaluate()["relative_strength_source"], "SECTOR")

    def test_market_crash_relief(self):
        closes, lows, highs, volumes, benchmark = market_data()
        closes[-2:] = [100, 97.8]
        lows[-4:] = [100, 99, 98.5, 97]
        volumes[-1] = 1500
        benchmark[-2:] = [100, 97]
        normal = evaluate(closes=closes, lows=lows, highs=highs, volumes=volumes,
                          topix=[100] * 40, sector=[])
        crash = evaluate(closes=closes, lows=lows, highs=highs, volumes=volumes,
                         topix=benchmark, sector=[])
        ranks = {"HOLD": 0, "CAUTION": 1, "PREPARE_EXIT": 2, "EXIT_CANDIDATE": 3}
        self.assertLessEqual(ranks[crash["exit_status"]], ranks[normal["exit_status"]])

    def test_two_consecutive_and_two_of_three_weak_days(self):
        closes, lows, highs, volumes, benchmark = market_data()
        closes[-4:] = [103, 101, 102, 99]
        volumes[-3:] = [1300, 800, 1400]
        two_of_three = evaluate(closes=closes, lows=lows, highs=highs, volumes=volumes,
                                topix=benchmark, sector=benchmark)
        self.assertEqual(two_of_three["weak_signal_days_3d"], 2)
        closes[-3:] = [103, 101, 99]
        volumes[-2:] = [1300, 1400]
        consecutive = evaluate(closes=closes, lows=lows, highs=highs, volumes=volumes,
                               topix=benchmark, sector=benchmark)
        self.assertEqual(consecutive["consecutive_weak_days"], 2)

    def test_entry_minus_seven_only_does_not_force_red(self):
        closes, lows, highs, volumes, benchmark = market_data()
        closes[-1], lows[-1], volumes[-1] = 93, 92.5, 500
        result = evaluate(closes=closes, lows=lows, highs=highs, volumes=volumes,
                          topix=benchmark, sector=benchmark, stop_price=80)
        self.assertTrue(result["hard_stop_reached"])
        self.assertTrue(result["hard_stop_triggered"])
        self.assertFalse(result["swing_stop_triggered"])
        self.assertEqual(result["hard_stop_status"], "HARD_STOP_TRIGGERED")
        self.assertEqual(result["hard_stop_reason"], "ハードストップ水準到達")
        self.assertNotEqual(result["exit_status"], "EXIT_CANDIDATE")

    def test_swing_stop_has_stronger_independent_warning(self):
        closes, lows, highs, volumes, benchmark = market_data()
        closes[-1], lows[-1] = 94, 93.5
        result = evaluate(closes=closes, lows=lows, highs=highs, volumes=volumes,
                          topix=benchmark, sector=benchmark, stop_price=95)
        self.assertTrue(result["swing_stop_triggered"])
        self.assertFalse(result["hard_stop_triggered"])
        self.assertEqual(result["hard_stop_status"], "SWING_STOP_TRIGGERED")
        self.assertEqual(result["hard_stop_reason"], "損切りライン到達")

    def test_normal_red_requires_price_volume_and_persistence(self):
        closes, lows, highs, volumes, benchmark = market_data()
        closes[-4:] = [105, 102, 98, 94]
        lows[-4:] = [104, 101, 97, 92]
        highs[-4:] = [106, 104, 100, 96]
        volumes[-3:] = [1400, 1500, 1600]
        result = evaluate(closes=closes, lows=lows, highs=highs, volumes=volumes,
                          topix=benchmark, sector=benchmark, stop_price=80)
        self.assertEqual(result["price_breakdown_signal"], "CLEAR")
        self.assertEqual(result["volume_exit_signal"], "SELLING_PRESSURE")
        self.assertGreaterEqual(result["weak_signal_days_3d"], 2)
        self.assertEqual(result["exit_status"], "EXIT_CANDIDATE")

    def test_market_crash_keeps_hard_stop_warning_separate(self):
        closes, lows, highs, volumes, benchmark = market_data()
        closes[-2:] = [100, 93]
        lows[-1], volumes[-1] = 92.5, 500
        benchmark[-2:] = [100, 90]
        result = evaluate(closes=closes, lows=lows, highs=highs, volumes=volumes,
                          topix=benchmark, sector=[], stop_price=80)
        self.assertTrue(result["hard_stop_triggered"])
        self.assertGreater(result["relative_strength_topix_1d"], 0)
        self.assertNotEqual(result["exit_status"], "EXIT_CANDIDATE")

    def test_stop_warning_does_not_change_score_profit_or_time_logic(self):
        closes, lows, highs, volumes, benchmark = market_data()
        closes[-1], lows[-1] = 94, 93.5
        triggered = evaluate(closes=closes, lows=lows, highs=highs, volumes=volumes,
                             topix=benchmark, sector=benchmark, stop_price=95)
        clear = evaluate(closes=closes, lows=lows, highs=highs, volumes=volumes,
                         topix=benchmark, sector=benchmark, stop_price=80)
        self.assertEqual(triggered["exit_risk_score"], clear["exit_risk_score"])
        self.assertEqual(triggered["profit_protection_signal"], clear["profit_protection_signal"])
        self.assertEqual(triggered["time_exit_signal"], clear["time_exit_signal"])

    def test_target_reached(self):
        closes, lows, highs, volumes, benchmark = market_data()
        closes[-1], highs[-1] = 116, 117
        result = evaluate(closes=closes, lows=lows, highs=highs, volumes=volumes,
                          topix=benchmark, sector=benchmark)
        self.assertEqual(result["exit_status"], "TARGET_REACHED")

    def test_max_profit_drawdown_and_profit_protection(self):
        closes, lows, highs, volumes, benchmark = market_data()
        highs[-7:] = [101, 103, 106, 110, 108, 106, 105]
        closes[-4:] = [108, 106, 104, 103]
        lows[-4:] = [107, 105, 103, 102]
        volumes[-3:] = [1400, 1500, 1600]
        result = evaluate(closes=closes, lows=lows, highs=highs, volumes=volumes,
                          topix=benchmark, sector=benchmark, holding_days=6)
        self.assertEqual(result["highest_price_since_entry"], 110)
        self.assertEqual(result["max_profit_pct"], 10)
        self.assertLessEqual(result["drawdown_from_high_pct"], -6)
        self.assertIn(result["profit_protection_signal"], {"CAUTION", "PREPARE"})

    def test_holding_period_relief(self):
        older = evaluate(holding_days=5)
        early = evaluate(holding_days=1)
        ranks = {"HOLD": 0, "CAUTION": 1, "PREPARE_EXIT": 2, "EXIT_CANDIDATE": 3}
        self.assertLessEqual(ranks[early["exit_status"]], ranks[older["exit_status"]])

    def test_time_exit_warning(self):
        closes, lows, highs, volumes, benchmark = market_data()
        volumes[-1] = 600
        closes[-1] = 99.5
        result = evaluate(closes=closes, lows=lows, highs=highs, volumes=volumes,
                          topix=benchmark, sector=benchmark, holding_days=8)
        self.assertTrue(result["time_exit_signal"])

    def test_missing_data_neutral_fallback(self):
        result = evaluate_exit_strategy(closes=[100] * 5, lows=[99] * 5, highs=[101] * 5,
                                        volumes=[1000] * 5, entry_price=100)
        self.assertEqual(result["exit_status"], "HOLD")
        self.assertEqual(result["exit_reasons"], ["判断材料不足"])

    def test_existing_json_is_additive(self):
        existing = {"code": "0000", "name": "互換性", "close": 100, "custom": {"kept": True}}
        original = copy.deepcopy(existing)
        existing.update(neutral_exit(100, 110, 93, 0))
        for key, value in original.items():
            self.assertEqual(existing[key], value)


if __name__ == "__main__":
    unittest.main()
