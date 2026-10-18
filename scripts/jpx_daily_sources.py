"""Resolve JPX daily PDFs from the publication feeds used by the official page."""
from __future__ import annotations

import datetime as dt
import json
import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

BASE = "https://www.jpx.co.jp"
FEED = BASE + "/automation/markets/statistics-equities/daily/json/"
MONTHS_URL = FEED + "tsedaily_report_monthlylist.json"


def read_url(url: str) -> str:
    with urlopen(Request(url, headers={"User-Agent": "SwingScout/2.0"}), timeout=30) as response:
        return response.read().decode("utf-8", "replace")


def stock_url(path: str) -> tuple[str, str]:
    url = urljoin(BASE, path)
    parts = urlsplit(url)
    match = re.search(r"/stq_(\d{8})\.pdf$", parts.path)
    if parts.scheme != "https" or parts.netloc != "www.jpx.co.jp" or not match or parts.query:
        raise ValueError(f"Invalid JPX stock PDF URL: {url}")
    day = match.group(1)
    dt.datetime.strptime(day, "%Y%m%d")
    return day, url


def json_stock_links(document: str, month: str) -> dict[str, str]:
    result = {}
    rows = json.loads(document)["TableDatas"]
    for row in rows:
        path = row.get("Stocks")
        if not path or path == "-":
            continue
        day, url = stock_url(path)
        if day != row.get("TradeDate") or not day.startswith(month):
            raise ValueError(f"JPX publication date mismatch: {row}")
        if day in result and result[day] != url:
            raise ValueError(f"Conflicting JPX links for {day}")
        result[day] = url
    return result


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.paths = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            path = dict(attrs).get("href", "")
            if re.search(r"/stq_\d{8}\.pdf$", path):
                self.paths.append(path)


def html_stock_links(document: str, month: str) -> dict[str, str]:
    parser = _Links()
    parser.feed(document)
    result = {}
    for path in parser.paths:
        day, url = stock_url(path)
        if not day.startswith(month):
            raise ValueError(f"JPX publication month mismatch: {url}")
        if day in result and result[day] != url:
            raise ValueError(f"Conflicting JPX links for {day}")
        result[day] = url
    return result


def publication_months(read=read_url) -> list[str]:
    rows = json.loads(read(MONTHS_URL))["TableDatas"]
    months = sorted({row["Month"] for row in rows}, reverse=True)
    if not months:
        raise ValueError("JPX publication month feed is empty")
    for month in months:
        if not re.fullmatch(r"\d{6}", month):
            raise ValueError(f"Invalid JPX publication month: {month}")
        dt.datetime.strptime(month, "%Y%m")
    return months


def previous_month(month: str, offset: int) -> str:
    number = int(month[:4]) * 12 + int(month[4:]) - 1 - offset
    year, zero_month = divmod(number, 12)
    return f"{year:04d}{zero_month + 1:02d}"


def month_links(month: str, modern_months: list[str], read=read_url) -> dict[str, str]:
    if month in modern_months:
        return json_stock_links(read(FEED + f"tsedaily_report_{month}.json"), month)
    # The official page uses historical HTML fragments before the JSON migration.
    if month >= min(modern_months):
        raise ValueError(f"Missing JPX month in publication feed: {month}")
    return html_stock_links(read(FEED + f"tsedaily_report_{month}.html"), month)


def latest_publication_date(read=read_url) -> str:
    months = publication_months(read)
    links = month_links(months[0], months, read)
    if not links:
        raise ValueError(f"JPX latest publication month is empty: {months[0]}")
    return max(links)


def discover_daily_links(read=read_url, days: int = 250) -> list[tuple[str, str]]:
    months = publication_months(read)
    links = {}
    # Bounded search; never silently replace a missing month with a partial history.
    for offset in range(18):
        month = previous_month(months[0], offset)
        found = month_links(month, months, read)
        if not found:
            raise ValueError(f"JPX publication month has no stock PDFs: {month}")
        links.update(found)
        if len(links) >= days:
            return sorted(links.items())[-days:]
    raise ValueError(f"Insufficient JPX daily history: {len(links)} < {days}")
