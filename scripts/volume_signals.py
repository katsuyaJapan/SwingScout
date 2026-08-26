#!/usr/bin/env python3
"""Early supply-demand signals for SwingScout.

The module deliberately avoids breakout requirements. A 20-session median is
the baseline, while the three-session price structure is the primary guard
against misclassifying a weak downtrend as selling exhaustion.
"""
from statistics import median


def _avg(values):
    return sum(values) / len(values) if values else 0.0


def _clamp(value, low, high):
    return max(low, min(high, value))


def relative_volume_value(volumes, index=-1):
    """Return volume / preceding-20-session median, excluding the target day."""
    target = index if index >= 0 else len(volumes) + index
    if target < 20 or target >= len(volumes) or volumes[target] is None:
        return None
    baseline_values = [value for value in volumes[target - 20:target] if value is not None]
    if len(baseline_values) < 20:
        return None
    baseline = median(baseline_values)
    return volumes[target] / baseline if baseline > 0 else 1.0


def close_location_value(close, high, low):
    """Return the close position in the daily range (0=low, 1=high)."""
    if close is None or high is None or low is None or high <= low:
        return 0.5
    return _clamp((close - low) / (high - low), 0.0, 1.0)


def low_trend_3d_value(lows):
    """Classify the latest three-session low trend with a tolerant -1% floor."""
    if not lows or len(lows) < 3 or any(value is None for value in lows[-3:]):
        return {"value": None, "signal": "UNKNOWN", "label": "安値不明"}
    first, middle, latest = lows[-3:]
    change = (latest / first - 1) * 100 if first else 0.0
    rising_steps = sum(curr >= prev * 1.002 for prev, curr in ((first, middle), (middle, latest)))
    falling_steps = sum(curr < prev * .995 for prev, curr in ((first, middle), (middle, latest)))
    if change >= .3 and rising_steps >= 1:
        signal, label = "RISING", "安値切り上げ"
    elif change >= -1.0 and falling_steps < 2:
        signal, label = "FLAT", "安値横ばい"
    else:
        signal, label = "FALLING", "安値切り下げ"
    return {"value": round(change, 3), "signal": signal, "label": label}


def price_hold_evaluation(closes, lows, ma25):
    """Evaluate whether price is holding instead of merely falling on low volume."""
    if len(closes) < 6 or not lows or len(lows) < 3:
        return {"signal": "UNKNOWN", "label": "価格維持不明", "score": 2.0}
    usable_lows = [low if low is not None else close for low, close in zip(lows[-3:], closes[-3:])]
    low_trend = low_trend_3d_value(usable_lows)
    daily_return = (closes[-1] / closes[-2] - 1) * 100 if closes[-2] else 0.0
    return5 = (closes[-1] / closes[-6] - 1) * 100 if closes[-6] else 0.0
    prior_low = min(usable_lows[:-1])
    checks = [
        low_trend["signal"] != "FALLING",
        usable_lows[-1] >= prior_low * .99,
        ma25 > 0 and closes[-1] >= ma25 * .97,
        daily_return >= -1.2,
        return5 >= -5.0,
    ]
    passed = sum(checks)
    if passed >= 4:
        signal, label, score = "STRONG", "価格維持", 3.0
    elif passed >= 3:
        signal, label, score = "WEAK", "価格維持弱め", 1.5
    else:
        signal, label, score = "NONE", "価格崩れ", 0.0
    return {"signal": signal, "label": label, "score": score}


def _neutral_result():
    return {
        "relativeVolume": None, "relativeVolumePrev": None,
        "volumeSignal": "YELLOW", "volumePhase": "INSUFFICIENT_DATA",
        "volumeSupplyDemand": "判断材料不足", "volumeSupplyDemandLabel": "🟡 判断材料不足",
        "closeLocation": 0.5, "lowTrend3d": None, "lowTrend3dSignal": "UNKNOWN",
        "lowTrend3dLabel": "安値不明", "priceHoldSignal": "UNKNOWN",
        "priceHoldLabel": "価格維持不明", "volumeScore": 6.0,
        "priceHoldScore": 1.5, "closeLocationScore": 1.0,
        "dailyReturn": None, "overheatSuppressed": False,
    }


