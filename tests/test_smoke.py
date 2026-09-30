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
