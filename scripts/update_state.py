"""Failure state without changing the last successful data or dates."""
import datetime as dt
import json
from pathlib import Path
from market_calendar import data_age


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text())
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def mark_failure(data: Path, diagnostics: dict, message: str, now=None) -> None:
    now = now or dt.datetime.now(dt.timezone.utc)
    diagnostics = {"generated_at": now.isoformat(), **diagnostics}
    status = read_json(data / "status.json")
    status.update({**data_age(status.get("dataAsOf"), now),
        "lastAttemptAt": now.isoformat(), "lastAttemptStatus": "failed",
        "message": message[:300], "failureStage": diagnostics.get("failure_stage", "unknown"),
        "failureReasons": diagnostics.get("failure_reasons", []),
        "qualityDetails": diagnostics.get("quality_details", {}),
    })
    (data / "status.json").write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n")
    (data / "update-diagnostics.json").write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2) + "\n")
