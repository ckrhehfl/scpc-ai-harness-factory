from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any
import ast
import re


SCHEMA_VERSION = "v0.10A"
DEFINITION_ARTIFACT_TYPE = "capability_registry_definition"
REGISTRY_ARTIFACT_TYPE = "capability_registry"

CAPABILITY_ID_RE = re.compile(r"^cap\.[a-z0-9_]+(?:\.[a-z0-9_]+)+$")
TOKEN_RE = re.compile(r"^[a-z0-9_]+(?:\.[a-z0-9_]+)+$")
WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")

ALLOWED_SCOPES = {"factory", "generated_harness"}
ALLOWED_CATEGORIES = {
    "intake",
    "normalization",
    "analysis",
    "governance",
    "design",
    "generation",
    "runtime",
    "verification",
    "handoff",
    "audit",
}
ALLOWED_DECLARED_STATUSES = {"implemented", "partial", "planned", "deprecated"}
ALLOWED_BLOCKED_ROOTS = {".git", "generated", "runs", ".venv", "contests"}
SECRET_MARKERS = {"secret", "secrets", "credential", "credentials"}


class CapabilityModelError(ValueError):
    pass


def validate_capability_definition(definition: dict[str, Any]) -> None:
    if not isinstance(definition, dict):
        raise CapabilityModelError("Capability definition must be a JSON object")
    if definition.get("schema_version") != SCHEMA_VERSION:
        raise CapabilityModelError(f"Unsupported schema_version: {definition.get('schema_version')}")
    if definition.get("artifact_type") != DEFINITION_ARTIFACT_TYPE:
        raise CapabilityModelError(f"Unsupported artifact_type: {definition.get('artifact_type')}")

    capabilities = definition.get("capabilities")
    if not isinstance(capabilities, list):
        raise CapabilityModelError("Field 'capabilities' must be a list")

    ids: list[str] = []
    for index, capability in enumerate(capabilities):
        if not isinstance(capability, dict):
            raise CapabilityModelError(f"capabilities[{index}] must be an object")
        _validate_capability_record(capability, index)
        ids.append(capability["capability_id"])

    duplicates = sorted({item for item in ids if ids.count(item) > 1})
    if duplicates:
        raise CapabilityModelError(f"Duplicate capability_id(s): {', '.join(duplicates)}")

    id_set = set(ids)
    for capability in capabilities:
        capability_id = capability["capability_id"]
        dependencies = capability.get("dependencies", [])
        for dependency in dependencies:
            if dependency == capability_id:
                raise CapabilityModelError(f"{capability_id} must not depend on itself")
            if dependency not in id_set:
                raise CapabilityModelError(f"{capability_id} depends on unknown capability_id: {dependency}")
    _validate_dependency_cycles(capabilities)


def validate_evidence_path_text(path_text: Any) -> str:
    if not isinstance(path_text, str) or not path_text:
        raise CapabilityModelError("Evidence path must be a non-empty string")
    normalized = path_text.replace("\\", "/")
    if normalized != path_text:
        raise CapabilityModelError(f"Evidence path must be POSIX relative: {path_text}")
    if normalized in {".", ".."}:
        raise CapabilityModelError(f"Evidence path is not safe: {path_text}")
    if normalized.startswith("/") or WINDOWS_DRIVE_RE.match(normalized):
        raise CapabilityModelError(f"Evidence path must be relative: {path_text}")

    pure_path = PurePosixPath(normalized)
    parts = pure_path.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise CapabilityModelError(f"Evidence path is not safe: {path_text}")
    if pure_path.as_posix() != normalized:
        raise CapabilityModelError(f"Evidence path must be normalized: {path_text}")

    lowered = [part.lower() for part in parts]
    if lowered[0] in ALLOWED_BLOCKED_ROOTS:
        raise CapabilityModelError(f"Evidence path uses blocked root: {path_text}")
    filename = lowered[-1]
    if filename == ".env" or filename.startswith(".env."):
        raise CapabilityModelError(f"Evidence path uses blocked env file: {path_text}")
    if any(marker in part for part in lowered for marker in SECRET_MARKERS):
        raise CapabilityModelError(f"Evidence path uses blocked secret or credential location: {path_text}")
    return normalized


def resolve_evidence_file(repo_root: str | Path, path_text: str) -> Path:
    normalized = validate_evidence_path_text(path_text)
    root = Path(repo_root).resolve()
    candidate = root / normalized
    if candidate.exists():
        resolved = candidate.resolve()
        if resolved == root or root not in resolved.parents:
            raise CapabilityModelError(f"Evidence path escapes repository root: {path_text}")
        if resolved.is_dir():
            raise CapabilityModelError(f"Evidence path must be a file, not a directory: {path_text}")
        return resolved
    return candidate


def python_top_level_symbols(path: str | Path) -> set[str]:
    source_path = Path(path)
    try:
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    except SyntaxError as exc:
        raise CapabilityModelError(f"Python syntax error in {source_path.name}: {exc.msg}") from exc
    except OSError as exc:
        raise CapabilityModelError(f"Could not read Python evidence file: {exc}") from exc
    symbols: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.add(node.name)
    return symbols


