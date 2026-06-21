from __future__ import annotations

from factory.input_scanner import scan_contest_inputs, save_input_scan_report


def test_scan_contest_inputs_collects_files_documents_and_csv_preview(tmp_path):
    scan = scan_contest_inputs("examples/mock_contest_02")

    assert scan["file_count"] >= 6
    assert scan["summary"]["has_description"] is True
    assert scan["summary"]["has_rules"] is True
    assert scan["summary"]["has_evaluation"] is True
    assert "description.md" in scan["documents"]

    files_by_path = {item["path"]: item for item in scan["files"]}
    train = files_by_path["train.csv"]
    assert train["file_kind"] == "csv"
    assert "train_data" in train["role_candidates"]
    assert train["csv_preview"]["columns"] == ["id", "text", "label"]
    assert train["csv_preview"]["row_count"] == 6
    assert train["csv_preview"]["first_row_preview"]["label"] == "positive"

    json_path, md_path = save_input_scan_report(scan, tmp_path)
    assert json_path.exists()
    assert md_path.exists()
    assert "# Input Scan Report" in md_path.read_text(encoding="utf-8")


def test_scan_contest_inputs_detects_json_jsonl_and_media(tmp_path):
    contest = tmp_path / "contest"
    contest.mkdir()
    (contest / "description.md").write_text("# Demo", encoding="utf-8")
    (contest / "data.json").write_text('{"items": [{"id": 1, "text": "a"}]}', encoding="utf-8")
    (contest / "records.jsonl").write_text('{"id": 1}\n{"id": 2}\n', encoding="utf-8")
    (contest / "image.png").write_bytes(b"not really an image")
    (contest / "bundle.zip").write_bytes(b"not really a zip")

    scan = scan_contest_inputs(contest)
    files_by_path = {item["path"]: item for item in scan["files"]}

    assert files_by_path["data.json"]["file_kind"] == "json"
    assert files_by_path["data.json"]["json_preview"]["json_type"] == "object"
    assert files_by_path["records.jsonl"]["file_kind"] == "jsonl"
    assert files_by_path["records.jsonl"]["jsonl_preview"]["line_count"] == 2
    assert files_by_path["image.png"]["file_kind"] == "image"
    assert files_by_path["bundle.zip"]["file_kind"] == "archive"
