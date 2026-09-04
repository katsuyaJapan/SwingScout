#!/usr/bin/env python3
"""Run one data pipeline stage and persist a compact diagnostic on failure."""
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "public" / "data" / "update-diagnostics.json"


def main() -> int:
    if len(sys.argv) < 3:
        raise SystemExit("usage: run-data-stage.py STAGE COMMAND [ARG ...]")
    stage, command = sys.argv[1], sys.argv[2:]
    completed = subprocess.run(command, cwd=ROOT)
    if completed.returncode:
        DIAGNOSTICS.write_text(json.dumps({
            "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "failure_stage": stage,
            "failure_reasons": [f"{stage} exited with code {completed.returncode}"],
            "quality_details": {},
        }, ensure_ascii=False, indent=2) + "\n")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
