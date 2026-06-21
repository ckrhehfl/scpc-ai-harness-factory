from __future__ import annotations

from pathlib import Path
from typing import Any
import json

from factory.evidence_model import (
    ARTIFACT_TYPE,
    CONFIDENCE_HIGH,
    SCHEMA_VERSION,
    SOURCE_ACTOR_DETERMINISTIC,
    SOURCE_TYPE_CONTEST_FILE,
    STATUS_OBSERVED,
    EvidenceModelError,
    build_evidence_id,
    normalize_source_path,
    validate_evidence_index,
)
from factory.utils import to_simple_yaml, write_json, write_text


EVIDENCE_TYPES = [
    "inventory",
    "csv_structure",
    "json_structure",
    "jsonl_structure",
    "document_excerpt",
    "document_chunk",
    "preview_error",
]


def load_input_scan_report(path: str | Path) -> dict[str, Any]:
    report_path = Path(path)
    try:
        data = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise EvidenceModelError(f"Malformed JSON in input scan report: {exc}") from exc
    except OSError as exc:
        raise EvidenceModelError(f"Could not read input scan report: {exc}") from exc
    if not isinstance(data, dict):
        raise EvidenceModelError("Input scan report must be a JSON object")
    files = data.get("files")
    if not isinstance(files, list):
        raise EvidenceModelError("Input scan report field 'files' must be a list")
    return data


def build_evidence_index(
    scan_report: dict[str, Any],
    *,
    source_artifact: str,
) -> dict[str, Any]:
    if not isinstance(scan_report, dict):
        raise EvidenceModelError("Input scan report must be an object")
    files = scan_report.get("files")
    if not isinstance(files, list):
        raise EvidenceModelError("Input scan report field 'files' must be a list")

    records: list[dict[str, Any]] = []
    for file_info in files:
        if not isinstance(file_info, dict):
            raise EvidenceModelError("Each input scan file item must be an object")
        records.extend(_records_for_file(file_info))

    records = sorted(records, key=lambda item: (item["source_file"], item["key"], item["evidence_id"]))
    index = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": ARTIFACT_TYPE,
        "contest_path": scan_report.get("contest_path"),
        "source_artifact": source_artifact,
        "record_count": len(records),
        "records": records,
    }
    validate_evidence_index(index)
    return index


