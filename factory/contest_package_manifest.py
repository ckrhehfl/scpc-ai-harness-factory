from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any
import json
import re


SCHEMA_VERSION = "v0.9B"
MANIFEST_NAME = "contest_package.json"
ALLOWED_SOURCE_KINDS = {"document", "image", "data", "config", "archive", "unknown"}
ALLOWED_VISIBILITIES = {"public", "restricted", "private"}
WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")
DOTTED_STRING_RE = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$")


class ContestPackageManifestError(ValueError):
    pass


def load_contest_package_manifest(contest_path: str | Path) -> dict[str, Any] | None:
    root = Path(contest_path)
    manifest_path = root / MANIFEST_NAME
    if not manifest_path.exists():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContestPackageManifestError(f"Malformed contest_package.json: {exc}") from exc
    except OSError as exc:
        raise ContestPackageManifestError(f"Could not read contest_package.json: {exc}") from exc
    validate_contest_package_manifest(manifest, root)
    return manifest


def validate_contest_package_manifest(manifest: dict[str, Any], contest_root: str | Path) -> None:
    if not isinstance(manifest, dict):
        raise ContestPackageManifestError("Manifest must be a JSON object")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise ContestPackageManifestError(f"Unsupported schema_version: {manifest.get('schema_version')}")

    contest = manifest.get("contest")
    if not isinstance(contest, dict):
        raise ContestPackageManifestError("Manifest field 'contest' must be an object")
    _require_non_empty_string(contest, "name", "contest.name")
    _require_non_empty_string(contest, "phase", "contest.phase")
    if "platform" in contest and not isinstance(contest["platform"], str):
        raise ContestPackageManifestError("contest.platform must be a string when present")

    sources = manifest.get("sources")
    if not isinstance(sources, list):
        raise ContestPackageManifestError("Manifest field 'sources' must be a list")

    root = Path(contest_root)
    seen_paths: set[str] = set()
    for index, source in enumerate(sources):
        context = f"sources[{index}]"
        if not isinstance(source, dict):
            raise ContestPackageManifestError(f"{context} must be an object")
        relative_path = _validate_source_path(source.get("path"), context)
        if relative_path == MANIFEST_NAME:
            raise ContestPackageManifestError("contest_package.json must not be listed as a source")
        if relative_path in seen_paths:
            raise ContestPackageManifestError(f"Duplicate source path: {relative_path}")
        seen_paths.add(relative_path)
        _require_non_empty_string(source, "role", f"{context}.role")

        source_kind = source.get("source_kind")
        if source_kind not in ALLOWED_SOURCE_KINDS:
            raise ContestPackageManifestError(f"Invalid source_kind for {relative_path}: {source_kind}")
        visibility = source.get("visibility")
        if visibility not in ALLOWED_VISIBILITIES:
            raise ContestPackageManifestError(f"Invalid visibility for {relative_path}: {visibility}")
        if "origin" in source and not isinstance(source["origin"], str):
            raise ContestPackageManifestError(f"{context}.origin must be a string when present")
        if not (root / relative_path).is_file():
            raise ContestPackageManifestError(f"Manifest source file not found: {relative_path}")

    declared_unknowns = manifest.get("declared_unknowns", [])
    if not isinstance(declared_unknowns, list):
        raise ContestPackageManifestError("Manifest field 'declared_unknowns' must be a list")
    for index, item in enumerate(declared_unknowns):
        if not isinstance(item, str) or not DOTTED_STRING_RE.match(item):
            raise ContestPackageManifestError(
                f"declared_unknowns[{index}] must be a non-empty dotted string"
            )


def build_manifest_source_map(
    manifest: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    if manifest is None:
        return {}
    sources = manifest.get("sources", [])
    if not isinstance(sources, list):
        return {}
    source_map: dict[str, dict[str, Any]] = {}
    for source in sources:
        if not isinstance(source, dict):
            continue
        path = source.get("path")
        if isinstance(path, str):
            source_map[path] = {
                "role": source.get("role"),
                "source_kind": source.get("source_kind"),
                "visibility": source.get("visibility"),
                **({"origin": source["origin"]} if "origin" in source else {}),
            }
    return source_map


def _require_non_empty_string(mapping: dict[str, Any], field: str, context: str) -> None:
    value = mapping.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ContestPackageManifestError(f"{context} must be a non-empty string")


def _validate_source_path(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ContestPackageManifestError(f"{context}.path must be a non-empty string")
    normalized = value.replace("\\", "/")
    if normalized != value:
        raise ContestPackageManifestError(f"{context}.path must be a POSIX relative path")
    if normalized.startswith("/") or WINDOWS_DRIVE_RE.match(normalized):
        raise ContestPackageManifestError(f"{context}.path must be relative: {value}")
    pure_path = PurePosixPath(normalized)
    parts = pure_path.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ContestPackageManifestError(f"{context}.path is not safe: {value}")
    if pure_path.as_posix() != normalized:
        raise ContestPackageManifestError(f"{context}.path must be normalized: {value}")
    return normalized
