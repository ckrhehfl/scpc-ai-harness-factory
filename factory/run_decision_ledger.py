from __future__ import annotations

import argparse
from pathlib import Path
import json
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from factory.decision_ledger_builder import (
    build_decision_intake_template,
    build_decision_ledger,
    load_decision_intake,
    save_decision_outputs,
)
from factory.decision_model import DecisionModelError


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Decision Intake template and append-only Decision Ledger artifacts.")
    parser.add_argument("--requirements", required=True, help="Contest Requirements JSON")
    parser.add_argument("--matches", required=True, help="Requirement Capability Match JSON")
    parser.add_argument("--capabilities", required=True, help="Capability Registry JSON")
    parser.add_argument("--intake", help="Optional Decision Intake JSON")
    parser.add_argument("--output", default="generated", help="Output directory")
    args = parser.parse_args()

    try:
        requirements = _load_json(args.requirements, "contest_requirements.json")
        matches = _load_json(args.matches, "requirement_capability_match.json")
        capabilities = _load_json(args.capabilities, "capability_registry.json")
        intake = load_decision_intake(args.intake) if args.intake else None
        ledger = build_decision_ledger(requirements, matches, capabilities, intake)
        template = build_decision_intake_template(ledger)
        paths = save_decision_outputs(ledger, template, args.output)
    except (DecisionModelError, OSError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    summary = ledger["summary"]
    print("[OK] Decision ledger generated")
    print(f"- Ledger JSON: {paths['ledger_json']}")
    print(f"- Ledger MD: {paths['ledger_md']}")
    print(f"- Intake template: {paths['intake_template']}")
    print(f"- Records: {summary['total']}")
    print(f"- Decision required: {summary['decision_required']}")
    print(f"- Confirmed: {summary['confirmed']}")
    print(f"- Pending: {summary['pending']}")
    print(f"- Stale: {summary['stale']}")
    print(f"- Conflicting: {summary['conflicting']}")
    print(f"- Unresolved required: {summary['unresolved_required_count']}")
    print(f"- Follow-up required: {summary['follow_up_required_count']}")
    if summary["unresolved_required_count"] or summary["stale"] or summary["conflicting"]:
        return 2
    return 0


def _load_json(path: str, label: str) -> dict:
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DecisionModelError(f"Malformed JSON in {label}: {exc}") from exc
    except OSError as exc:
        raise DecisionModelError(f"Could not read {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise DecisionModelError(f"{label} must be a JSON object")
    return data


if __name__ == "__main__":
    raise SystemExit(main())
