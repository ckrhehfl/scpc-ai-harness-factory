from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from factory.code_agent_prompt_builder import CodeAgentPromptError, save_code_agent_work_package


def main() -> int:
    parser = argparse.ArgumentParser(description="Build an offline Code Agent implementation prompt package.")
    parser.add_argument("--contest", required=True, help="Path to contest folder")
    parser.add_argument("--analysis-candidates", required=True, help="Path to ai_analysis_candidates.json")
    parser.add_argument("--output", default="generated", help="Output directory")
    args = parser.parse_args()

    try:
        paths = save_code_agent_work_package(
            contest_path=args.contest,
            analysis_candidates_path=args.analysis_candidates,
            output_dir=args.output,
            template_path=PROJECT_ROOT / "templates" / "prompts" / "code_agent_implementation.md",
        )
    except CodeAgentPromptError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"[ERROR] Failed to read or write code agent prompt artifacts: {exc}", file=sys.stderr)
        return 2

    print("[OK] Code agent work package generated")
    print(f"- Context JSON: {paths['context_json']}")
    print(f"- Implementation prompt: {paths['implementation_prompt']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
