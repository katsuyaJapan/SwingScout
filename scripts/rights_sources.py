#!/usr/bin/env python3
"""Parsers and lightweight fetchers for SwingScout rights-risk sources."""

from __future__ import annotations

import datetime as dt
import html
import re
import urllib.request


USER_AGENT = "Mozilla/5.0 SwingScout/1.5"
RIGHTS_DISCLOSURE_PATTERNS = (
    re.compile(r"株主優待.{0,30}(?:変更|廃止|新設|導入|再開)"),
    re.compile(r"(?:配当|剰余金).{0,30}基準日"),
    re.compile(r"基準日.{0,30}(?:変更|設定)"),
)


def _plain_text(page: str) -> str:
    page = re.sub(r"<script\b[^>]*>.*?</script>", " ", page, flags=re.I | re.S)
    page = re.sub(r"<style\b[^>]*>.*?</style>", " ", page, flags=re.I | re.S)
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page))).strip()


def _next_weekday(day: dt.date) -> dt.date:
    day += dt.timedelta(days=1)
    while day.weekday() >= 5:
        day += dt.timedelta(days=1)
    return day


def _add_weekdays(day: dt.date, count: int) -> dt.date:
    for _ in range(count):
        day = _next_weekday(day)
    return day


def parse_yahoo_incentive_dates(page: str, as_of: str) -> list[dict[str, str]]:
    """Extract exact future last-trade dates from a Yahoo Japan incentive page."""
    text = _plain_text(page)
    marker = text.find("権利付き最終日")
    if marker < 0:
        return []
    window = text[marker : marker + 360]
    as_of_day = dt.datetime.strptime(as_of, "%Y%m%d").date()
    events: list[dict[str, str]] = []
    seen: set[dt.date] = set()
    for year, month, day in re.findall(r"(20\d{2})年(\d{1,2})月(\d{1,2})日", window):
        last_trade = dt.date(int(year), int(month), int(day))
        if last_trade < as_of_day or last_trade in seen:
            continue
        seen.add(last_trade)
        ex_date = _next_weekday(last_trade)
        record_date = _add_weekdays(last_trade, 2)
        events.append({
            "rightsExitDeadline": last_trade.strftime("%Y%m%d"),
            "exRightsDate": ex_date.strftime("%Y%m%d"),
            "rightsRecordDate": record_date.strftime("%Y%m%d"),
        })
    return sorted(events, key=lambda row: row["exRightsDate"])


def parse_recent_rights_disclosures(page: str, as_of: str, days: int = 31) -> list[str]:
    """Return recent TDnet titles that may change an entitlement date or benefit."""
    text = _plain_text(page)
    as_of_day = dt.datetime.strptime(as_of, "%Y%m%d").date()
    titles: list[str] = []
    for pattern in RIGHTS_DISCLOSURE_PATTERNS:
        for match in pattern.finditer(text):
            start = max(0, match.start() - 80)
            segment = text[start : match.end() + 140]
            date_match = re.search(r"(?:(20\d{2})/)?(\d{1,2})/(\d{1,2})(?:\s+\d{1,2}:\d{2})?", segment[match.start() - start :])
            if not date_match:
                continue
            year = int(date_match.group(1) or as_of_day.year)
            month, day = int(date_match.group(2)), int(date_match.group(3))
            disclosed = dt.date(year, month, day)
            if not date_match.group(1) and disclosed > as_of_day + dt.timedelta(days=31):
                disclosed = disclosed.replace(year=year - 1)
            if 0 <= (as_of_day - disclosed).days <= days:
                title = re.sub(r"\s+", " ", match.group(0)).strip()
                if title not in titles:
                    titles.append(title)
    return titles


def fetch_yahoo_rights(code: str, as_of: str, timeout: int = 20) -> dict:
    """Check Yahoo's exact benefit deadline and its candidate-specific TDnet list."""
    result = {"checked": [], "events": [], "disclosures": [], "errors": []}
    pages = (
        ("Yahoo!ファイナンス株主優待", f"https://finance.yahoo.co.jp/quote/{code}.T/incentive"),
        ("TDnet掲載一覧", f"https://finance.yahoo.co.jp/quote/{code}.T/disclosure"),
    )
    for name, url in pages:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            page = urllib.request.urlopen(request, timeout=timeout).read().decode("utf-8", "replace")
            result["checked"].append(name)
            if "incentive" in url:
                result["events"] = parse_yahoo_incentive_dates(page, as_of)
            else:
                result["disclosures"] = parse_recent_rights_disclosures(page, as_of)
        except Exception as exc:  # The caller decides whether coverage is sufficient.
            result["errors"].append(f"{name}: {exc}")
    return result
