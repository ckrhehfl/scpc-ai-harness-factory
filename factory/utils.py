from __future__ import annotations

from pathlib import Path
from typing import Any
import json


def ensure_dir(path: str | Path) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_text(path: str | Path, text: str) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def read_text_if_exists(path: str | Path) -> str:
    p = Path(path)
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8")


def write_json(path: str | Path, data: Any) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def to_simple_yaml(data: Any, indent: int = 0) -> str:
    """Small YAML writer for simple dictionaries/lists/scalars.

    This avoids requiring PyYAML for the MVP. It is not a full YAML serializer.
    """
    spaces = "  " * indent
    if isinstance(data, dict):
        lines: list[str] = []
        for key, value in data.items():
            if value == []:
                lines.append(f"{spaces}{key}: []")
            elif value == {}:
                lines.append(f"{spaces}{key}: {{}}")
            elif isinstance(value, (dict, list)):
                lines.append(f"{spaces}{key}:")
                lines.append(to_simple_yaml(value, indent + 1))
            else:
                lines.append(f"{spaces}{key}: {format_scalar(value)}")
        return "\n".join(lines)
    if isinstance(data, list):
        lines = []
        for item in data:
            if isinstance(item, dict):
                lines.append(f"{spaces}-")
                lines.append(to_simple_yaml(item, indent + 1))
            elif isinstance(item, list):
                lines.append(f"{spaces}-")
                lines.append(to_simple_yaml(item, indent + 1))
            else:
                lines.append(f"{spaces}- {format_scalar(item)}")
        return "\n".join(lines)
    return f"{spaces}{format_scalar(data)}"


def format_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if text == "" or any(ch in text for ch in [":", "#", "\n", "[", "]", "{", "}"]):
        return json.dumps(text, ensure_ascii=False)
    return text
