from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Allow running as: python factory\run_factory.py
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from factory.spec_builder import build_contest_spec, save_contest_spec
from factory.gap_analyzer import analyze_gaps, save_gap_report
from factory.blueprint_generator import build_harness_blueprint, save_harness_blueprint
from factory.harness_generator import generate_harness
from factory.experiment_manager import save_run_log
from factory.report_writer import write_solution_log_stub
from factory.rule_guard import rule_guard_warnings
from factory.input_scanner import scan_contest_inputs, save_input_scan_report
from factory.ai_problem_analyzer import save_ai_problem_analysis_prompt
from factory.utils import ensure_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a contest-specific harness scaffold.")
    parser.add_argument("--contest", required=True, help="Path to contest folder")
    parser.add_argument("--output", default="generated", help="Output directory")
    args = parser.parse_args()

    output_dir = ensure_dir(args.output)

    input_scan = scan_contest_inputs(args.contest)
    input_scan_json, input_scan_md = save_input_scan_report(input_scan, output_dir)

    spec = build_contest_spec(args.contest)
    spec_yaml, spec_json = save_contest_spec(spec, output_dir)

    gap_report = analyze_gaps(spec)
    gap_path = save_gap_report(gap_report, output_dir)

    blueprint = build_harness_blueprint(
        spec,
        gap_report,
        templates_dir=PROJECT_ROOT / "templates",
    )
    blueprint_yaml, blueprint_md = save_harness_blueprint(blueprint, output_dir)

    ai_prompt_path = save_ai_problem_analysis_prompt(
        input_scan,
        spec,
        gap_report,
        blueprint,
        output_dir,
        template_path=PROJECT_ROOT / "templates" / "prompts" / "problem_analyzer.md",
    )

    harness_dir = generate_harness(
        spec,
        blueprint=blueprint,
        template_dir=PROJECT_ROOT / "templates" / "base_harness",
        output_dir=output_dir / "final_harness",
    )

    solution_log = write_solution_log_stub(spec, output_dir)
    run_dir = save_run_log(spec, gap_path, harness_dir)

    print("[OK] Factory generated MVP artifacts")
    print(f"- Input scan report JSON: {input_scan_json}")
    print(f"- Input scan report MD: {input_scan_md}")
    print(f"- AI problem analysis prompt: {ai_prompt_path}")
    print(f"- Contest spec: {spec_yaml}")
    print(f"- Contest spec JSON: {spec_json}")
    print(f"- Gap report: {gap_path}")
    print(f"- Harness blueprint YAML: {blueprint_yaml}")
    print(f"- Harness blueprint MD: {blueprint_md}")
    print(f"- Solution log: {solution_log}")
    print(f"- Final harness: {harness_dir}")
    print(f"- Run log: {run_dir}")

    warnings = rule_guard_warnings(spec)
    if warnings:
        print("\n[Rule Guard Warnings]")
        for warning in warnings:
            print(f"- {warning}")

    print("\nNext:")
    print("  python generated\\final_harness\\run.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
