#!/usr/bin/env python3
"""Compare the legacy and new volume scores over recent JPX sessions.

This checks the technical stage only. Earnings, ex-rights and recent-selection
filters run later and are unchanged by the volume-signal migration.
"""
import json
import math
import tempfile
import urllib.request
from pathlib import Path

import xlrd

from volume_signals import analyze_volume_supply_demand

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = json.loads((ROOT / "public/data/jpx-snapshot.json").read_text())


def avg(values):
    return sum(values) / len(values) if values else 0.0


def rsi(values, period=14):
    window = values[-(period + 1):]
    gains = sum(max(0, window[i] - window[i - 1]) for i in range(1, len(window)))
    losses = sum(max(0, window[i - 1] - window[i]) for i in range(1, len(window)))
    return 100 if losses == 0 else 100 - 100 / (1 + gains / losses)


def triangle(value, center, half_width, maximum):
    return max(0.0, maximum * (1 - abs(value - center) / half_width))


def load_master():
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    with tempfile.NamedTemporaryFile(suffix=".xls") as handle:
        handle.write(urllib.request.urlopen(url, timeout=30).read())
        handle.flush()
        sheet = xlrd.open_workbook(handle.name).sheet_by_index(0)
        headers = [str(sheet.cell_value(0, i)).strip() for i in range(sheet.ncols)]
        code_col, sector_col, market_col = (headers.index(x) for x in ("コード", "33業種区分", "市場・商品区分"))
        return {
            str(sheet.cell_value(row, code_col)).split(".")[0].zfill(4): (
                str(sheet.cell_value(row, sector_col)).strip(),
                str(sheet.cell_value(row, market_col)).strip(),
            )
            for row in range(1, sheet.nrows)
        }


def universe_at(index, master):
    universe = []
    for security in SNAPSHOT["securities"]:
        rows = list(zip(
            security["c"][:index + 1], security["v"][:index + 1], security["t"][:index + 1],
            security.get("h", [None] * len(security["c"]))[:index + 1],
            security.get("l", [None] * len(security["c"]))[:index + 1],
        ))
        rows = [row for row in rows if row[0] is not None and row[1] is not None and row[2] is not None][-250:]
        if len(rows) < 200:
            continue
        closes = [row[0] for row in rows]
        volumes = [row[1] for row in rows]
        turnovers = [row[2] for row in rows]
        highs = [row[3] for row in rows]
        lows = [row[4] for row in rows]
        turnover20 = turnovers[-20:]
        avg_turnover = avg(turnover20)
        if avg_turnover < 300_000_000 or sum(x >= 100_000_000 for x in turnover20) < 15:
            continue
        sector, market = master.get(security["code"], ("その他製品", "未分類"))
        if any(word in market for word in ("ETF", "REIT", "ファンド")):
            continue
        close = closes[-1]
        ma5, ma25 = avg(closes[-5:]), avg(closes[-25:])
        signal = analyze_volume_supply_demand(closes, volumes, highs, lows, ma25)
        universe.append({
            "code": security["code"], "name": security["name"], "sector": sector,
            "close": close, "c": closes, "v": volumes, "ma5": ma5, "ma25": ma25,
            "high20": max(closes[-20:]), "low10": min(closes[-10:]), "rsi": rsi(closes),
            "ret5": (close / closes[-6] - 1) * 100, "ret20": (close / closes[-21] - 1) * 100,
            "d25": (close / ma25 - 1) * 100, "legacyVolumeRatio": avg(volumes[-5:]) / avg(volumes[-20:]),
            "avgTurnover": avg_turnover, **signal,
        })
    return universe


def sector_scores(universe):
    groups = {}
    for stock in universe:
        groups.setdefault(stock["sector"], []).append(stock)
    result = {}
    for name, stocks in groups.items():
        ret5 = avg([x["ret5"] for x in stocks])
        ret20 = avg([x["ret20"] for x in stocks])
        breadth = 100 * sum(x["close"] > x["ma25"] for x in stocks) / len(stocks)
        prior = 100 * sum(x["c"][-6] > avg(x["c"][-30:-5]) for x in stocks) / len(stocks)
        acceleration = ret5 - ret20 / 4
        raw_score = 45 + acceleration * 3 + (breadth - prior) * .35
        sample_factor = min(1, len(stocks) / 12)
        result[name] = max(0, min(100, 50 + (raw_score - 50) * sample_factor))
    return result


