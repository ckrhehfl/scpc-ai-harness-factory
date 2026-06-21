from __future__ import annotations

from pathlib import Path
from typing import Any
import csv
import json

from factory.utils import read_text_if_exists, write_json, write_text
from factory.contest_package_manifest import (
    build_manifest_source_map,
    load_contest_package_manifest,
)


DOCUMENT_EXTENSIONS = {".md", ".txt", ".rst"}
CSV_EXTENSIONS = {".csv", ".tsv"}
JSON_EXTENSIONS = {".json"}
JSONL_EXTENSIONS = {".jsonl", ".ndjson"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
ARCHIVE_EXTENSIONS = {".zip", ".tar", ".gz", ".tgz", ".7z", ".rar"}
DOCUMENT_BINARY_EXTENSIONS = {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}

DOC_ROLE_NAMES = {
    "description.md": "description_document",
    "rules.md": "rules_document",
    "evaluation.md": "evaluation_document",
    "readme.md": "readme_document",
}
DATA_ROLE_NAMES = {
    "train.csv": "train_data",
    "test.csv": "test_data",
    "sample_submission.csv": "sample_submission",
    "contest_overrides.yaml": "contest_overrides",
    "contest_overrides.yml": "contest_overrides",
}


def infer_file_kind(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in CSV_EXTENSIONS:
        return "csv"
    if suffix in JSON_EXTENSIONS:
        return "json"
    if suffix in JSONL_EXTENSIONS:
        return "jsonl"
    if suffix in DOCUMENT_EXTENSIONS:
        return "document"
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in ARCHIVE_EXTENSIONS:
        return "archive"
    if suffix in DOCUMENT_BINARY_EXTENSIONS:
        return "binary_document"
    if suffix in {".yaml", ".yml"}:
        return "config"
    return "unknown"


def infer_role_candidates(relative_path: str, file_kind: str) -> list[str]:
    name = Path(relative_path).name.lower()
    roles: list[str] = []
    if name in DOC_ROLE_NAMES:
        roles.append(DOC_ROLE_NAMES[name])
    if name in DATA_ROLE_NAMES:
        roles.append(DATA_ROLE_NAMES[name])
    if file_kind in {"json", "jsonl"}:
        roles.append(f"{file_kind}_data_candidate")
    if file_kind in {"image", "archive", "binary_document"}:
        roles.append(f"{file_kind}_file_candidate")
    if file_kind == "document" and not roles:
        roles.append("supporting_document")
    if not roles:
        roles.append("unknown")
    return roles


def read_csv_preview(path: Path, *, max_preview_rows: int = 3) -> dict[str, Any]:
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        columns = list(reader.fieldnames or [])
        preview_rows: list[dict[str, str]] = []
        row_count = 0
        for row in reader:
            row_count += 1
            if len(preview_rows) < max_preview_rows:
                preview_rows.append(dict(row))
    return {
        "columns": columns,
        "column_count": len(columns),
        "row_count": row_count,
        "first_row_preview": preview_rows[0] if preview_rows else {},
        "preview_rows": preview_rows,
    }


def compact_json_preview(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): compact_json_preview(v) for k, v in list(value.items())[:10]}
    if isinstance(value, list):
        return [compact_json_preview(v) for v in value[:3]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def read_json_preview(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if isinstance(data, dict):
        top_level_type = "object"
        keys = list(data.keys())[:20]
        item_count = len(data)
    elif isinstance(data, list):
        top_level_type = "array"
        keys = []
        item_count = len(data)
    else:
        top_level_type = type(data).__name__
        keys = []
        item_count = None
    return {
        "json_type": top_level_type,
        "top_level_keys": keys,
        "item_count": item_count,
        "preview": compact_json_preview(data),
    }


def read_jsonl_preview(path: Path, *, max_preview_rows: int = 3) -> dict[str, Any]:
    preview_rows: list[Any] = []
    line_count = 0
    parse_errors: list[str] = []
    with path.open("r", encoding="utf-8-sig") as f:
        for line_number, line in enumerate(f, start=1):
            if not line.strip():
                continue
            line_count += 1
            if len(preview_rows) >= max_preview_rows:
                continue
            try:
                preview_rows.append(compact_json_preview(json.loads(line)))
            except json.JSONDecodeError as exc:
                parse_errors.append(f"line {line_number}: {exc.msg}")
    return {
        "line_count": line_count,
        "preview_rows": preview_rows,
        "parse_errors": parse_errors[:5],
    }


def read_document_excerpt(path: Path, *, max_chars: int = 4000) -> dict[str, Any]:
    text = read_text_if_exists(path)
    return {
        "char_count": len(text),
        "excerpt": text[:max_chars],
        "truncated": len(text) > max_chars,
    }


def read_document_chunks(path: Path, *, chunk_size: int = 4000) -> list[dict[str, Any]]:
    text = read_text_if_exists(path)
    return [
        {
            "char_start": start,
            "char_end": min(start + chunk_size, len(text)),
            "text": text[start : min(start + chunk_size, len(text))],
        }
        for start in range(0, len(text), chunk_size)
    ]


def manifest_kind_warnings(relative_path: str, file_kind: str, declared: dict[str, Any]) -> list[str]:
    source_kind = declared.get("source_kind")
    if source_kind in {None, "unknown"}:
        return []
    compatible = {
        "document": {"document", "binary_document"},
        "image": {"image"},
        "archive": {"archive"},
        "data": {"csv", "json", "jsonl"},
        "config": {"config", "json"},
    }
    if file_kind not in compatible.get(str(source_kind), set()):
        return [
            f"source_kind {source_kind!r} does not match scanner file_kind {file_kind!r} for {relative_path}"
        ]
    return []


def scan_file(path: Path, root: Path, source_map: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    relative_path = path.relative_to(root).as_posix()
    suffix = path.suffix.lower()
    file_kind = infer_file_kind(path)
    stat = path.stat()
    info: dict[str, Any] = {
        "path": relative_path,
        "absolute_path": str(path),
        "name": path.name,
        "extension": suffix,
        "size_bytes": stat.st_size,
        "file_kind": file_kind,
        "role_candidates": infer_role_candidates(relative_path, file_kind),
    }
    if source_map and relative_path in source_map:
        info["declared_source"] = source_map[relative_path]
        warnings = manifest_kind_warnings(relative_path, file_kind, source_map[relative_path])
        if warnings:
            info["declared_source_warnings"] = warnings

    try:
        if file_kind == "csv":
            info["csv_preview"] = read_csv_preview(path)
        elif file_kind == "json":
            info["json_preview"] = read_json_preview(path)
        elif file_kind == "jsonl":
            info["jsonl_preview"] = read_jsonl_preview(path)
        elif file_kind == "document":
            info["document_excerpt"] = read_document_excerpt(path)
            info["document_chunks"] = read_document_chunks(path)
    except UnicodeDecodeError as exc:
        info["preview_error"] = f"text_decode_error: {exc}"
    except (csv.Error, json.JSONDecodeError, OSError) as exc:
        info["preview_error"] = f"preview_failed: {exc}"

    return info


def scan_contest_inputs(contest_path: str | Path) -> dict[str, Any]:
    root = Path(contest_path)
    if not root.exists():
        raise FileNotFoundError(f"Contest folder not found: {root}")

    manifest = load_contest_package_manifest(root)
    source_map = build_manifest_source_map(manifest)
    files = [scan_file(path, root, source_map) for path in sorted(root.rglob("*")) if path.is_file()]
    documents = {
        name: read_text_if_exists(root / name)
        for name in ["description.md", "rules.md", "evaluation.md"]
        if (root / name).exists()
    }
    by_kind: dict[str, int] = {}
    by_role: dict[str, int] = {}
    for file_info in files:
        by_kind[file_info["file_kind"]] = by_kind.get(file_info["file_kind"], 0) + 1
        for role in file_info.get("role_candidates", []):
            by_role[role] = by_role.get(role, 0) + 1

    return {
        "contest_path": str(root),
        "file_count": len(files),
        "files": files,
        "documents": documents,
        "contest_package_manifest": manifest,
        "summary": {
            "by_kind": by_kind,
            "by_role": by_role,
            "has_description": "description.md" in documents,
            "has_rules": "rules.md" in documents,
            "has_evaluation": "evaluation.md" in documents,
            "manifest_present": manifest is not None,
        },
    }


def render_input_scan_report_markdown(scan: dict[str, Any]) -> str:
    lines = [
        "# Input Scan Report",
        "",
        f"- contest_path: {scan.get('contest_path')}",
        f"- file_count: {scan.get('file_count')}",
        "",
        "## File Summary",
        "",
    ]
    for kind, count in sorted(scan.get("summary", {}).get("by_kind", {}).items()):
        lines.append(f"- {kind}: {count}")
    lines.extend(["", "## Files", ""])
    for file_info in scan.get("files", []):
        roles = ", ".join(file_info.get("role_candidates", []))
        lines.append(
            f"- `{file_info.get('path')}` / kind={file_info.get('file_kind')} / "
            f"size={file_info.get('size_bytes')} / roles={roles}"
        )
        csv_preview = file_info.get("csv_preview")
        if csv_preview:
            lines.append(
                f"  - columns={csv_preview.get('columns')} / rows={csv_preview.get('row_count')} / "
                f"first_row={csv_preview.get('first_row_preview')}"
            )
        json_preview = file_info.get("json_preview")
        if json_preview:
            lines.append(
                f"  - json_type={json_preview.get('json_type')} / keys={json_preview.get('top_level_keys')}"
            )
        jsonl_preview = file_info.get("jsonl_preview")
        if jsonl_preview:
            lines.append(f"  - jsonl_lines={jsonl_preview.get('line_count')}")
        if file_info.get("preview_error"):
            lines.append(f"  - preview_error={file_info.get('preview_error')}")
    lines.append("")
    return "\n".join(lines)


def save_input_scan_report(scan: dict[str, Any], output_dir: str | Path) -> tuple[Path, Path]:
    out = Path(output_dir)
    json_path = write_json(out / "input_scan_report.json", scan)
    md_path = write_text(out / "input_scan_report.md", render_input_scan_report_markdown(scan))
    return json_path, md_path