def _validate_capability_record(capability: dict[str, Any], index: int) -> None:
    context = f"capabilities[{index}]"
    capability_id = _require_non_empty_string(capability, "capability_id", context)
    if not CAPABILITY_ID_RE.match(capability_id):
        raise CapabilityModelError(f"Invalid capability_id: {capability_id}")

    _require_non_empty_string(capability, "name", capability_id)
    scope = _require_non_empty_string(capability, "scope", capability_id)
    if scope not in ALLOWED_SCOPES:
        raise CapabilityModelError(f"Invalid scope for {capability_id}: {scope}")
    category = _require_non_empty_string(capability, "category", capability_id)
    if category not in ALLOWED_CATEGORIES:
        raise CapabilityModelError(f"Invalid category for {capability_id}: {category}")
    status = _require_non_empty_string(capability, "declared_status", capability_id)
    if status not in ALLOWED_DECLARED_STATUSES:
        raise CapabilityModelError(f"Invalid declared_status for {capability_id}: {status}")
    _require_non_empty_string(capability, "description", capability_id)

    provides = _require_string_list(capability, "provides", capability_id, min_items=1)
    _validate_unique(provides, f"{capability_id}.provides")
    for token in provides:
        if not TOKEN_RE.match(token):
            raise CapabilityModelError(f"Invalid provides token for {capability_id}: {token}")

    for field in ["inputs", "outputs", "limitations", "tags", "risk_gates"]:
        _require_string_list(capability, field, capability_id)
    for gate in capability.get("risk_gates", []):
        if not TOKEN_RE.match(gate):
            raise CapabilityModelError(f"Invalid risk gate for {capability_id}: {gate}")
    dependencies = _require_string_list(capability, "dependencies", capability_id)
    _validate_unique(dependencies, f"{capability_id}.dependencies")
    for dependency in dependencies:
        if not CAPABILITY_ID_RE.match(dependency):
            raise CapabilityModelError(f"Invalid dependency id for {capability_id}: {dependency}")

    implementation = _validate_evidence_list(capability, "implementation_evidence", capability_id)
    tests = _validate_evidence_list(capability, "test_evidence", capability_id)
    if status == "implemented":
        if not implementation:
            raise CapabilityModelError(f"{capability_id} is implemented but has no implementation_evidence")
        if not tests:
            raise CapabilityModelError(f"{capability_id} is implemented but has no test_evidence")
    if not capability.get("limitations"):
        raise CapabilityModelError(f"{capability_id} must include at least one limitation")


def _validate_evidence_list(capability: dict[str, Any], field: str, capability_id: str) -> list[dict[str, Any]]:
    value = capability.get(field)
    if not isinstance(value, list):
        raise CapabilityModelError(f"{capability_id}.{field} must be a list")
    for index, entry in enumerate(value):
        if not isinstance(entry, dict):
            raise CapabilityModelError(f"{capability_id}.{field}[{index}] must be an object")
        validate_evidence_path_text(entry.get("path"))
        symbols = entry.get("symbols")
        if not isinstance(symbols, list) or not symbols:
            raise CapabilityModelError(f"{capability_id}.{field}[{index}].symbols must be a non-empty list")
        _validate_unique(symbols, f"{capability_id}.{field}[{index}].symbols")
        for symbol in symbols:
            if not isinstance(symbol, str) or not symbol.strip():
                raise CapabilityModelError(f"{capability_id}.{field}[{index}] has an invalid symbol")
    return value


def _validate_dependency_cycles(capabilities: list[dict[str, Any]]) -> None:
    graph = {
        capability["capability_id"]: list(capability.get("dependencies", []))
        for capability in capabilities
    }
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str, stack: list[str]) -> None:
        if node in visited:
            return
        if node in visiting:
            cycle = stack[stack.index(node):] + [node]
            raise CapabilityModelError(f"Dependency cycle detected: {' -> '.join(cycle)}")
        visiting.add(node)
        for dependency in graph[node]:
            visit(dependency, stack + [dependency])
        visiting.remove(node)
        visited.add(node)

    for node in sorted(graph):
        visit(node, [node])


def _require_non_empty_string(mapping: dict[str, Any], field: str, context: str) -> str:
    value = mapping.get(field)
    if not isinstance(value, str) or not value.strip():
        raise CapabilityModelError(f"{context}.{field} must be a non-empty string")
    return value


def _require_string_list(
    mapping: dict[str, Any],
    field: str,
    context: str,
    *,
    min_items: int = 0,
) -> list[str]:
    value = mapping.get(field)
    if not isinstance(value, list):
        raise CapabilityModelError(f"{context}.{field} must be a list")
    if len(value) < min_items:
        raise CapabilityModelError(f"{context}.{field} must not be empty")
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise CapabilityModelError(f"{context}.{field}[{index}] must be a non-empty string")
    return value


def _validate_unique(items: list[str], context: str) -> None:
    duplicates = sorted({item for item in items if items.count(item) > 1})
    if duplicates:
        raise CapabilityModelError(f"{context} contains duplicate value(s): {', '.join(duplicates)}")
