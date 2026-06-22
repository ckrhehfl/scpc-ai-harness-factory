from __future__ import annotations

import argparse
from pathlib import Path
import json
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from factory.handoff_model import HandoffModelError
from factory.submission_handoff_builder import (
    build_freeze_confirmation_template,
    build_submission_handoff,
    load_freeze_confirmation_intake,
    save_submission_handoff_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a deterministic local submission handoff package.")
    parser.add_argument("--submission", required=True, help="submission.csv path")
    parser.add_argument("--validation-report", required=True, help="validation_report.json path")
    parser.add_argument("--approval-summary", required=True, help="human_approval_summary.json path")
    parser.add_argument("--decision-ledger", required=True, help="decision_ledger.json path")
    parser.add_argument("--requirements", required=True, help="contest_requirements.json path")
    parser.add_argument("--matches", required=True, help="requirement_capability_match.json path")
    parser.add_argument("--capabilities", required=True, help="capability_registry.json path")
    parser.add_argument("--freeze-confirmation", help="Optional freeze confirmation intake JSON")
    parser.add_argument("--output", default="generated", help="Output directory")
    args = parser.parse_args()

    try:
        manifest, package_files = build_submission_handoff(
            submission_path=args.submission,
            validation_report=_load_json(args.validation_report, "validation_report.json"),
            human_approval_summary=_load_json(args.approval_summary, "human_approval_summary.json"),
            decision_ledger=_load_json(args.decision_ledger, "decision_ledger.json"),
            requirements=_load_json(args.requirements, "contest_requirements.json"),
            matches=_load_json(args.matches, "requirement_capability_match.json"),
            capabilities=_load_json(args.capabilities, "capability_registry.json"),
            freeze_confirmation=load_freeze_confirmation_intake(args.freeze_confirmation),
        )
        template = build_freeze_confirmation_template(manifest)
        paths = save_submission_handoff_outputs(manifest, template, package_files, args.output)
    except (HandoffModelError, OSError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    package_dir = paths["package_dir"] if package_files else "not generated"
    package_zip = paths["package_zip"] if package_files else "not generated"
    print("[OK] Submission handoff evaluated")
    print(f"- Manifest JSON: {paths['manifest_json']}")
    print(f"- Manifest MD: {paths['manifest_md']}")
    print(f"- Freeze template: {paths['freeze_template']}")
    print(f"- Package directory: {package_dir}")
    print(f"- Package archive: {package_zip}")
    print(f"- Handoff status: {manifest['status']}")
    print(f"- Preflight blockers: {manifest['preflight']['blocker_count']}")
    print(f"- Candidate digest: {manifest['candidate']['candidate_digest'] or 'none'}")
    print(f"- Freeze confirmation: {manifest['freeze_confirmation']['status']}")
    return 0 if manifest["status"] == "frozen" else 2


def _load_json(path: str, label: str) -> dict:
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HandoffModelError(f"Malformed JSON in {label}: {exc}") from exc
    except OSError as exc:
        raise HandoffModelError(f"Could not read {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise HandoffModelError(f"{label} must be a JSON object")
    return data


if __name__ == "__main__":
    raise SystemExit(main())