def analyze_volume_supply_demand(closes, volumes, highs=None, lows=None, ma25=None):
    """Evaluate 1-day, 3-day and 20-day supply-demand layers safely."""
    if len(closes) < 22 or len(volumes) < 22:
        return _neutral_result()
    if any(value is None for value in closes[-22:] + volumes[-22:]):
        return _neutral_result()

    highs = list(highs or [])
    lows = list(lows or [])
    aligned_lows = [low if low is not None else close for low, close in zip(lows[-3:], closes[-3:])] if len(lows) >= 3 else closes[-3:]
    relative_volume = relative_volume_value(volumes)
    relative_volume_prev = relative_volume_value(volumes, -2)
    if relative_volume is None:
        return _neutral_result()
    relative_volume_prev = relative_volume_prev if relative_volume_prev is not None else 1.0

    daily_return = (closes[-1] / closes[-2] - 1) * 100 if closes[-2] else 0.0
    return5 = (closes[-1] / closes[-6] - 1) * 100 if closes[-6] else 0.0
    ma25 = ma25 or _avg(closes[-25:])
    deviation25 = (closes[-1] / ma25 - 1) * 100 if ma25 else 0.0
    latest_high = highs[-1] if highs else None
    latest_low = lows[-1] if lows else None
    clv = close_location_value(closes[-1], latest_high, latest_low)
    low_trend = low_trend_3d_value(aligned_lows)
    price_hold = price_hold_evaluation(closes, aligned_lows, ma25)

    accumulation_days = 0
    distribution_days = 0
    for offset in range(-3, 0):
        move = (closes[offset] / closes[offset - 1] - 1) * 100 if closes[offset - 1] else 0.0
        session_rvol = relative_volume_value(volumes, offset)
        session_rvol = session_rvol if session_rvol is not None else 1.0
        if move >= .3 and session_rvol >= 1.1:
            accumulation_days += 1
        elif move <= -.3 and session_rvol >= 1.2:
            distribution_days += 1

    baseline = median(volumes[-21:-1])
    prior5_average = _avg(volumes[-6:-1])
    prior3_average = _avg(volumes[-4:-1])
    volume_bottomed = volumes[-1] >= volumes[-2] * 1.08 and volumes[-1] >= prior3_average * 1.03
    rvol_recovering = relative_volume > relative_volume_prev * 1.03
    structure_points = sum([
        price_hold["signal"] in ("STRONG", "WEAK"),
        low_trend["signal"] in ("RISING", "FLAT"),
        ma25 > 0 and closes[-1] >= ma25 * .97,
        daily_return >= -.2 or low_trend["signal"] == "RISING",
    ])
    dry_up_reacceleration = prior5_average < baseline * .90 and volume_bottomed and rvol_recovering and structure_points >= 3

    overheat = return5 >= 5.0 or deviation25 >= 6.0 or relative_volume >= 3.0
    signal, phase, label, score = "YELLOW", "NORMAL", "出来高通常", 6.5
    sustained_price_break = low_trend["signal"] == "FALLING" and price_hold["signal"] == "NONE"

    if distribution_days >= 2:
        signal, phase, label, score = "RED", "DISTRIBUTION", "売り圧力が継続", 1.0
    elif daily_return < -.3 and relative_volume >= 1.5:
        if price_hold["signal"] == "STRONG" and low_trend["signal"] != "FALLING":
            signal, phase, label, score = "YELLOW", "ONE_DAY_SELLING", "下落出来高増・3日維持", 3.5
        else:
            signal, phase, label, score = "RED", "SELLING_PRESSURE", "下落時に出来高増", 1.5
    elif sustained_price_break and relative_volume < .7 and clv < .3:
        signal, phase, label, score = "RED", "FALLING_ON_LOW_VOLUME", "安値切り下げ継続", 2.0
    elif dry_up_reacceleration:
        signal, phase, label, score = "GREEN", "DRY_UP_REACCELERATION", "売り枯れ→出来高再増加", 11.5
    elif low_trend["signal"] == "RISING" and rvol_recovering and price_hold["signal"] == "STRONG":
        signal, phase, label, score = "GREEN", "LOW_RISING_RECOVERY", "安値切り上げ＋出来高回復", 10.0
    elif daily_return > .3 and relative_volume >= 1.2:
        signal, phase, label, score = "GREEN", "BUYING_DEMAND", "上昇＋出来高増", 9.5
    elif daily_return < -.3 and relative_volume < .7:
        if price_hold["signal"] == "STRONG" and low_trend["signal"] != "FALLING":
            signal, phase, label, score = "GREEN", "SELLING_EXHAUSTION", "価格維持＋出来高減", 7.0
        elif sustained_price_break:
            signal, phase, label, score = "RED", "FALLING_ON_LOW_VOLUME", "出来高減でも価格崩れ", 2.5
        else:
            phase, label, score = "LOW_VOLUME_WEAK_HOLD", "出来高減・維持判定弱い", 4.5
    elif daily_return < -.3 and relative_volume >= 1.2:
        phase, label, score = "SELLING_CAUTION", "下落時に出来高やや増", 4.0
    elif daily_return > .3 and relative_volume < .7:
        phase, label, score = "WEAK_RISE", "上昇も出来高減", 5.5
    elif relative_volume < .7:
        if price_hold["signal"] == "STRONG" and low_trend["signal"] != "FALLING":
            signal, phase, label, score = "GREEN", "DRYING_UP", "価格維持＋出来高減", 7.0
        elif sustained_price_break:
            signal, phase, label, score = "RED", "FALLING_ON_LOW_VOLUME", "出来高減でも価格崩れ", 2.5
        else:
            phase, label, score = "LOW_VOLUME_NEUTRAL", "出来高減・需給確認中", 5.0
    elif daily_return > 0:
        phase, label, score = "EARLY_ACCUMULATION", "緩やかな買い需要", 7.5

    score += min(1.5, accumulation_days * .75) - min(1.5, distribution_days * .75)
    if overheat and score > 6:
        score = min(score - 3.0, 7.0)
        if signal == "GREEN":
            signal, phase, label = "YELLOW", "OVERHEATED_DEMAND", "需給改善も初動後"
    score = _clamp(score, 0.0, 12.0)

    close_location_score = .4 + 1.6 * clv
    if clv < .3 and price_hold["signal"] == "STRONG":
        close_location_score = max(close_location_score, .9)
    icon = {"GREEN": "🟢", "YELLOW": "🟡", "RED": "🔴"}[signal]
    return {
        "relativeVolume": round(relative_volume, 3), "relativeVolumePrev": round(relative_volume_prev, 3),
        "volumeSignal": signal, "volumePhase": phase, "volumeSupplyDemand": label,
        "volumeSupplyDemandLabel": f"{icon} {label}", "closeLocation": round(clv, 3),
        "lowTrend3d": low_trend["value"], "lowTrend3dSignal": low_trend["signal"],
        "lowTrend3dLabel": low_trend["label"], "priceHoldSignal": price_hold["signal"],
        "priceHoldLabel": price_hold["label"], "volumeScore": round(score, 3),
        "priceHoldScore": round(price_hold["score"], 3), "closeLocationScore": round(close_location_score, 3),
        "dailyReturn": round(daily_return, 3), "overheatSuppressed": overheat,
    }
