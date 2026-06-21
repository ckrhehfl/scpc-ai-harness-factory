from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from factory.ai_analysis_intake import AnalysisIntakeError, run_analysis_review


def main() -> int:
    parser = argparse.ArgumentParser(description="Build human review artifacts from an offline AI analysis response.")
    parser.add_argument("--contest", required=True, help="Path to contest folder")
    parser.add_argument("--analysis-response", required=True, help="Path to saved AI analysis markdown response")
    parser.add_argument("--output", default="generated", help="Output directory")
    args = parser.parse_args()

    try:
        paths = run_analysis_review(
            contest_path=args.contest,
            response_path=args.analysis_response,
            output_dir=args.output,
        )
    except AnalysisIntakeError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"[ERROR] Failed to read or write review artifacts: {exc}", file=sys.stderr)
        return 2

    print("[OK] AI analysis review artifacts generated")
    print(f"- Candidates JSON: {paths['candidates_json']}")
    print(f"- Review report: {paths['review_md']}")
    print(f"- Proposed overrides: {paths['proposed_yaml']}")
    print(f"- Code agent task plan: {paths['task_plan_md']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
