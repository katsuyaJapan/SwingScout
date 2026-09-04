#!/usr/bin/env python3
"""SwingScout exit strategy v1.

The exit signal is intentionally additive and advisory.  It combines price
structure, volume, relative strength and persistence; a one-day decline alone
cannot produce a red exit candidate (except when the hard stop is reached).
"""
from __future__ import annotations

from statistics import mean, median


def _pct(current, previous):
    return (current / previous - 1) * 100 if current is not None and previous else None


def _return(series, days):
    usable = [x for x in series if x is not None]
    return _pct(usable[-1], usable[-1 - days]) if len(usable) > days else None


def _relative(stock, benchmark, days):
    stock_return, benchmark_return = _return(stock, days), _return(benchmark, days)
    return None if stock_return is None or benchmark_return is None else stock_return - benchmark_return


def _rvol(volumes, index=-1):
    target = index if index >= 0 else len(volumes) + index
    if target < 20 or target >= len(volumes) or volumes[target] is None:
        return None
    baseline = [x for x in volumes[target - 20:target] if x is not None]
    if len(baseline) < 20:
        return None
    base = median(baseline)
    return volumes[target] / base if base else None


def _volume_bias(closes, volumes):
    rising, falling = [], []
    start = max(1, len(closes) - 5)
    for index in range(start, len(closes)):
        if closes[index] is None or closes[index - 1] is None or volumes[index] is None:
            continue
        (falling if closes[index] < closes[index - 1] else rising).append(volumes[index])
    if not rising or not falling:
        return None
    return mean(falling) / mean(rising) if mean(rising) else None


def _step_down(status):
    order = ["HOLD", "CAUTION", "PREPARE_EXIT", "EXIT_CANDIDATE"]
    return order[max(0, order.index(status) - 1)] if status in order else status


def neutral_exit(entry_price=None, target_price=None, stop_price=None, holding_days=0):
    return {
        "entry_price": entry_price, "target_price": target_price, "stop_price": stop_price,
        "hard_stop_price": None, "hard_stop_reached": False, "holding_days": holding_days,
        "hard_stop_status": "NOT_TRIGGERED", "hard_stop_reason": None,
        "hard_stop_triggered": False, "swing_stop_triggered": False,
        "highest_price_since_entry": None, "max_profit_pct": None, "drawdown_from_high_pct": None,
        "price_breakdown_signal": "NEUTRAL", "volume_exit_signal": "NEUTRAL",
        "down_up_volume_ratio_5d": None, "relative_strength_topix_1d": None,
        "relative_strength_topix_3d": None, "relative_strength_topix_5d": None,
        "relative_strength_sector": None, "relative_strength_source": "NONE",
        "ma25_deviation_pct": None, "relative_volume_exit": None, "clv_exit": None,
        "weak_signal_days_3d": 0, "consecutive_weak_days": 0, "profit_protection_signal": "NONE",
        "time_exit_signal": False, "exit_risk_score": 0, "exit_status": "HOLD",
        "exit_reasons": ["判断材料不足"], "price_health": "NEUTRAL",
        "volume_health": "NEUTRAL", "relative_strength_health": "NEUTRAL",
    }


