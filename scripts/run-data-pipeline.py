#!/usr/bin/env python3
"""Validate the entire data update before allowing any generated files to publish."""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from update_state import mark_failure, read_json

ROOT = Path(__file__).resolve().parents[1]
STAGES = [
    ("jpx_snapshot", [sys.executable, "scripts/build-jpx-snapshot.py"]),
    ("sector_data", ["node", "scripts/fetch-sector-data.mjs"]),
    ("analysis_seed", [sys.executable, "scripts/build-analysis-seed.py"]),
    ("static_data", [sys.executable, "scripts/generate-static-data.py"]),
    ("data_tests", ["npm", "run", "test:data"]),
]


def run_pipeline(root=ROOT, stages=STAGES, execute=subprocess.run) -> int:
    data = root / "public" / "data"
    with tempfile.TemporaryDirectory(prefix="swingscout-last-good-") as directory:
        backup = Path(directory) / "data"
        shutil.copytree(data, backup)
        # Old diagnostics must never be attributed to this attempt.
        (data / "update-diagnostics.json").unlink(missing_ok=True)
        try:
            for stage, command in stages:
                result = execute([sys.executable, "scripts/run-data-stage.py", stage, *command], cwd=root)
                if result.returncode:
                    raise RuntimeError(f"{stage} exited with code {result.returncode}")
        except Exception as exc:
            diagnostics = read_json(data / "update-diagnostics.json")
            if not diagnostics:
                diagnostics = {"failure_stage": stage, "failure_reasons": [str(exc)], "quality_details": {}}
            # Restore every file, including candidates written before a later test failed.
            shutil.rmtree(data)
            shutil.copytree(backup, data)
            mark_failure(data, diagnostics, "日次更新に失敗したため、前回正常データを表示しています。")
            print(str(exc), file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(run_pipeline())
