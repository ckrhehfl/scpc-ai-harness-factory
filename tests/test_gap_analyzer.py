from factory.spec_builder import build_contest_spec
from factory.gap_analyzer import analyze_gaps


def test_gap_analyzer_reports_unknowns():
    spec = build_contest_spec("examples/mock_contest_01")
    report = analyze_gaps(spec)
    assert report["confirmed"]
    assert any("external_api_allowed" in item for item in report["gaps"])
    assert report["risks"]