def rank(universe, use_new):
    sectors = sector_scores(universe)
    rows = []
    for stock in universe:
        deviation = triangle(stock["d25"], 1.5, 5.0, 17.0)
        momentum = triangle(stock["rsi"], 51.0, 17.0, 15.0)
        volume = stock["volumeScore"] if use_new else triangle(stock["legacyVolumeRatio"], 1.18, .65, 14.0)
        price_hold = stock["priceHoldScore"] if use_new else 0.0
        close_position = stock["closeLocationScore"] if use_new else 0.0
        headroom = (stock["high20"] / stock["close"] - 1) * 100
        headroom_score = triangle(headroom, 6.0, 7.0, 9.0)
        trend = max(0, min(6, 3 + (stock["ma5"] / stock["ma25"] - 1) * 100 * 1.5))
        risk_width = max(0, (stock["close"] / stock["low10"] - 1) * 100)
        risk = max(0, 6 - abs(risk_width - 4) * 1.2)
        liquidity = max(0, min(8, 2 + math.log10(max(stock["avgTurnover"], 1) / 100_000_000) * 3))
        individual = deviation + momentum + volume + price_hold + close_position + headroom_score + trend + risk + liquidity
        penalty = max(0, stock["ret5"] - 5) * 2.5 + max(0, stock["d25"] - 6) * 3 + (12 if stock["rsi"] > 70 else 0) + (8 if stock["close"] >= stock["high20"] and stock["ret5"] > 5 else 0)
        score = max(0, min(100, sectors[stock["sector"]] * .30 + individual - penalty))
        if individual >= 35 and sectors[stock["sector"]] >= 50 and penalty < 15:
            rows.append({**stock, "score": score, "volumeScoreUsed": volume, "priceHoldScoreUsed": price_hold, "closeLocationScoreUsed": close_position})
    rows.sort(key=lambda x: x["score"], reverse=True)
    selected, used = [], set()
    for row in rows:
        if row["sector"] in used:
            continue
        selected.append(row)
        used.add(row["sector"])
        if len(selected) == 3:
            break
    return rows, selected


def compact(row, old_by_code=None, forward=None):
    old = (old_by_code or {}).get(row["code"])
    return {
        "code": row["code"], "name": row["name"], "sector": row["sector"],
        "score": round(row["score"], 2),
        "scoreDelta": None if old is None else round(row["score"] - old["score"], 2),
        "volumeScore": round(row["volumeScoreUsed"], 2),
        "relativeVolume": row["relativeVolume"], "volumeSignal": row["volumeSignal"],
        "relativeVolumePrev": row["relativeVolumePrev"],
        "priceHoldSignal": row["priceHoldSignal"], "lowTrend3d": row["lowTrend3d"],
        "lowTrend3dSignal": row["lowTrend3dSignal"], "volumePhase": row["volumePhase"],
        "volumeSupplyDemand": row["volumeSupplyDemand"], "closeLocation": row["closeLocation"],
        "overheatSuppressed": row["overheatSuppressed"],
        "forwardReturn1d": (forward or {}).get(row["code"], {}).get("return1d"),
        "forwardReturn3d": (forward or {}).get(row["code"], {}).get("return3d"),
    }


def forward_returns(index):
    result = {}
    for security in SNAPSHOT["securities"]:
        selected = security["c"][index]
        if selected is None:
            continue
        record = {}
        for horizon in (1, 3):
            target_index = index + horizon
            if target_index < len(security["c"]) and security["c"][target_index] is not None:
                record[f"return{horizon}d"] = round((security["c"][target_index] / selected - 1) * 100, 2)
        result[security["code"]] = record
    return result


def main():
    master = load_master()
    comparisons = []
    start = max(0, len(SNAPSHOT["dates"]) - 6)
    for index in range(start, len(SNAPSHOT["dates"]) - 1):
        universe = universe_at(index, master)
        old_rows, old_selected = rank(universe, False)
        new_rows, new_selected = rank(universe, True)
        old_by_code = {row["code"]: row for row in old_rows}
        forward = forward_returns(index)
        phase_counts = {}
        for row in new_rows:
            phase_counts[row["volumePhase"]] = phase_counts.get(row["volumePhase"], 0) + 1
        selling_pressure = [row for row in new_rows if row["volumePhase"] in ("SELLING_PRESSURE", "DISTRIBUTION")]
        comparisons.append({
            "date": SNAPSHOT["dates"][index], "universe": len(universe),
            "oldCandidateCount": len(old_rows), "newCandidateCount": len(new_rows),
            "oldCandidates": [compact(row, forward=forward) for row in old_selected],
            "newCandidates": [compact(row, old_by_code, forward) for row in new_selected],
            "validation": {
                "selectedRedCount": sum(row["volumeSignal"] == "RED" for row in new_selected),
                "sellingPressureCandidateCount": len(selling_pressure),
                "maxSellingPressureScore": round(max((row["score"] for row in selling_pressure), default=0), 2),
                "dryUpReaccelerationCandidateCount": phase_counts.get("DRY_UP_REACCELERATION", 0),
                "sellingExhaustionCandidateCount": phase_counts.get("SELLING_EXHAUSTION", 0),
                "fallingLowVolumeMisclassifiedGreen": sum(row["volumeSignal"] == "GREEN" and row["lowTrend3dSignal"] == "FALLING" and (row["relativeVolume"] or 1) < .7 for row in new_rows),
                "overheatedSelectedCount": sum(row["overheatSuppressed"] for row in new_selected),
            },
        })
    print(json.dumps({
        "scope": "technical stage; shared liquidity/sector-diversity filters; earnings/rights/recent-selection filters unchanged",
        "comparisons": comparisons,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
