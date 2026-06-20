from factory.spec_builder import build_contest_spec
from factory.gap_analyzer import analyze_gaps, render_gap_report


def test_gap_analyzer_reports_unknowns():
    spec = build_contest_spec("examples/mock_contest_01")
    report = analyze_gaps(spec)
    assert report["confirmed"]
    assert any("external_api_allowed" in item for item in report["gaps"])
    assert report["risks"]
    assert any("train/test 공통 컬럼" in item for item in report["schema_summary"])

    text = render_gap_report(report)
    assert "## 불명확한 항목" in text
    assert "## 사람 확인 필요" in text
    assert "## 규칙상 위험한 항목" in text
    assert "## 데이터 스키마 요약" in text
