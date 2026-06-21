from __future__ import annotations

from factory.input_scanner import read_document_chunks, scan_contest_inputs, save_input_scan_report


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


def test_document_chunks_cover_full_text_deterministically_and_keep_excerpt(tmp_path):
    contest = tmp_path / "contest"
    contest.mkdir()
    text = "A" * 4000 + "B" + "C" * 3999 + "D"
    document = contest / "notice.txt"
    document.write_text(text, encoding="utf-8")

    assert read_document_chunks(tmp_path / "missing.txt") == []
    chunks = read_document_chunks(document)
    assert chunks == read_document_chunks(document)
    assert chunks[0]["char_start"] == 0
    assert chunks[-1]["char_end"] == len(text)
    assert all(left["char_end"] == right["char_start"] for left, right in zip(chunks, chunks[1:]))
    assert "".join(chunk["text"] for chunk in chunks) == text

    scan = scan_contest_inputs(contest)
    item = {file_info["path"]: file_info for file_info in scan["files"]}["notice.txt"]
    assert item["document_excerpt"]["excerpt"] == text[:4000]
    assert item["document_excerpt"]["truncated"] is True
    assert len(item["document_chunks"]) == 3


def test_document_chunk_boundaries_for_empty_short_exact_and_one_over(tmp_path):
    empty = tmp_path / "empty.txt"
    short = tmp_path / "short.txt"
    exact = tmp_path / "exact.txt"
    one_over = tmp_path / "one_over.txt"
    empty.write_text("", encoding="utf-8")
    short.write_text("x" * 10, encoding="utf-8")
    exact.write_text("x" * 4000, encoding="utf-8")
    one_over.write_text("x" * 4001, encoding="utf-8")

    assert read_document_chunks(empty) == []
    assert read_document_chunks(short) == [{"char_start": 0, "char_end": 10, "text": "x" * 10}]
    assert read_document_chunks(exact) == [{"char_start": 0, "char_end": 4000, "text": "x" * 4000}]
    assert [chunk["char_end"] for chunk in read_document_chunks(one_over)] == [4000, 4001]


def test_manifest_metadata_is_added_without_overwriting_scanner_facts(tmp_path):
    contest = tmp_path / "contest"
    contest.mkdir()
    (contest / "notice.txt").write_text("notice", encoding="utf-8")
    (contest / "contest_package.json").write_text(
        '{"schema_version":"v0.9B","contest":{"name":"SCPC","phase":"preannouncement"},'
        '"sources":[{"path":"notice.txt","role":"official_notice","source_kind":"document",'
        '"visibility":"public","origin":"export"}],"declared_unknowns":[]}',
        encoding="utf-8",
    )

    item = {file_info["path"]: file_info for file_info in scan_contest_inputs(contest)["files"]}["notice.txt"]
    assert item["file_kind"] == "document"
    assert item["role_candidates"] == ["supporting_document"]
    assert item["declared_source"]["role"] == "official_notice"


def test_manifest_source_kind_conflict_is_warning_not_observed_fact(tmp_path):
    contest = tmp_path / "contest"
    contest.mkdir()
    (contest / "notice.txt").write_text("notice", encoding="utf-8")
    (contest / "contest_package.json").write_text(
        '{"schema_version":"v0.9B","contest":{"name":"SCPC","phase":"preannouncement"},'
        '"sources":[{"path":"notice.txt","role":"official_notice","source_kind":"image",'
        '"visibility":"public"}],"declared_unknowns":[]}',
        encoding="utf-8",
    )

    item = {file_info["path"]: file_info for file_info in scan_contest_inputs(contest)["files"]}["notice.txt"]
    assert item["file_kind"] == "document"
    assert item["declared_source"]["source_kind"] == "image"
    assert item["declared_source_warnings"]
