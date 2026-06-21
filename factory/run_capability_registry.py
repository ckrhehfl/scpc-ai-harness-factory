from __future__ import annotations

import argparse
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from factory.capability_model import CapabilityModelError
from factory.capability_registry_builder import (
    audit_capability_registry,
    load_capability_definition,
    save_capability_registry,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a static Capability Registry audit.")
    parser.add_argument("--registry", default="capabilities/registry.json", help="Capability registry definition")
    parser.add_argument("--repo-root", default=".", help="Repository root")
    parser.add_argument("--output", default="generated", help="Output directory")
    args = parser.parse_args()

    try:
        definition = load_capability_definition(args.registry)
        registry = audit_capability_registry(
            definition,
            repo_root=args.repo_root,
            source_registry=Path(args.registry).as_posix(),
        )
        paths = save_capability_registry(registry, args.output)
    except (CapabilityModelError, OSError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    summary = registry["summary"]
    verification_failures = summary["incomplete"]
    print("[OK] Capability registry generated")
    print(f"- Registry JSON: {paths['json']}")
    print(f"- Registry MD: {paths['md']}")
    print(f"- Total: {summary['total']}")
    print(f"- Eligible: {summary['eligible']}")
    print(f"- Limited: {summary['limited']}")
    print(f"- Ineligible: {summary['ineligible']}")
    print(f"- Verification failures: {verification_failures}")
    for warning in registry.get("warnings", []):
        print(f"[WARN] {warning}")
    return 2 if verification_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
