import datetime as dt
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from market_calendar import data_age, last_completed_session
from update_state import mark_failure


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

pipeline = load("run-data-pipeline")
stage_runner = load("run-data-stage")


class RecoveryTest(unittest.TestCase):
    def baseline(self, root):
        data = root / "public" / "data"
        data.mkdir(parents=True)
        for name in ["latest", "history", "sector-data", "jpx-snapshot"]:
            (data / f"{name}.json").write_text(json.dumps({"value": "last-good"}))
        (data / "status.json").write_text(json.dumps({"dataAsOf": "20260902", "lastSuccessfulAt": "old-success"}))
        (data / "update-diagnostics.json").write_text(json.dumps({"failure_stage": "old-failure"}))
        return data

    def test_failure_after_generation_restores_all_files_and_removes_new_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = self.baseline(root)
            def execute(command, cwd):
                for name in ["latest", "history", "sector-data", "jpx-snapshot"]:
                    (data / f"{name}.json").write_text('{"value":"new"}')
                (data / "analysis-seed.json").write_text("new")
                (data / "status.json").write_text('{"dataAsOf":"20261015","lastSuccessfulAt":"new-success"}')
                (data / "update-diagnostics.json").write_text(json.dumps({
                    "failure_stage": "data_tests", "failure_reasons": ["contract failed"], "quality_details": {"detail": 7}}))
                return SimpleNamespace(returncode=1)
            self.assertEqual(pipeline.run_pipeline(root, [("data_tests", ["test"])], execute), 1)
            for name in ["latest", "history", "sector-data", "jpx-snapshot"]:
                self.assertEqual(json.loads((data / f"{name}.json").read_text())["value"], "last-good")
            self.assertFalse((data / "analysis-seed.json").exists())
            status = json.loads((data / "status.json").read_text())
            self.assertEqual(status["dataAsOf"], "20260902")
            self.assertEqual(status["lastSuccessfulAt"], "old-success")
            self.assertEqual(status["failureStage"], "data_tests")
            self.assertEqual(status["qualityDetails"], {"detail": 7})

    def test_success_keeps_generated_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); data = self.baseline(root)
            def execute(command, cwd):
                (data / "latest.json").write_text("new")
                return SimpleNamespace(returncode=0)
            self.assertEqual(pipeline.run_pipeline(root, [("generate", ["test"])], execute), 0)
            self.assertEqual((data / "latest.json").read_text(), "new")

    def test_stage_keeps_quality_failure_and_its_details(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); data = self.baseline(root)
            command = [sys.executable, "-c", '''import json,sys
from pathlib import Path
Path('public/data/update-diagnostics.json').write_text(json.dumps({'failure_stage':'quality_gate','failure_reasons':['sector_date'],'quality_details':{'sector_price_date':'2026-09-30'}}))
print('HTTP Error 404: https://www.jpx.co.jp/missing.xls',file=sys.stderr)
sys.exit(1)''']
            self.assertEqual(stage_runner.run_stage("static_data", command, root), 1)
            diagnostic = json.loads((data / "update-diagnostics.json").read_text())
            self.assertEqual(diagnostic["failure_stage"], "quality_gate")
            self.assertEqual(diagnostic["failure_reasons"], ["sector_date"])
            self.assertEqual(diagnostic["quality_details"]["sector_price_date"], "2026-09-30")
            self.assertIn("https://www.jpx.co.jp/missing.xls", diagnostic["quality_details"]["source_urls"])

    def test_unexpected_process_error_does_not_reuse_old_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); data = self.baseline(root)
            def execute(command, cwd):
                raise OSError("cannot start")
            self.assertEqual(pipeline.run_pipeline(root, [("analysis_seed", ["test"])], execute), 1)
            status = json.loads((data / "status.json").read_text())
            self.assertEqual(status["failureStage"], "analysis_seed")
            self.assertIn("cannot start", status["failureReasons"])

    def test_last_completed_session_across_midnight_weekend_and_holiday(self):
        jst = dt.timezone(dt.timedelta(hours=9))
        for timestamp, expected in (
            ((2026, 10, 30, 15, 29), "20261029"),
            ((2026, 10, 30, 15, 30), "20261030"),
            ((2026, 10, 30, 23, 59), "20261030"),
            ((2026, 10, 31, 0, 0), "20261030"),
            ((2026, 11, 2, 10, 0), "20261030"),
            ((2026, 11, 3, 16, 0), "20261102"),
        ):
            with self.subTest(timestamp=timestamp):
                now = dt.datetime(*timestamp, tzinfo=jst)
                self.assertEqual(last_completed_session(now).strftime("%Y%m%d"), expected)

    def test_weekend_and_holiday_data_age(self):
        sunday = dt.datetime(2026, 10, 18, 4, 0, tzinfo=dt.timezone.utc)
        self.assertEqual(data_age("20261015", sunday)["dataLagBusinessDays"], 1)
        self.assertFalse(data_age("20260902", sunday)["isPreviousBusinessDay"])
        tuesday_before_open = dt.datetime(2026, 10, 12, 23, 0, tzinfo=dt.timezone.utc)
        self.assertEqual(data_age("20261009", tuesday_before_open)["dataLagBusinessDays"], 0)
