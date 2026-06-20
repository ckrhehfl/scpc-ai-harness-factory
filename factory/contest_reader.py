from __future__ import annotations

from pathlib import Path
import csv
from typing import Any
from factory.utils import read_text_if_exists


def parse_scalar(value: str) -> Any:
    text = value.strip()
    if text == "":
        return ""
    lowered = text.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "none"}:
        return None
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        return text[1:-1]
    return text


def read_simple_yaml(path: Path) -> dict[str, Any]:
    """Read the small YAML subset used by contest_overrides.yaml.

    Supported shapes are nested mappings and scalar lists with two-space indentation.
    This keeps the project dependency-free while avoiding ad hoc string matching in
    the spec builder.
    """
    if not path.exists():
        return {}

    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any] | list[Any]]] = [(-1, root)]
    lines = [
        line.split("#", 1)[0].rstrip()
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
    meaningful_lines = [line for line in lines if line.strip()]

    for index, raw_line in enumerate(meaningful_lines):
        line_without_comment = raw_line.rstrip()

        indent = len(line_without_comment) - len(line_without_comment.lstrip(" "))
        line = line_without_comment.strip()

        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]

        if line.startswith("- "):
            if not isinstance(parent, list):
                raise ValueError(f"YAML list item without list parent in {path}: {raw_line}")
            parent.append(parse_scalar(line[2:]))
            continue

        if ":" not in line:
            raise ValueError(f"Unsupported YAML line in {path}: {raw_line}")

        key, raw_value = line.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if not isinstance(parent, dict):
            raise ValueError(f"YAML mapping item under list is unsupported in {path}: {raw_line}")

        if raw_value:
            parent[key] = parse_scalar(raw_value)
            continue

        next_container: dict[str, Any] | list[Any] = {}
        if index + 1 < len(meaningful_lines):
            next_line = meaningful_lines[index + 1]
            next_indent = len(next_line) - len(next_line.lstrip(" "))
            if next_indent > indent and next_line.strip().startswith("- "):
                next_container = []
        parent[key] = next_container
        stack.append((indent, next_container))

        continue

    return root


def read_csv_meta(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "columns": [], "row_count": 0}

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        try:
            columns = next(reader)
        except StopIteration:
            columns = []
            row_count = 0
            first_row = {}
        else:
            rows = list(reader)
            row_count = len(rows)
            first_row = dict(zip(columns, rows[0])) if rows else {}

    return {
        "path": str(path),
        "exists": True,
        "columns": columns,
        "row_count": row_count,
        "first_row": first_row,
    }


def read_contest_folder(contest_path: str | Path) -> dict[str, Any]:
    root = Path(contest_path)
    if not root.exists():
        raise FileNotFoundError(f"Contest folder not found: {root}")

    return {
        "root": str(root),
        "description": read_text_if_exists(root / "description.md"),
        "rules": read_text_if_exists(root / "rules.md"),
        "evaluation": read_text_if_exists(root / "evaluation.md"),
        "overrides": read_simple_yaml(root / "contest_overrides.yaml"),
        "overrides_path": str(root / "contest_overrides.yaml"),
        "files": {
            "train": read_csv_meta(root / "train.csv"),
            "test": read_csv_meta(root / "test.csv"),
            "sample_submission": read_csv_meta(root / "sample_submission.csv"),
        },
        "all_files": sorted(p.name for p in root.iterdir() if p.is_file()),
    }
