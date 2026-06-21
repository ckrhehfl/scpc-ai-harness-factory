from __future__ import annotations

from factory.evidence_index_builder import build_evidence_index, render_evidence_index_markdown
from factory.evidence_model import validate_evidence_index


def scan_report_fixture() -> dict:
    return {
        "contest_path": "examples/mock_contest_02",
        "files": [
            {
                "path": "records.jsonl",
                "absolute_path": "/local/records.jsonl",
                "name": "records.jsonl",
                "extension": ".jsonl",
                "size_bytes": 20,
                "file_kind": "jsonl",
                "role_candidates": ["jsonl_data_candidate"],
                "jsonl_preview": {
                    "line_count": 2,
                    "preview_rows": [{"id": 1}, {"id": 2}],
                    "parse_errors": [],
                },
            },
            {
                "path": "train.csv",
                "absolute_path": "/local/train.csv",
                "name": "train.csv",
                "extension": ".csv",
                "size_bytes": 200,
                "file_kind": "csv",
                "role_candidates": ["train_data"],
                "csv_preview": {
                    "columns": ["id", "text", "label"],
                    "column_count": 3,
                    "row_count": 6,
                    "first_row_preview": {"id": "1", "text": "great", "label": "positive"},
                    "preview_rows": [{"id": "1", "text": "great", "label": "positive"}],
                },
            },
            {
                "path": "metadata.json",
                "absolute_path": "/local/metadata.json",
                "name": "metadata.json",
                "extension": ".json",
                "size_bytes": 100,
                "file_kind": "json",
                "role_candidates": ["json_data_candidate"],
                "json_preview": {
                    "json_type": "object",
                    "top_level_keys": ["labels"],
                    "item_count": 1,
                    "preview": {"labels": ["positive", "negative"]},
                },
            },
            {
                "path": "rules.md",
                "absolute_path": "/local/rules.md",
                "name": "rules.md",
                "extension": ".md",
                "size_bytes": 80,
                "file_kind": "document",
                "role_candidates": ["rules_document"],
                "document_excerpt": {
                    "char_count": 17,
                    "excerpt": "Use exact labels.",
                    "truncated": False,
                },
                "document_chunks": [
                    {
                        "char_start": 0,
                        "char_end": 10,
                        "text": "Use exact ",
                    },
                    {
                        "char_start": 10,
                        "char_end": 17,
                        "text": "labels.",
                    },
                ],
                "declared_source": {
                    "role": "official_notice",
                    "source_kind": "document",
                    "visibility": "public",
                },
            },
            {
                "path": "broken.json",
                "absolute_path": "/local/broken.json",
                "name": "broken.json",
                "extension": ".json",
                "size_bytes": 8,
                "file_kind": "json",
                "role_candidates": ["json_data_candidate"],
                "preview_error": "preview_failed: bad json",
            },
        ],
    }


def records_by_type(index: dict) -> dict[str, dict]:
    return {record["key"].rsplit(":", 1)[-1]: record for record in index["records"]}


def evidence_type(record: dict) -> str:
    suffix = record["key"][len(f"file:{record['source_file']}:") :]
    if suffix.startswith("document_chunk:"):
        return "document_chunk"
    return suffix


def test_build_evidence_index_projects_all_supported_scan_facts():
    index = build_evidence_index(scan_report_fixture(), source_artifact="generated/input_scan_report.json")
    validate_evidence_index(index)

    assert index["schema_version"] == "v0.9A"
    assert index["artifact_type"] == "evidence_index"
    assert index["record_count"] == len(index["records"])
    assert len({record["evidence_id"] for record in index["records"]}) == len(index["records"])

    all_types = [evidence_type(record) for record in index["records"]]
    assert all_types.count("inventory") == 5
    assert "csv_structure" in all_types
    assert "json_structure" in all_types
    assert "jsonl_structure" in all_types
    assert "document_excerpt" in all_types
    assert all_types.count("document_chunk") == 2
    assert "preview_error" in all_types


def test_build_evidence_index_maps_preview_payloads_and_excludes_scanner_candidates():
    index = build_evidence_index(scan_report_fixture(), source_artifact="generated/input_scan_report.json")
    by_key = {record["key"]: record for record in index["records"]}

    inventory = by_key["file:train.csv:inventory"]
    assert inventory["observed_value"] == {"name": "train.csv", "extension": ".csv", "size_bytes": 200}

    csv_record = by_key["file:train.csv:csv_structure"]
    assert csv_record["observed_value"]["columns"] == ["id", "text", "label"]
    assert csv_record["observed_value"]["row_count"] == 6
    assert "preview_rows" not in csv_record["observed_value"]

    json_record = by_key["file:metadata.json:json_structure"]
    assert json_record["location"]["scope"] == "json_document"
    assert json_record["observed_value"]["top_level_keys"] == ["labels"]

    jsonl_record = by_key["file:records.jsonl:jsonl_structure"]
    assert jsonl_record["location"]["scope"] == "json_lines"
    assert jsonl_record["observed_value"]["line_count"] == 2

    doc_record = by_key["file:rules.md:document_excerpt"]
    assert doc_record["location"]["char_start"] == 0
    assert doc_record["location"]["char_end"] == len("Use exact labels.")
    assert doc_record["observed_value"]["excerpt"] == "Use exact labels."

    chunk_record = by_key["file:rules.md:document_chunk:0:10"]
    assert chunk_record["location"]["scope"] == "document_chunk"
    assert chunk_record["location"]["char_start"] == 0
    assert chunk_record["location"]["char_end"] == 10
    assert chunk_record["observed_value"] == {"text": "Use exact "}
    assert by_key["file:rules.md:document_chunk:10:17"]["evidence_id"] != chunk_record["evidence_id"]

    error_record = by_key["file:broken.json:preview_error"]
    assert error_record["observed_value"] == "preview_failed: bad json"

    for record in index["records"]:
        if isinstance(record["observed_value"], dict):
            assert "absolute_path" not in record["observed_value"]
            assert "role_candidates" not in record["observed_value"]
            assert "file_kind" not in record["observed_value"]
            assert "declared_source" not in record["observed_value"]
            assert "role" not in record["observed_value"]


def test_build_evidence_index_order_and_full_output_are_deterministic():
    scan = scan_report_fixture()
    first = build_evidence_index(scan, source_artifact="generated/input_scan_report.json")
    second = build_evidence_index(scan, source_artifact="generated/input_scan_report.json")

    assert first == second
    assert first["records"] == sorted(
        first["records"],
        key=lambda item: (item["source_file"], item["key"], item["evidence_id"]),
    )


def test_render_evidence_index_markdown_summarizes_records_and_scope_notes():
    index = build_evidence_index(scan_report_fixture(), source_artifact="generated/input_scan_report.json")
    markdown = render_evidence_index_markdown(index)

    assert "# Evidence Index" in markdown
    assert "- csv_structure: 1" in markdown
    assert "- document_chunk: 2" in markdown
    assert "## train.csv" in markdown
    assert "### csv_structure" in markdown
    assert "role_candidates는 Evidence로 승격하지 않음" in markdown
    assert "AI 추론과 사람 결정은 아직 포함하지 않음" in markdown
