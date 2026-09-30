import json

from exporter.smoke import run_smoke_test


def test_offline_package_smoke(app, tmp_path):
    report = tmp_path / "report.json"
    assert run_smoke_test(app, report) == 0
    data = json.loads(report.read_text())
    assert data["status"] == "passed"
    assert data["version"] == "3.0.0"
    assert data["network"] == "blocked"
    assert data["export_formats"] == 4


def test_source_smoke_does_not_need_optional_qt_stacks(tmp_path):
    import subprocess
    import sys

    report = tmp_path / "without-media.json"
    program = """
import importlib.abc
import sys
class BlockOptionalQt(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('qfluentwidgets.multimedia', 'PyQt6.QtMultimedia', 'PyQt6.QtPdf')):
            raise ModuleNotFoundError('Optional media/PDF stack deliberately unavailable')
sys.meta_path.insert(0, BlockOptionalQt())
import spotify_exporter
spotify_exporter.main(['--smoke-test', '--smoke-report', sys.argv[1]])
"""
    result = subprocess.run(
        [sys.executable, "-c", program, str(report)], capture_output=True, text=True, timeout=20
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(report.read_text())["status"] == "passed"
