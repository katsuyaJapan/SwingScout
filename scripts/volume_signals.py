#!/usr/bin/env python3
"""Volume/price supply-demand signals used by SwingScout.

The functions in this module are intentionally pure so the daily build and the
historical comparison tool use exactly the same calculation.
"""
from statistics import median


def _avg(values):
    return sum(values) / len(values) if values else 0.0


def _clamp(value, low, high):
    return max(low, min(high, value))


def close_location_value(close, high, low):
    """Return the close position in the daily range (0=low, 1=high)."""
    if close is None or high is None or low is None or high <= low:
        return 0.5
    return _clamp((close - low) / (high - low), 0.0, 1.0)


def analyze_volume_supply_demand(closes, volumes, highs=None, lows=None, ma25=None):
    """Evaluate early supply-demand improvement without requiring a breakout.

    Relative volume compares the latest session with the *preceding* 20-session
    median.  The latest observation is deliberately excluded from the baseline.
    """
    if len(closes) < 6 or len(volumes) < 21:
        return {
            "relativeVolume": None,
            "volumeSignal": "YELLOW",
            "volumePhase": "INSUFFICIENT_DATA",
            "volumeSupplyDemand": "判断材料不足",
            "closeLocation": 0.5,
            "volumeScore": 6.0,
            "closeLocationScore": 1.5,
            "dailyReturn": None,
        }

    baseline = median(volumes[-21:-1])
    relative_volume = volumes[-1] / baseline if baseline > 0 else 1.0
    daily_return = (closes[-1] / closes[-2] - 1) * 100 if closes[-2] else 0.0
    return5 = (closes[-1] / closes[-6] - 1) * 100 if closes[-6] else 0.0
    latest_high = highs[-1] if highs and len(highs) else None
    latest_low = lows[-1] if lows and len(lows) else None
    clv = close_location_value(closes[-1], latest_high, latest_low)
    ma25 = ma25 or (_avg(closes[-25:]) if len(closes) >= 25 else _avg(closes))

    # Look at the three latest sessions so a single noisy day cannot dominate.
    accumulation_days = 0
    distribution_days = 0
    for offset in range(-3, 0):
        previous = closes[offset - 1]
        if not previous:
            continue
        move = (closes[offset] / previous - 1) * 100
        session_rvol = volumes[offset] / baseline if baseline > 0 else 1.0
        if move >= 0.3 and session_rvol >= 1.1:
            accumulation_days += 1
        elif move <= -0.3 and session_rvol >= 1.2:
            distribution_days += 1

    prior5_average = _avg(volumes[-6:-1])
    prior3_average = _avg(volumes[-4:-1])
    near_ma25 = ma25 > 0 and closes[-1] >= ma25 * 0.97
    price_stable = abs(return5) <= 5.0 and min(closes[-5:]) >= ma25 * 0.94
    volume_bottomed = (
        volumes[-1] >= volumes[-2] * 1.10
        and volumes[-1] >= prior3_average * 1.05
        and volumes[-2] <= max(volumes[-4:-1])
    )
    dry_up_reacceleration = (
        prior5_average < baseline * 0.90
        and volume_bottomed
        and near_ma25
        and price_stable
    )

    signal = "YELLOW"
    phase = "NORMAL"
    label = "出来高通常"
    score = 7.0

    if daily_return < -0.3 and relative_volume >= 1.5:
        signal, phase, label, score = "RED", "SELLING_PRESSURE", "下落時に出来高増", 1.0
    elif distribution_days >= 2 and relative_volume >= 1.2:
        signal, phase, label, score = "RED", "DISTRIBUTION", "売り圧力が継続", 2.0
    elif dry_up_reacceleration:
        signal, phase, label, score = "GREEN", "DRY_UP_REACCELERATION", "売り枯れ→再増加", 13.0
    elif daily_return > 0.3 and relative_volume >= 1.2:
        signal, phase, label, score = "GREEN", "BUYING_DEMAND", "上昇＋出来高増", 10.5
    elif daily_return < -0.3 and relative_volume < 0.7 and price_stable:
        signal, phase, label, score = "GREEN", "SELLING_EXHAUSTION", "下落＋出来高減", 8.5
    elif daily_return < -0.3 and relative_volume >= 1.2:
        signal, phase, label, score = "YELLOW", "SELLING_CAUTION", "下落時に出来高やや増", 4.0
    elif daily_return > 0.3 and relative_volume < 0.7:
        phase, label, score = "WEAK_RISE", "上昇も出来高減", 6.0
    elif relative_volume < 0.7 and price_stable:
        phase, label, score = "DRYING_UP", "出来高枯れを監視", 8.0
    elif daily_return > 0:
        phase, label, score = "EARLY_ACCUMULATION", "緩やかな買い需要", 8.0

    # Recent accumulation/distribution only nudges the phase score by two points.
    score += min(2, accumulation_days) - min(2, distribution_days)
    score = _clamp(score, 0.0, 14.0)
    close_location_score = 0.5 + 2.5 * clv  # Low-weight, never a hard filter.
    return {
        "relativeVolume": round(relative_volume, 3),
        "volumeSignal": signal,
        "volumePhase": phase,
        "volumeSupplyDemand": label,
        "closeLocation": round(clv, 3),
        "volumeScore": round(score, 3),
        "closeLocationScore": round(close_location_score, 3),
        "dailyReturn": round(daily_return, 3),
    }