def render_evidence_index_markdown(index: dict[str, Any]) -> str:
    validate_evidence_index(index)
    counts = {evidence_type: 0 for evidence_type in EVIDENCE_TYPES}
    for record in index["records"]:
        evidence_type = _evidence_type_from_key(record)
        counts[evidence_type] = counts.get(evidence_type, 0) + 1

    lines = [
        "# Evidence Index",
        "",
        f"- schema_version: {index['schema_version']}",
        f"- contest_path: {index.get('contest_path')}",
        f"- source_artifact: {index.get('source_artifact')}",
        f"- record_count: {index['record_count']}",
        "",
        "## Summary",
        "",
    ]
    for evidence_type in EVIDENCE_TYPES:
        lines.append(f"- {evidence_type}: {counts.get(evidence_type, 0)}")

    lines.extend(
        [
            "",
            "## Scope Notes",
            "",
            "- role_candidates는 Evidence로 승격하지 않음",
            "- 이 산출물은 관찰 사실만 포함함",
            "- AI 추론과 사람 결정은 아직 포함하지 않음",
            "",
        ]
    )

    current_file: str | None = None
    for record in index["records"]:
        if record["source_file"] != current_file:
            current_file = record["source_file"]
            lines.extend(["", f"## {current_file}", ""])
        evidence_type = _evidence_type_from_key(record)
        lines.extend(
            [
                f"### {evidence_type}",
                "",
                f"- evidence_id: `{record['evidence_id']}`",
                f"- status: {record['status']}",
                f"- source_actor: {record['source_actor']}",
                f"- extraction_method: {record['extraction_method']}",
                "- observed_value:",
                "",
                "```yaml",
                _render_observed_value(record),
                "```",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def save_evidence_index(index: dict[str, Any], output_dir: str | Path) -> dict[str, Path]:
    validate_evidence_index(index)
    markdown = render_evidence_index_markdown(index)
    out = Path(output_dir)
    return {
        "json": write_json(out / "evidence_index.json", index),
        "md": write_text(out / "evidence_index.md", markdown),
    }


def _records_for_file(file_info: dict[str, Any]) -> list[dict[str, Any]]:
    source_file = normalize_source_path(file_info.get("path"))
    inventory = _require_fields(file_info, ["name", "extension", "size_bytes"], source_file)
    records = [
        _build_record(
            source_file=source_file,
            evidence_type="inventory",
            location={"path": source_file, "scope": "file"},
            extraction_method="input_scanner.scan_file",
            observed_value={
                "name": inventory["name"],
                "extension": inventory["extension"],
                "size_bytes": inventory["size_bytes"],
            },
        )
    ]

    csv_preview = file_info.get("csv_preview")
    if csv_preview is not None:
        if not isinstance(csv_preview, dict):
            raise EvidenceModelError(f"csv_preview must be an object for {source_file}")
        csv_values = _require_fields(
            csv_preview,
            ["columns", "column_count", "row_count", "first_row_preview"],
            f"{source_file}.csv_preview",
        )
        records.append(
            _build_record(
                source_file=source_file,
                evidence_type="csv_structure",
                location={"path": source_file, "scope": "table"},
                extraction_method="input_scanner.read_csv_preview",
                observed_value={
                    "columns": csv_values["columns"],
                    "column_count": csv_values["column_count"],
                    "row_count": csv_values["row_count"],
                    "first_row_preview": csv_values["first_row_preview"],
                },
            )
        )

    json_preview = file_info.get("json_preview")
    if json_preview is not None:
        if not isinstance(json_preview, dict):
            raise EvidenceModelError(f"json_preview must be an object for {source_file}")
        json_values = _require_fields(
            json_preview,
            ["json_type", "top_level_keys", "item_count", "preview"],
            f"{source_file}.json_preview",
        )
        records.append(
            _build_record(
                source_file=source_file,
                evidence_type="json_structure",
                location={"path": source_file, "scope": "json_document"},
                extraction_method="input_scanner.read_json_preview",
                observed_value={
                    "json_type": json_values["json_type"],
                    "top_level_keys": json_values["top_level_keys"],
                    "item_count": json_values["item_count"],
                    "preview": json_values["preview"],
                },
            )
        )

    jsonl_preview = file_info.get("jsonl_preview")
    if jsonl_preview is not None:
        if not isinstance(jsonl_preview, dict):
            raise EvidenceModelError(f"jsonl_preview must be an object for {source_file}")
        jsonl_values = _require_fields(
            jsonl_preview,
            ["line_count", "preview_rows", "parse_errors"],
            f"{source_file}.jsonl_preview",
        )
        records.append(
            _build_record(
                source_file=source_file,
                evidence_type="jsonl_structure",
                location={"path": source_file, "scope": "json_lines"},
                extraction_method="input_scanner.read_jsonl_preview",
                observed_value={
                    "line_count": jsonl_values["line_count"],
                    "preview_rows": jsonl_values["preview_rows"],
                    "parse_errors": jsonl_values["parse_errors"],
                },
            )
        )

    document_excerpt = file_info.get("document_excerpt")
    if document_excerpt is not None:
        if not isinstance(document_excerpt, dict):
            raise EvidenceModelError(f"document_excerpt must be an object for {source_file}")
        document_values = _require_fields(
            document_excerpt,
            ["char_count", "excerpt", "truncated"],
            f"{source_file}.document_excerpt",
        )
        excerpt = document_values["excerpt"]
        if not isinstance(excerpt, str):
            raise EvidenceModelError(f"document_excerpt.excerpt must be a string for {source_file}")
        records.append(
            _build_record(
                source_file=source_file,
                evidence_type="document_excerpt",
                location={
                    "path": source_file,
                    "scope": "excerpt",
                    "char_start": 0,
                    "char_end": len(excerpt),
                },
                extraction_method="input_scanner.read_document_excerpt",
                observed_value={
                    "char_count": document_values["char_count"],
                    "excerpt": excerpt,
                    "truncated": document_values["truncated"],
                },
            )
        )

    document_chunks = file_info.get("document_chunks")
    if document_chunks is not None:
        if not isinstance(document_chunks, list):
            raise EvidenceModelError(f"document_chunks must be a list for {source_file}")
        for chunk in document_chunks:
            if not isinstance(chunk, dict):
                raise EvidenceModelError(f"document_chunks items must be objects for {source_file}")
            chunk_values = _require_fields(
                chunk,
                ["char_start", "char_end", "text"],
                f"{source_file}.document_chunks",
            )
            char_start = chunk_values["char_start"]
            char_end = chunk_values["char_end"]
            text = chunk_values["text"]
            if not isinstance(char_start, int) or not isinstance(char_end, int):
                raise EvidenceModelError(f"document chunk char range must be integers for {source_file}")
            if char_start < 0 or char_end < char_start:
                raise EvidenceModelError(f"document chunk char range is invalid for {source_file}")
            if not isinstance(text, str):
                raise EvidenceModelError(f"document chunk text must be a string for {source_file}")
            records.append(
                _build_record(
                    source_file=source_file,
                    evidence_type=f"document_chunk:{char_start}:{char_end}",
                    location={
                        "path": source_file,
                        "scope": "document_chunk",
                        "char_start": char_start,
                        "char_end": char_end,
                    },
                    extraction_method="input_scanner.read_document_chunks",
                    observed_value={"text": text},
                )
            )

    preview_error = file_info.get("preview_error")
    if preview_error is not None:
        if not isinstance(preview_error, str):
            raise EvidenceModelError(f"preview_error must be a string for {source_file}")
        records.append(
            _build_record(
                source_file=source_file,
                evidence_type="preview_error",
                location={"path": source_file, "scope": "preview"},
                extraction_method="input_scanner.preview_error",
                observed_value=preview_error,
            )
        )

    return records


def _require_fields(mapping: dict[str, Any], fields: list[str], context: str) -> dict[str, Any]:
    missing = [field for field in fields if field not in mapping]
    if missing:
        raise EvidenceModelError(f"Missing required fields in {context}: {', '.join(missing)}")
    return {field: mapping[field] for field in fields}


def _build_record(
    *,
    source_file: str,
    evidence_type: str,
    location: dict[str, Any],
    extraction_method: str,
    observed_value: Any,
) -> dict[str, Any]:
    record = {
        "key": f"file:{source_file}:{evidence_type}",
        "status": STATUS_OBSERVED,
        "source_actor": SOURCE_ACTOR_DETERMINISTIC,
        "source_file": source_file,
        "source_type": SOURCE_TYPE_CONTEST_FILE,
        "location": location,
        "extraction_method": extraction_method,
        "observed_value": observed_value,
        "confidence": CONFIDENCE_HIGH,
    }
    record["evidence_id"] = build_evidence_id(record)
    return record


def _evidence_type_from_key(record: dict[str, Any]) -> str:
    source_file = record.get("source_file")
    key = record.get("key")
    if isinstance(source_file, str) and isinstance(key, str):
        prefix = f"file:{source_file}:"
        if key.startswith(prefix):
            suffix = key[len(prefix) :]
            if suffix.startswith("document_chunk:"):
                return "document_chunk"
            return suffix.split(":", 1)[0]
    return str(key).rsplit(":", 1)[-1]


def _render_observed_value(record: dict[str, Any]) -> str:
    value = record["observed_value"]
    if record["key"].endswith(":document_excerpt") and isinstance(value, dict):
        value = dict(value)
        excerpt = value.get("excerpt")
        if isinstance(excerpt, str) and len(excerpt) > 1200:
            value["excerpt"] = excerpt[:1200] + "\n...[truncated for markdown display]"
    rendered = to_simple_yaml(value)
    return rendered if rendered else "null"