def evaluate_exit_strategy(*, closes, lows, highs, volumes, entry_price, target_price=None,
                           stop_price=None, holding_days=0, topix=None, sector=None):
    """Return additive JSON fields for one held security."""
    result = neutral_exit(entry_price, target_price, stop_price, holding_days)
    arrays = (closes, lows, highs, volumes)
    if any(len(x) < 26 for x in arrays) or any(x is None for series in arrays for x in series[-6:]):
        return result

    current = closes[-1]
    hard_stop = entry_price * .93 if entry_price else None
    highest = max(highs[-max(1, holding_days + 1):]) if holding_days else current
    max_profit = _pct(highest, entry_price)
    drawdown = _pct(current, highest)
    ma25 = mean(closes[-25:])
    ma_dev = _pct(current, ma25)
    prior_3d_low = min(lows[-4:-1])
    low_break_pct = _pct(lows[-1], prior_3d_low)
    lower_low_steps = sum(lows[i] < lows[i - 1] for i in range(len(lows) - 2, len(lows)))
    clv = .5 if highs[-1] <= lows[-1] else max(0, min(1, (current - lows[-1]) / (highs[-1] - lows[-1])))
    rvol = _rvol(volumes)
    volume_ratio = _volume_bias(closes, volumes)

    price_score = 0
    if low_break_pct < 0:
        price_score += 10
    if low_break_pct <= -1:
        price_score += 10
    if ma_dev < 0:
        price_score += 5
    if ma_dev <= -2:
        price_score += 5
    if lower_low_steps >= 2:
        price_score += 5
    price_score = min(35, price_score)
    clear_price_break = low_break_pct <= -1 or (ma_dev <= -2 and lower_low_steps >= 2)
    weak_price_break = price_score > 0

    down_today = current < closes[-2]
    volume_score = 0
    if down_today and rvol is not None:
        volume_score += 15 if rvol >= 1.5 else 10 if rvol >= 1.2 else 0
    if volume_ratio is not None and volume_ratio > 1.2:
        volume_score += 10
    distribution_days = 0
    weak_days = []
    for index in range(len(closes) - 3, len(closes)):
        session_rvol = _rvol(volumes, index)
        weak = closes[index] < closes[index - 1] and (session_rvol or 0) >= 1.2
        weak_days.append(weak)
        distribution_days += int(weak)
    if distribution_days >= 2:
        volume_score += 5
    volume_score = min(30, volume_score)
    volume_bad = volume_score >= 10

    topix = list(topix or [])
    sector = list(sector or [])
    rs_topix = {days: _relative(closes, topix, days) for days in (1, 3, 5)}
    rs_sector_5d = _relative(closes, sector, 5)
    relative_source = "SECTOR" if rs_sector_5d is not None else "TOPIX" if rs_topix[5] is not None else "NONE"
    primary_relatives = ([rs_sector_5d] if rs_sector_5d is not None else list(rs_topix.values()))
    relative_score = min(20, 5 * sum(x is not None and x <= -1 for x in primary_relatives) +
                         5 * sum(x is not None and x <= -2 for x in primary_relatives))
    relative_bad = any(x is not None and x <= -1 for x in primary_relatives)
    clv_score = 10 if clv < .2 else 5 if clv < .35 else 0
    persistence_score = 5 if distribution_days >= 2 or (len(weak_days) >= 2 and sum(weak_days) >= 2) else 0
    score = min(100, price_score + volume_score + relative_score + clv_score + persistence_score)

    hard_stop_triggered = bool(hard_stop and current <= hard_stop)
    swing_stop_triggered = bool(stop_price and current <= stop_price)
    hard_stop_reached = hard_stop_triggered or swing_stop_triggered
    if swing_stop_triggered:
        hard_stop_status, hard_stop_reason = "SWING_STOP_TRIGGERED", "損切りライン到達"
    elif hard_stop_triggered:
        hard_stop_status, hard_stop_reason = "HARD_STOP_TRIGGERED", "ハードストップ水準到達"
    else:
        hard_stop_status, hard_stop_reason = "NOT_TRIGGERED", None
    target_reached = bool(target_price and current >= target_price)
    persistence = distribution_days >= 2 or sum(weak_days) >= 2
    if score >= 70 and clear_price_break and volume_bad and persistence:
        status = "EXIT_CANDIDATE"
    elif score >= 50:
        status = "PREPARE_EXIT"
    elif score >= 30 or weak_price_break or volume_bad or relative_bad:
        status = "CAUTION"
    else:
        status = "HOLD"
    topix_1d = _return(topix, 1)
    market_relatively_ok = rs_topix[1] is None or rs_topix[1] >= -1
    if topix_1d is not None and topix_1d <= -2 and market_relatively_ok:
        status = _step_down(status)
    if holding_days <= 2:
        status = _step_down(status)

    profit_protection = "NONE"
    if max_profit is not None and max_profit >= 5 and drawdown is not None and drawdown <= -3 and weak_price_break:
        profit_protection = "PREPARE" if volume_bad else "CAUTION"
        if profit_protection == "PREPARE" and status == "CAUTION":
            status = "PREPARE_EXIT"
    no_reacceleration = rvol is None or rvol < 1.0
    no_relative_improvement = rs_topix[5] is None or rs_topix[5] <= 0
    time_exit = holding_days >= 7 and current <= entry_price * 1.01 and no_reacceleration and no_relative_improvement

    reasons = []
    if low_break_pct <= -1:
        reasons.append("3日安値を明確割れ")
    elif ma_dev < 0:
        reasons.append("25日線割れ")
    if down_today and rvol is not None and rvol >= 1.2:
        reasons.append(f"下落RVOL {rvol:.1f}")
    elif volume_ratio is not None and volume_ratio > 1.2:
        reasons.append("売り日出来高優勢")
    elif relative_bad:
        reasons.append("相対強度悪化")
    if not reasons:
        reasons = ["価格維持", "相対強度良好"]

    labels = {"HOLD": "HOLD", "CAUTION": "CAUTION", "PREPARE_EXIT": "PREPARE_EXIT", "EXIT_CANDIDATE": "EXIT_CANDIDATE"}
    result.update({
        "hard_stop_price": round(hard_stop, 2) if hard_stop else None,
        "hard_stop_reached": hard_stop_reached, "hard_stop_status": hard_stop_status,
        "hard_stop_reason": hard_stop_reason, "hard_stop_triggered": hard_stop_triggered,
        "swing_stop_triggered": swing_stop_triggered, "highest_price_since_entry": round(highest, 2),
        "max_profit_pct": round(max_profit, 2) if max_profit is not None else None,
        "drawdown_from_high_pct": round(drawdown, 2) if drawdown is not None else None,
        "price_breakdown_signal": "CLEAR" if clear_price_break else "WEAK" if weak_price_break else "NONE",
        "volume_exit_signal": "SELLING_PRESSURE" if volume_bad else "NEUTRAL",
        "down_up_volume_ratio_5d": round(volume_ratio, 2) if volume_ratio is not None else None,
        "relative_strength_topix_1d": round(rs_topix[1], 2) if rs_topix[1] is not None else None,
        "relative_strength_topix_3d": round(rs_topix[3], 2) if rs_topix[3] is not None else None,
        "relative_strength_topix_5d": round(rs_topix[5], 2) if rs_topix[5] is not None else None,
        "relative_strength_sector": round(rs_sector_5d, 2) if rs_sector_5d is not None else None,
        "relative_strength_source": relative_source, "ma25_deviation_pct": round(ma_dev, 2),
        "relative_volume_exit": round(rvol, 2) if rvol is not None else None, "clv_exit": round(clv, 2),
        "weak_signal_days_3d": sum(weak_days),
        "consecutive_weak_days": 2 if weak_days[-2:] == [True, True] else 1 if weak_days[-1] else 0,
        "profit_protection_signal": profit_protection, "time_exit_signal": time_exit,
        "exit_risk_score": round(score), "exit_status": "TARGET_REACHED" if target_reached else labels[status],
        "exit_reasons": ["目標株価到達", "利確検討"] if target_reached else reasons[:2],
        "price_health": "BAD" if clear_price_break else "CAUTION" if weak_price_break else "GOOD",
        "volume_health": "BAD" if volume_bad else "GOOD" if down_today and (rvol or 1) < .7 else "NEUTRAL",
        "relative_strength_health": "BAD" if relative_bad else "GOOD" if any(x is not None and x > 0 for x in primary_relatives) else "NEUTRAL",
    })
    return result
