#!/usr/bin/env python3
import datetime as dt
import json
import os
from pathlib import Path

path = Path(__file__).resolve().parents[1] / "public" / "data" / "status.json"
diagnostics_path = path.with_name("update-diagnostics.json")
status = json.loads(path.read_text()) if path.exists() else {}
diagnostics = json.loads(diagnostics_path.read_text()) if diagnostics_path.exists() else {}
status.update({
    "lastAttemptAt": dt.datetime.now(dt.timezone.utc).isoformat(),
    "lastAttemptStatus": "failed",
    "isPreviousBusinessDay": True,
    "message": os.environ.get("SWINGSCOUT_FAILURE_MESSAGE", "日次更新に失敗したため、前回正常データを表示しています。")[:300],
    "failureStage": diagnostics.get("failure_stage", os.environ.get("SWINGSCOUT_FAILURE_STAGE", "unknown")),
    "failureReasons": diagnostics.get("failure_reasons", []),
    "qualityDetails": diagnostics.get("quality_details", {}),
})
path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n")
