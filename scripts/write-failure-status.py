#!/usr/bin/env python3
import datetime as dt
import os
from pathlib import Path
from update_state import mark_failure, read_json

if __name__ == "__main__":
    data = Path(__file__).resolve().parents[1] / "public" / "data"
    stage = os.environ.get("SWINGSCOUT_FAILURE_STAGE")
    message = os.environ.get("SWINGSCOUT_FAILURE_MESSAGE", "日次更新に失敗したため、前回正常データを表示しています。")
    diagnostics = read_json(data / "update-diagnostics.json")
    if stage:
        diagnostics = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
                       "failure_stage": stage, "failure_reasons": [message], "quality_details": {}}
    mark_failure(data, diagnostics, message)
