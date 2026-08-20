#!/usr/bin/env python3
"""Build the immutable JSON read by the static SwingScout frontend."""
from __future__ import annotations

import copy
import datetime as dt
import json
import math
import re
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "public" / "data"
SEED = json.loads((DATA / "analysis-seed.json").read_text())
try:
    SNAPSHOT = json.loads((DATA / "jpx-snapshot.json").read_text())
except (json.JSONDecodeError, FileNotFoundError):
    # 初回移行時の旧スナップショットが壊れていても、最新候補JSONの生成は検証できる。
    # 日次Actionでは先に公式スナップショットを再生成するため、この経路は通常使われない。
    SNAPSHOT = {"securities": []}
HISTORY_PATH = DATA / "history.json"
LATEST_PATH = DATA / "latest.json"
STATUS_PATH = DATA / "status.json"
VERSION = 20
MAX_OPENING_GAP_PCT = 1.0

JPX_HOLIDAYS = {
    "20260101", "20260102", "20260112", "20260211", "20260223", "20260320", "20260429", "20260504", "20260505", "20260506", "20260720", "20260811", "20260921", "20260922", "20260923", "20261012", "20261103", "20261123", "20261231",
    "20270101", "20270111", "20270211", "20270223", "20270322", "20270429", "20270503", "20270504", "20270505", "20270719", "20270811", "20270920", "20270923", "20271011", "20271103", "20271123", "20271231",
}


