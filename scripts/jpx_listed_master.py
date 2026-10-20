"""Discover and validate JPX's monthly listed-security master."""
from __future__ import annotations

import datetime as dt
import io
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

import openpyxl
import xlrd

INDEX_URL = "https://www.jpx.co.jp/markets/statistics-equities/misc/01.html"
REQUIRED_COLUMNS = ("日付", "コード", "33業種区分", "市場・商品区分")


class MasterError(RuntimeError):
    pass


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)


def discover_url(html: str) -> str:
    parser = _Links()
    parser.feed(html)
    matches = []
    for href in parser.links:
        url = urljoin(INDEX_URL, href)
        parts = urlsplit(url)
        if (parts.scheme == "https" and parts.netloc == "www.jpx.co.jp"
                and parts.path.rsplit("/", 1)[-1].lower() in ("data_j.xls", "data_j.xlsx")):
            matches.append(url)
    matches = list(dict.fromkeys(matches))
    if len(matches) != 1:
        raise MasterError(f"JPX listed master: expected one download link at {INDEX_URL}, found {len(matches)}")
    return matches[0]


def download(url: str) -> bytes:
    try:
        with urlopen(Request(url, headers={"User-Agent": "SwingScout/2.0"}), timeout=30) as response:
            return response.read()
    except Exception as exc:
        raise MasterError(f"JPX listed master download failed: url={url}: {exc}") from exc


def parse_master(content: bytes, url: str) -> tuple[dict, str]:
    """Return code -> (sector, market), plus the actual workbook reference date."""
    try:
        if urlsplit(url).path.lower().endswith(".xlsx"):
            book = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
            try:
                rows = list(book.active.iter_rows(values_only=True))
            finally:
                book.close()
        else:
            book = xlrd.open_workbook(file_contents=content)
            sheet = book.sheet_by_index(0)
            rows = [sheet.row_values(i) for i in range(sheet.nrows)]
        headers = [str(value).strip() for value in rows[0]]
        positions = {name: headers.index(name) for name in REQUIRED_COLUMNS}
        master = {}
        dates = set()
        for row in rows[1:]:
            if not any(value is not None and value != "" for value in row):
                continue
            code = str(row[positions["コード"]]).strip()
            if code.endswith(".0"):
                code = code[:-2]
            # Preserve alphanumeric codes and five-character preferred-share codes.
            if len(code) not in (4, 5) or not code.isascii() or not code.isalnum():
                raise ValueError(f"invalid security code: {code!r}")
            sector = str(row[positions["33業種区分"]] or "").strip()
            market = str(row[positions["市場・商品区分"]] or "").strip()
            if not sector or not market or code in master:
                raise ValueError(f"missing classification or duplicate security code: {code}")
            date = row[positions["日付"]]
            if isinstance(date, (dt.datetime, dt.date)):
                date = date.strftime("%Y%m%d")
            else:
                date = str(date).removesuffix(".0").strip()
            dt.datetime.strptime(date, "%Y%m%d")
            dates.add(date)
            master[code] = (sector, market)
        if len(master) < 3000 or len(dates) != 1:
            raise ValueError(f"unexpected rows={len(master)}, dates={sorted(dates)}")
        return master, dates.pop()
    except Exception as exc:
        raise MasterError(f"JPX listed master validation failed: url={url}: {exc}") from exc


def fetch_master() -> tuple[dict, dict]:
    url = discover_url(download(INDEX_URL).decode("utf-8", "replace"))
    master, as_of = parse_master(download(url), url)
    return master, {"url": url, "asOf": as_of, "rows": len(master)}


def has_current_listing_and_price(security: dict, master: dict) -> bool:
    """Historical rows for delisted or unpriced securities are not current candidates."""
    return security.get("code") in master and all(
        security.get(field) and security[field][-1] is not None for field in ("c", "v", "t")
    )
