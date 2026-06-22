from __future__ import annotations

import argparse
from pathlib import Path
import json
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from factory.post_submission_audit import (
    build_post_submission_audit,
    build_receipt_evidence_index,
    build_submission_receipt_template,
    load_submission_receipt_intake,
    save_post_submission_outputs,
)
from factory.receipt_model import ReceiptModelError


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit a manual platform submission receipt against a frozen local handoff candidate.")
    parser.add_argument("--handoff-manifest", required=True, help="submission_handoff_manifest.json path")
    parser.add_argument("--handoff-archive", required=True, help="submission_handoff_package.zip path")
    parser.add_argument("--submitted-file", required=True, help="Local preserved copy of the manually submitted CSV")
    parser.add_argument("--receipt-intake", help="Optional submission_receipt_intake.json path")
    parser.add_argument("--output", default="generated", help="Output directory")
    args = parser.parse_args()

    try:
        handoff_manifest = _load_json(args.handoff_manifest, "submission_handoff_manifest.json")
        receipt_intake, evidence_base_dir = load_submission_receipt_intake(args.receipt_intake)
        evidence_index = build_receipt_evidence_index(receipt_intake, evidence_base_dir=evidence_base_dir)
        audit = build_post_submission_audit(
            handoff_manifest=handoff_manifest,
            handoff_archive_path=args.handoff_archive,
            submitted_file_path=args.submitted_file,
            receipt_intake=receipt_intake,
            receipt_evidence_index=evidence_index,
        )
        template = build_submission_receipt_template(audit)
        paths = save_post_submission_outputs(audit, template, evidence_index, args.output)
    except (ReceiptModelError, OSError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print("[OK] Post-submission audit generated")
    print(f"- Audit JSON: {paths['audit_json']}")
    print(f"- Audit MD: {paths['audit_md']}")
    print(f"- Receipt template: {paths['receipt_template']}")
    print(f"- Evidence index: {paths['evidence_index']}")
    print(f"- Artifact binding: {audit['handoff_binding']['status']}")
    print(f"- Receipt state: {audit['receipt_state']['status']}")
    print(f"- Platform status: {audit['platform_outcome']['platform_status']}")
    print(f"- Audit status: {audit['status']}")
    print(f"- Blockers: {audit['summary']['blocker_count']}")
    print(f"- Warnings: {audit['summary']['warning_count']}")
    return 0 if audit["status"] == "complete" else 2


def _load_json(path: str, label: str) -> dict:
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReceiptModelError(f"Malformed JSON in {label}: {exc}") from exc
    except OSError as exc:
        raise ReceiptModelError(f"Could not read {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise ReceiptModelError(f"{label} must be a JSON object")
    return data


if __name__ == "__main__":
    raise SystemExit(main())
