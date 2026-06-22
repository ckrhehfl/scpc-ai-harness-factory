from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "factory" / "run_capability_registry.py"


def capability(*, implementation_path: str = "module.py", implementation_symbol: str = "build_sample") -> dict:
    return {
        "capability_id": "cap.factory.sample",
        "name": "Sample capability",
        "scope": "factory",
        "category": "audit",
        "declared_status": "implemented",
        "description": "A sample capability.",
        "provides": ["sample.capability.token"],
        "inputs": ["input"],
        "outputs": ["output"],
        "implementation_evidence": [{"path": implementation_path, "symbols": [implementation_symbol]}],
        "test_evidence": [{"path": "test_module.py", "symbols": ["test_sample"]}],
        "dependencies": [],
        "risk_gates": [],
        "limitations": ["Only validates static evidence."],
        "tags": ["offline"],
    }


def write_definition(path: Path, cap: dict | None = None) -> bytes:
    data = {
        "schema_version": "v0.10A",
        "artifact_type": "capability_registry_definition",
        "capabilities": [cap or capability()],
    }
    encoded = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    path.write_bytes(encoded)
    return encoded


def make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "module.py").write_text("def build_sample():\n    return 1\n", encoding="utf-8")
    (repo / "test_module.py").write_text("def test_sample():\n    pass\n", encoding="utf-8")
    return repo


def run_cli(registry: Path, repo_root: Path, output: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--registry",
            str(registry),
            "--repo-root",
            str(repo_root),
            "--output",
            str(output),
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_success_generates_json_and_markdown(tmp_path: Path):
    repo = make_repo(tmp_path)
    registry_path = tmp_path / "registry.json"
    write_definition(registry_path)
    output = tmp_path / "generated"

    result = run_cli(registry_path, repo, output)

    assert result.returncode == 0
    assert "[OK] Capability registry generated" in result.stdout
    assert "- Verification failures: 0" in result.stdout
    assert (output / "capability_registry.json").exists()
    assert (output / "capability_registry.md").exists()
    data = json.loads((output / "capability_registry.json").read_text(encoding="utf-8"))
    assert data["summary"]["eligible"] == 1


def test_cli_malformed_registry_exits_1_without_output(tmp_path: Path):
    repo = make_repo(tmp_path)
    registry_path = tmp_path / "registry.json"
    registry_path.write_text("{bad", encoding="utf-8")
    output = tmp_path / "generated"

    result = run_cli(registry_path, repo, output)

    assert result.returncode == 1
    assert "[ERROR]" in result.stderr
    assert not output.exists()


def test_cli_unsafe_evidence_path_exits_1_without_output(tmp_path: Path):
    repo = make_repo(tmp_path)
    registry_path = tmp_path / "registry.json"
    write_definition(registry_path, capability(implementation_path="../module.py"))
    output = tmp_path / "generated"

    result = run_cli(registry_path, repo, output)

    assert result.returncode == 1
    assert "[ERROR]" in result.stderr
    assert not output.exists()


def test_cli_incomplete_evidence_exits_2_and_writes_output(tmp_path: Path):
    repo = make_repo(tmp_path)
    registry_path = tmp_path / "registry.json"
    original_registry = write_definition(registry_path, capability(implementation_symbol="missing"))
    original_module = (repo / "module.py").read_bytes()
    output = tmp_path / "generated"

    result = run_cli(registry_path, repo, output)

    assert result.returncode == 2
    assert "- Verification failures: 1" in result.stdout
    assert "[WARN]" in result.stdout
    assert registry_path.read_bytes() == original_registry
    assert (repo / "module.py").read_bytes() == original_module
    data = json.loads((output / "capability_registry.json").read_text(encoding="utf-8"))
    assert data["summary"]["incomplete"] == 1


def test_cli_repeated_runs_are_deterministic(tmp_path: Path):
    repo = make_repo(tmp_path)
    registry_path = tmp_path / "registry.json"
    write_definition(registry_path)
    output = tmp_path / "generated"

    first = run_cli(registry_path, repo, output)
    first_bytes = (output / "capability_registry.json").read_bytes()
    second = run_cli(registry_path, repo, output)
    second_bytes = (output / "capability_registry.json").read_bytes()

    assert first.returncode == 0
    assert second.returncode == 0
    assert first_bytes == second_bytes


def test_cli_checked_in_registry_succeeds(tmp_path: Path):
    output = tmp_path / "generated"
    result = run_cli(REPO_ROOT / "capabilities" / "registry.json", REPO_ROOT, output)
    assert result.returncode == 0
    data = json.loads((output / "capability_registry.json").read_text(encoding="utf-8"))
    assert data["summary"]["total"] == 27
    assert data["summary"]["verified"] == 27
    assert data["summary"]["eligible"] == 27
    assert data["summary"]["incomplete"] == 0
    ids = {item["capability_id"] for item in data["capabilities"]}
    assert "cap.factory.contest_requirement_generation" in ids
    assert "cap.factory.requirement_capability_matching" in ids
    assert "cap.factory.decision_intake_validation" in ids
    assert "cap.factory.decision_ledger_generation" in ids
    assert "cap.factory.human_approval_intake_validation" in ids
    assert "cap.factory.local_readiness_gate_generation" in ids
    assert "cap.factory.freeze_confirmation_validation" in ids
    assert "cap.factory.submission_handoff_package_generation" in ids
    assert "cap.factory.submission_receipt_validation" in ids
    assert "cap.factory.post_submission_audit_generation" in ids
