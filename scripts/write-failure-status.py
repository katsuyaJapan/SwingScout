#!/usr/bin/env python3
import datetime as dt
import json
import os
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "public" / "data" / "status.json"
status = json.loads(path.read_text()) if path.exists() else {}
status.update({
    "lastAttemptAt": dt.datetime.now(dt.timezone.utc).isoformat(),
    "lastAttemptStatus": "failed",
    "isPreviousBusinessDay": True,
    "message": os.environ.get("SWINGSCOUT_FAILURE_MESSAGE", "日次更新に失敗したため、前回正常データを表示しています。")[:300],
})
path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n")
