#!/usr/bin/env python3
"""Check whether JPX has published a trading day newer than the deployed data."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS_PATH = ROOT / "public" / "data" / "status.json"
JPX_DAILY_URL = "https://www.jpx.co.jp/markets/statistics-equities/daily/index.html"
USER_AGENT = {"User-Agent": "SwingScout/2.0 JPX freshness check"}


def extract_latest_date(html: str) -> str:
    dates = {
        f"{year}{month}{day}"
        for year, month, day in re.findall(r"(20\d{2})/(\d{2})/(\d{2})", html)
    }
    if not dates:
        raise ValueError("JPX日報ページから掲載日を取得できませんでした")
    return max(dates)


def read_status() -> dict:
    return json.loads(STATUS_PATH.read_text()) if STATUS_PATH.exists() else {}


def write_output(name: str, value: str) -> None:
    import os

    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")
    print(f"{name}={value}")


def mark_waiting(status: dict, jpx_date: str) -> None:
    status.update({
        "lastAttemptAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        "lastAttemptStatus": "waiting",
        "isPreviousBusinessDay": True,
        "message": f"JPX公式データ公開待ち（最新掲載 {jpx_date}）",
    })
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mark-waiting", action="store_true")
    args = parser.parse_args()
    status = read_status()
    stored_date = str(status.get("dataAsOf") or "00000000")
    try:
        request = urllib.request.Request(JPX_DAILY_URL, headers=USER_AGENT)
        with urllib.request.urlopen(request, timeout=30) as response:
            jpx_date = extract_latest_date(response.read().decode("utf-8", "replace"))
        refresh_required = jpx_date > stored_date
        if args.mark_waiting and not refresh_required:
            mark_waiting(status, jpx_date)
        write_output("jpx_date", jpx_date)
        write_output("stored_date", stored_date)
        write_output("refresh_required", str(refresh_required).lower())
    except Exception as exc:
        # 判定不能時は従来の完全処理を実行し、前回正常データを守る。
        write_output("jpx_date", "unknown")
        write_output("stored_date", stored_date)
        write_output("refresh_required", "true")
        write_output("freshness_error", str(exc).replace("\n", " ")[:200])


if __name__ == "__main__":
    main()
