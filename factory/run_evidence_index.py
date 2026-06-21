from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Allow running as: python factory\run_evidence_index.py
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from factory.evidence_index_builder import (
    build_evidence_index,
    load_input_scan_report,
    save_evidence_index,
)
from factory.evidence_model import EvidenceModelError


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an Evidence Index from an input scan report.")
    parser.add_argument("--input-scan", required=True, help="Path to generated/input_scan_report.json")
    parser.add_argument("--output", default="generated", help="Output directory")
    args = parser.parse_args()

    try:
        scan_report = load_input_scan_report(args.input_scan)
        index = build_evidence_index(scan_report, source_artifact=args.input_scan)
        paths = save_evidence_index(index, args.output)
    except EvidenceModelError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print("[OK] Evidence index generated")
    print(f"- Evidence index JSON: {paths['json']}")
    print(f"- Evidence index MD: {paths['md']}")
    print(f"- Records: {index['record_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
