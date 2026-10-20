#!/usr/bin/env python3
"""Stream stage logs and retain the cause without overwriting quality diagnostics."""
from collections import deque
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path
from update_state import read_json

ROOT = Path(__file__).resolve().parents[1]
DIAGNOSTICS = ROOT / "public" / "data" / "update-diagnostics.json"


def run_stage(stage, command, root=ROOT) -> int:
    path = root / "public" / "data" / "update-diagnostics.json"
    before = path.read_text() if path.exists() else None
    tail = deque(maxlen=60)
    try:
        with subprocess.Popen(command, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, encoding="utf-8", errors="replace", bufsize=1) as child:
            for line in child.stdout:
                print(line, end="", flush=True)
                tail.append(line[-2000:])
            code = child.wait()
    except OSError as exc:
        code = 1
        tail.append(str(exc))
    if code:
        after = path.read_text() if path.exists() else None
        diagnostics = read_json(path) if after is not None and after != before else {}
        log = "".join(tail)[-8000:]
        diagnostics.update({"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
            "failure_stage": diagnostics.get("failure_stage") or stage,
            "failure_reasons": diagnostics.get("failure_reasons") or [f"{stage} exited with code {code}", log[-2000:]],
        })
        diagnostics["quality_details"] = {**diagnostics.get("quality_details", {}),
            "command": command, "exit_code": code, "error_log_tail": log,
            "source_urls": sorted(set(re.findall(r'https?://[^\s\x22\x27<>]+', log))),
        }
        path.write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2) + "\n")
    return code


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit("usage: run-data-stage.py STAGE COMMAND [ARG ...]")
    raise SystemExit(run_stage(sys.argv[1], sys.argv[2:]))