def dump(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def business_days(start: str, end: str) -> int | None:
    a = dt.datetime.strptime(start, "%Y%m%d").date()
    b = dt.datetime.strptime(end, "%Y%m%d").date()
    if b < a:
        return None
    count = 0
    day = a + dt.timedelta(days=1)
    while day <= b:
        key = day.strftime("%Y%m%d")
        if day.weekday() < 5 and key not in JPX_HOLIDAYS:
            count += 1
        day += dt.timedelta(days=1)
    return count


def tick_size(price: float) -> int:
    return 1 if price < 5000 else 10


def to_tick(price: float, tick: int, up: bool = False) -> int:
    return int((math.ceil(price / tick) if up else math.floor(price / tick)) * tick)


def invalidation_value(label: str) -> float:
    found = re.search(r"[\d,.]+", label or "")
    return float(found.group(0).replace(",", "")) if found else 0


def apply_entry_plan(candidate: dict, previous_high: float | None = None) -> dict:
    row = copy.deepcopy(candidate)
    close = float(row["close"])
    tick = tick_size(close)
    lower = to_tick(close * .998, tick)
    chase_limit = to_tick(close * 1.015, tick, True)
    breakout = to_tick((previous_high + tick) if previous_high else close * 1.003, tick, True)
    upper = min(max(to_tick(close, tick, True), breakout), chase_limit) if row.get("setup") == "初動候補" else to_tick(close * 1.003, tick, True)
    stop = invalidation_value(row.get("invalidation", ""))
    risk = max(0, upper - stop)
    closes = row.get("metrics", {}).get("closes", [])
    window = [float(x) for x in closes[-20:] if x is not None] + [close]
    high20, low20 = max(window), min(window)
    target1 = max(high20, close + (high20 - low20) * .35)
    target2 = max(target1, close + (high20 - low20) * .65)
    risk_pct = risk / upper * 100 if upper else 999
    rr = max(0, (target2 - upper) / risk) if risk else 0
    flags = [x for x in row.get("riskFlags", []) if x not in {"ENTRY_RISK_TOO_WIDE", "RISK_REWARD_LOW", "RISK_REWARD_CAUTION"}]
    if risk_pct > 6:
        flags.append("ENTRY_RISK_TOO_WIDE")
    if rr < 1.2:
        flags.append("RISK_REWARD_LOW")
    elif rr < 1.5:
        flags.append("RISK_REWARD_CAUTION")
    entry_type = "現在値〜前日高値抜け" if row.get("setup") == "初動候補" else "現在値付近"
    max_open = min(to_tick(close * (1 + MAX_OPENING_GAP_PCT / 100), tick), upper)
    row.update({
        "entryLower": lower, "entryUpper": upper, "entryType": entry_type,
        "entry": f"{lower:,}円〜{upper:,}円（{entry_type}）",
        "entryRiskPct": round(risk_pct, 1), "riskReward": round(rr, 2),
        "targetPrice": round(target2), "targetPrice1": round(target1), "targetPrice2": round(target2),
        "maxOpeningPrice": max_open, "maxOpeningGapPct": MAX_OPENING_GAP_PCT,
        "openingRule": f"9:00の寄り付きが{max_open:,}円を超えた場合は見送り", "riskFlags": flags,
    })
    return row


def apply_swing_risk(candidate: dict, as_of: str) -> dict:
    row = copy.deepcopy(candidate)
    earnings_days = business_days(as_of, row["earningsDate"]) if row.get("earningsDate") else None
    rights_days = business_days(as_of, row["exRightsDate"]) if row.get("exRightsDate") else None
    flags = [x for x in row.get("riskFlags", []) if x not in {"EARNINGS_WITHIN_3_DAYS", "EX_RIGHTS_WITHIN_3_DAYS"}]
    if rights_days is not None and rights_days <= 3:
        flags.append("EX_RIGHTS_WITHIN_3_DAYS")
    if earnings_days is not None and earnings_days <= 3:
        flags = [x for x in flags if x != "EARNINGS_UNCONFIRMED"]
        flags.append("EARNINGS_WITHIN_3_DAYS")
        row["score"] = max(0, row["score"] - 15)
    row.update({"earningsDays": earnings_days, "exRightsDays": rights_days, "riskFlags": flags})
    return row


def diversified(candidates: list[dict]) -> list[dict]:
    by_sector: dict[str, dict] = {}
    for row in candidates:
        by_sector.setdefault(row.get("sector", "未分類"), row)
    return sorted(by_sector.values(), key=lambda x: x["score"], reverse=True)[:3]


def market_regime() -> dict:
    sector = json.loads((DATA / "sector-data.json").read_text())
    def returns(series: list[dict]) -> tuple[float | None, float | None]:
        prices = [float(x["close"]) for x in series if x.get("close") is not None]
        one = (prices[-1] / prices[-2] - 1) * 100 if len(prices) >= 2 else None
        five = (prices[-1] / prices[-6] - 1) * 100 if len(prices) >= 6 else None
        return one, five
    topix1, topix5 = returns(sector.get("topix", []))
    nikkei1, nikkei5 = returns(sector.get("nikkei", []))
    weak_day = topix1 is not None and nikkei1 is not None and topix1 <= -.5 and nikkei1 <= -.5
    weak_week = any(x is not None and x <= -2 for x in (topix5, nikkei5))
    level = "CAUTION" if weak_day or weak_week else "NORMAL"
    return {
        "level": level,
        "title": "地合い警戒" if level == "CAUTION" else "地合い通常",
        "message": "指数が弱いため、エントリー下限割れでの逆張りは避け、ポジションを抑えてください。" if level == "CAUTION" else "指数に強い警戒シグナルはありません。個別の無効化ラインを優先してください。",
        "asOf": sector.get("asOf"),
        "topix1d": None if topix1 is None else round(topix1, 2), "topix5d": None if topix5 is None else round(topix5, 2),
        "nikkei1d": None if nikkei1 is None else round(nikkei1, 2), "nikkei5d": None if nikkei5 is None else round(nikkei5, 2),
    }


def main() -> None:
    old_history = json.loads(HISTORY_PATH.read_text()) if HISTORY_PATH.exists() else {"history": []}
    supplemental = SEED.get("supplementalQuotes", {})
    candidate_rows = SEED.get("technicalCandidates", [])
    supplemental_date = SEED.get("supplementalDate", SEED["asOf"])
    quotes_complete = bool(candidate_rows) and all((supplemental.get(x["code"]) or {}).get("date") == supplemental_date for x in candidate_rows)
    effective_date = supplemental_date if quotes_complete else SEED["asOf"]
    refreshed = []
    for candidate in candidate_rows:
        quote = supplemental.get(candidate["code"]) if quotes_complete else None
        row = copy.deepcopy(candidate)
        if quote:
            row.update({"close": quote["close"], "provisional": True, "priceDate": quote["date"]})
        row = apply_entry_plan(row, quote.get("high") if quote else None)
        refreshed.append(apply_swing_risk(row, effective_date))
    refreshed.sort(key=lambda x: x["score"], reverse=True)

    quality = SEED.get("earningsQuality", {})
    earnings_ok = quality.get("secondaryCoverage", 0) >= math.ceil(max(1, quality.get("secondaryTotal", 30)) * .8)
    gate = not SEED.get("failures") and earnings_ok and SEED.get("latestCoverage", 0) >= 3800 and SEED.get("historyReady", 0) >= 3000 and (effective_date == SEED["asOf"] or quotes_complete)
    history_days = sorted(old_history.get("history", []), key=lambda x: x["asOf"], reverse=True)
    recent_codes = {c["code"] for day in history_days[:5] if day.get("asOf", "") < effective_date for c in day.get("candidates", [])}
    hard_flags = {"EARNINGS_WITHIN_3_DAYS", "EARNINGS_DATE_UNDECIDED", "EARNINGS_DATE_CONFLICT", "EARNINGS_UNCONFIRMED", "EX_RIGHTS_WITHIN_3_DAYS", "ENTRY_RISK_TOO_WIDE", "RISK_REWARD_LOW"}
    eligible = [x for x in refreshed if not hard_flags.intersection(x.get("riskFlags", []))]
    continued = [{**x, "lastSelectedDate": next((d["asOf"] for d in history_days if any(c["code"] == x["code"] for c in d.get("candidates", []))), None)} for x in eligible if x["code"] in recent_codes]
    final = diversified([x for x in eligible if x["code"] not in recent_codes]) if gate else []
    generated = dt.datetime.now(dt.timezone.utc).isoformat()
    result = {
        "version": VERSION, "asOf": effective_date, "officialAsOf": SEED["asOf"], "generatedAt": generated, "cached": False,
        "priceStatus": "PROVISIONAL" if effective_date > SEED["asOf"] else "JPX_CONFIRMED",
        "status": "READY" if gate else "ANALYSIS_HELD",
        "message": f"過去5営業日の重複を除外し、仕込み候補を{len(final)}銘柄選定しました。" if gate else "価格日または決算照合の品質条件を満たさないため、前回正常データを維持します。",
        "finalCandidates": final, "continuedCandidates": continued,
        "excludedEarnings": [x for x in refreshed if {"EARNINGS_WITHIN_3_DAYS", "EARNINGS_DATE_UNDECIDED", "EARNINGS_UNCONFIRMED"}.intersection(x.get("riskFlags", []))],
        "sectorSignals": SEED.get("sectorSignals", []), "sectorOutflows": SEED.get("sectorOutflows", []), "sectorOutflowAsOf": SEED.get("sectorOutflowAsOf"),
        "excludedExtended": SEED.get("excludedExtended", []), "technicalCandidates": refreshed if gate else [], "marketRegime": market_regime(),
        "funnel": {"listed": SEED.get("listed", 0), "latestPrice": SEED.get("latestCoverage", 0), "historyReady": SEED.get("historyReady", 0), "liquid": SEED.get("liquid", 0), "primary": SEED.get("primary", 0), "detailReview": min(10, len(eligible)), "final": len(final)},
        "quality": {"passed": gate, "files": SEED.get("files", 0), "failures": len(SEED.get("failures", [])), "latestCoverage": SEED.get("latestCoverage", 0), "priceDate": effective_date, "officialPriceDate": SEED["asOf"], "provisionalCount": sum(bool(x.get("provisional")) for x in refreshed), "provisionalTotal": len(refreshed), "fundamental": "任意・未確認", "earningsDate": f"決算判定 {quality.get('secondaryResolved', 0)}/{quality.get('secondaryTotal', 0)}（外部ページ取得 {quality.get('secondaryCoverage', 0)}/{quality.get('secondaryTotal', 0)}）", "tdnet": "発表済み資料は企業IRで確認"},
        "sources": [
            {"name": "JPX 東京証券取引所日報・上場銘柄一覧", "asOf": SEED["asOf"], "status": "公式値・33業種"},
            {"name": "JPX・Yahoo!ファイナンス・株予報 決算日", "asOf": effective_date, "status": "複数ソース照合済み" if earnings_ok else "照合不足"},
            {"name": "Yahoo!ファイナンス前日終値スナップショット", "asOf": effective_date, "status": f"完全同期 {len(supplemental)}/{len(candidate_rows)}" if quotes_complete else "不完全・未使用"},
        ],
    }
    if not gate:
        raise RuntimeError(result["message"])

    latest_close = {x["code"]: next((p for p in reversed(x["c"]) if p is not None), None) for x in SNAPSHOT["securities"]}
    latest_close.update({x["code"]: x.get("close") for x in refreshed})
    if quotes_complete:
        latest_close.update({code: q["close"] for code, q in supplemental.items() if q and q.get("date") == effective_date})
    history_days = [x for x in history_days if x.get("asOf") != effective_date]
    history_days.insert(0, {"asOf": effective_date, "candidates": [{k: c.get(k) for k in ("code", "name", "close", "entry", "targetPrice", "targetPrice1", "targetPrice2", "invalidation")} for c in final]})
    history_days = history_days[:30]
    for day in history_days:
        for row in day.get("candidates", []):
            current = latest_close.get(row["code"])
            row["currentClose"] = current
            row["changePct"] = round((current / row["close"] - 1) * 100, 1) if current else None
            row["targetReached"] = bool(current and row.get("targetPrice") and current >= row["targetPrice"])
    history_payload = {"currentAsOf": effective_date, "retentionDays": 30, "history": history_days}
    jst_today = dt.datetime.now(ZoneInfo("Asia/Tokyo")).strftime("%Y%m%d")
    is_previous = effective_date != jst_today
    status = {"lastAttemptAt": generated, "lastAttemptStatus": "success", "lastSuccessfulAt": generated, "dataAsOf": effective_date, "isPreviousBusinessDay": is_previous, "message": "更新成功（前営業日データ）" if is_previous else "日次更新成功"}
    dump(LATEST_PATH, result)
    dump(HISTORY_PATH, history_payload)
    dump(STATUS_PATH, status)
    print(json.dumps({"asOf": effective_date, "final": len(final), "historyDays": len(history_days), "market": result["marketRegime"]["level"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
