from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from factory.contest_requirement_builder import (
    build_contest_requirements,
    load_contest_spec,
    load_coverage,
    load_evidence_index,
    render_contest_requirements_markdown,
)
from factory.requirement_capability_matcher import (
    load_json,
    match_requirements_to_capabilities,
    render_requirement_capability_match_markdown,
    validate_capability_registry,
)
from factory.requirement_model import (
    RequirementModelError,
    save_match_artifact,
    save_requirements_artifact,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Contest Requirements and exact-token Capability Match artifacts.")
    parser.add_argument("--contest-spec", required=True, help="ContestSpec JSON")
    parser.add_argument("--evidence-index", required=True, help="Evidence Index JSON")
    parser.add_argument("--capabilities", required=True, help="Capability Registry JSON")
    parser.add_argument("--coverage", help="Optional Contest Package Coverage JSON")
    parser.add_argument("--output", default="generated", help="Output directory")
    args = parser.parse_args()

    try:
        contest_spec = load_contest_spec(args.contest_spec)
        evidence_index = load_evidence_index(args.evidence_index)
        capability_registry = load_json(args.capabilities, "capability_registry.json")
        validate_capability_registry(capability_registry)
        coverage = load_coverage(args.coverage) if args.coverage else None

        requirements = build_contest_requirements(
            contest_spec,
            evidence_index,
            coverage=coverage,
            source_artifacts={
                "contest_spec": _display_path(args.contest_spec),
                "evidence_index": _display_path(args.evidence_index),
                "coverage": _display_path(args.coverage) if args.coverage else None,
            },
        )
        match = match_requirements_to_capabilities(
            requirements,
            capability_registry,
            contest_spec,
            source_requirements=_display_path(str(Path(args.output) / "contest_requirements.json")),
            source_capabilities=_display_path(args.capabilities),
        )

        req_md = render_contest_requirements_markdown(requirements)
        match_md = render_requirement_capability_match_markdown(match, requirements["requirements"])
        req_paths = save_requirements_artifact(requirements, args.output, req_md)
        match_paths = save_match_artifact(match, args.output, match_md, requirements["requirements"])
    except (RequirementModelError, OSError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    summary = match["summary"]
    print("[OK] Requirement contract and capability match generated")
    print(f"- Requirements JSON: {req_paths['json']}")
    print(f"- Requirements MD: {req_paths['md']}")
    print(f"- Match JSON: {match_paths['json']}")
    print(f"- Match MD: {match_paths['md']}")
    print(f"- Requirements: {requirements['summary']['total']}")
    print(f"- Satisfied: {summary['satisfied']}")
    print(f"- Partial: {summary['partial']}")
    print(f"- Unmet: {summary['unmet']}")
    print(f"- Active must gaps: {summary['active_must_gap_count']}")
    print(f"- Pending high-risk: {summary['pending_high_risk_count']}")
    return 2 if summary["active_must_gap_count"] else 0


def _display_path(path_text: str | None) -> str | None:
    if path_text is None:
        return None
    path = Path(path_text)
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except (OSError, ValueError):
        return path.as_posix() if not path.is_absolute() else path.name


if __name__ == "__main__":
    raise SystemExit(main())
