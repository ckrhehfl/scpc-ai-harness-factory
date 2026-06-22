from __future__ import annotations

import argparse
from pathlib import Path
import json
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from factory.approval_model import ApprovalModelError
from factory.human_approval_builder import (
    build_human_approval_intake_template,
    build_human_approval_summary,
    load_human_approval_intake,
    load_validation_report,
    save_human_approval_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Human Approval Summary and local readiness gate artifacts.")
    parser.add_argument("--requirements", required=True, help="Contest Requirements JSON")
    parser.add_argument("--matches", required=True, help="Requirement Capability Match JSON")
    parser.add_argument("--decision-ledger", required=True, help="Decision Ledger JSON")
    parser.add_argument("--capabilities", required=True, help="Capability Registry JSON")
    parser.add_argument("--validation-report", help="Optional local submission validation report JSON")
    parser.add_argument("--approval-intake", help="Optional human approval intake JSON")
    parser.add_argument("--output", default="generated", help="Output directory")
    args = parser.parse_args()

    try:
        requirements = _load_json(args.requirements, "contest_requirements.json")
        matches = _load_json(args.matches, "requirement_capability_match.json")
        decision_ledger = _load_json(args.decision_ledger, "decision_ledger.json")
        capabilities = _load_json(args.capabilities, "capability_registry.json")
        validation_report = load_validation_report(args.validation_report) if args.validation_report else None
        approval_intake = load_human_approval_intake(args.approval_intake) if args.approval_intake else None
        summary = build_human_approval_summary(
            requirements,
            matches,
            decision_ledger,
            capabilities,
            validation_report=validation_report,
            approval_intake=approval_intake,
        )
        template = build_human_approval_intake_template(summary)
        paths = save_human_approval_outputs(summary, template, args.output)
    except (ApprovalModelError, OSError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print("[OK] Human approval summary generated")
    print(f"- Summary JSON: {paths['summary_json']}")
    print(f"- Summary MD: {paths['summary_md']}")
    print(f"- Approval template: {paths['approval_template']}")
    print(f"- Machine readiness: {summary['machine_readiness']['status']}")
    print(f"- Human approval: {summary['human_approval']['status']}")
    print(f"- Overall gate: {summary['overall_gate']['status']}")
    print(f"- Blockers: {summary['machine_readiness']['blocker_count']}")
    print(f"- Warnings: {summary['machine_readiness']['warning_count'] + len(summary['warnings'])}")
    return summary["overall_gate"]["exit_code"]


def _load_json(path: str, label: str) -> dict:
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ApprovalModelError(f"Malformed JSON in {label}: {exc}") from exc
    except OSError as exc:
        raise ApprovalModelError(f"Could not read {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise ApprovalModelError(f"{label} must be a JSON object")
    return data


if __name__ == "__main__":
    raise SystemExit(main())
