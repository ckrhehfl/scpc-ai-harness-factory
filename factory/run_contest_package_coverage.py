from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Allow running as: python factory/run_contest_package_coverage.py
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from factory.contest_package_coverage import (
    ContestPackageCoverageError,
    build_contest_package_coverage,
    save_contest_package_coverage,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Contest Package coverage from existing artifacts.")
    parser.add_argument("--contest", required=True, help="Path to contest package folder")
    parser.add_argument(
        "--artifacts",
        required=True,
        help="Directory containing input_scan_report.json, evidence_index.json, and contest_spec.json",
    )
    parser.add_argument("--output", default="generated", help="Output directory")
    args = parser.parse_args()

    try:
        coverage = build_contest_package_coverage(args.contest, artifacts_dir=args.artifacts)
        paths = save_contest_package_coverage(coverage, args.output)
    except ContestPackageCoverageError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print("[OK] Contest package coverage generated")
    print(f"- Coverage JSON: {paths['json']}")
    print(f"- Coverage MD: {paths['md']}")
    print(f"- Manifest sources: {coverage['source_summary']['manifest_source_count']}")
    print(f"- High-risk unknowns: {len(coverage['high_risk_unknowns'])}")
    print(f"- Not-modeled topics: {len(coverage['not_modeled_topics'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
