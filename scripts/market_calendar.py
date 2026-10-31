"""Shared JPX business-day and last-completed-session calculations."""
import datetime as dt
from zoneinfo import ZoneInfo

JPX_HOLIDAYS = {
    "20260101", "20260102", "20260112", "20260211", "20260223", "20260320", "20260429", "20260504", "20260505", "20260506", "20260720", "20260811", "20260921", "20260922", "20260923", "20261012", "20261103", "20261123", "20261231",
    "20270101", "20270111", "20270211", "20270223", "20270322", "20270429", "20270503", "20270504", "20270505", "20270719", "20270811", "20270920", "20270923", "20271011", "20271103", "20271123", "20271231",
}

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


def previous_business_day(day: dt.date) -> dt.date:
    day -= dt.timedelta(days=1)
    while day.weekday() >= 5 or day.strftime("%Y%m%d") in JPX_HOLIDAYS:
        day -= dt.timedelta(days=1)
    return day


def last_completed_session(now: dt.datetime | None = None) -> dt.date:
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(ZoneInfo("Asia/Tokyo"))
    today = now.date()
    if today.weekday() >= 5 or today.strftime("%Y%m%d") in JPX_HOLIDAYS or (now.hour, now.minute) < (15, 30):
        return previous_business_day(today)
    return today


def data_age(as_of: str | None, now: dt.datetime | None = None) -> dict:
    now = (now or dt.datetime.now(dt.timezone.utc)).astimezone(ZoneInfo("Asia/Tokyo"))
    today = now.date()
    expected = last_completed_session(now)
    try:
        parsed = dt.datetime.strptime(as_of or "", "%Y%m%d").date()
        lag = business_days(parsed.strftime("%Y%m%d"), expected.strftime("%Y%m%d"))
    except (TypeError, ValueError):
        return {"isPreviousBusinessDay": False, "dataLagBusinessDays": None, "isStale": True}
    return {"isPreviousBusinessDay": parsed == previous_business_day(today),
            "dataLagBusinessDays": lag, "isStale": lag is None or lag > 0}
