from __future__ import annotations

from pathlib import Path
import json
import subprocess
import sys

from factory.decision_model import canonical_json_digest
from factory.handoff_model import sha256_file
from factory.submission_handoff_builder import save_submission_handoff_outputs
from test_submission_handoff_builder import build, freeze


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "factory" / "run_post_submission_audit.py"


def frozen_files(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    prepared, _ = build(tmp_path)
    digest = prepared["candidate"]["candidate_digest"]
    manifest, package = build(tmp_path, freeze=freeze(digest))
    output = tmp_path / "handoff"
    template = {"schema_version": "v0.12", "artifact_type": "freeze_confirmation_intake", "scope": "local_submission_candidate", "candidate_digest": digest, "confirmations": [], "notes": []}
    paths = save_submission_handoff_outputs(manifest, template, package, output)
    submitted = tmp_path / "private" / "submission.csv"
    submitted.parent.mkdir()
    submitted.write_bytes(package["submission/submission.csv"])
    return manifest, paths["manifest_json"], paths["package_zip"], submitted


def write_receipt(path: Path, manifest: dict, archive: Path, submitted: Path, *, receipt_status="recorded", platform_status="submitted", supersedes=None, receipt_id="receipt.local_submission_candidate.r001", score=None):
    receipt = {
        "receipt_id": receipt_id,
        "scope": "local_submission_candidate",
        "expected_candidate_digest": manifest["candidate"]["candidate_digest"],
        "expected_submission_sha256": sha256_file(submitted),
        "actor": "human",
        "receipt_status": receipt_status,
        "platform": "internal_mock" if receipt_status == "recorded" else None,
        "submission_identifier": "SUB-2026-0001" if receipt_status == "recorded" else None,
        "submitted_at": "2026-06-22T14:30:00+09:00" if receipt_status == "recorded" else None,
        "uploaded_filename": "submission.csv" if receipt_status == "recorded" else None,
        "platform_status": platform_status if receipt_status == "recorded" else "unknown",
        "score": score,
        "evidence_ids": [],
        "rationale": "The frozen submission file was uploaded manually." if receipt_status != "pending" else "",
        "supersedes": supersedes,
        "notes": [],
    }
    intake = {
        "schema_version": "v0.13",
        "artifact_type": "submission_receipt_intake",
        "scope": "local_submission_candidate",
        "source_digests": {"handoff_manifest": canonical_json_digest(manifest), "handoff_archive": sha256_file(archive)},
        "candidate_digest": manifest["candidate"]["candidate_digest"],
        "submission_sha256": sha256_file(submitted),
        "evidence_files": [],
        "receipts": [receipt],
        "notes": [],
    }
    path.write_text(json.dumps(intake, ensure_ascii=False, indent=2), encoding="utf-8")
    return intake


def run_cli(manifest: Path, archive: Path, submitted: Path, output: Path, receipt: Path | None = None) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        str(SCRIPT),
        "--handoff-manifest",
        str(manifest),
        "--handoff-archive",
        str(archive),
        "--submitted-file",
        str(submitted),
        "--output",
        str(output),
    ]
    if receipt is not None:
        cmd.extend(["--receipt-intake", str(receipt)])
    return subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, check=False)


def test_cli_matched_no_receipt_exit_2_and_writes_template(tmp_path: Path):
    manifest_data, manifest, archive, submitted = frozen_files(tmp_path)
    output = tmp_path / "generated"
    original_manifest = manifest.read_bytes()
    original_submitted = submitted.read_bytes()
    result = run_cli(manifest, archive, submitted, output)
    assert result.returncode == 2
    assert "- Audit status: awaiting_receipt" in result.stdout
    assert (output / "post_submission_audit.json").exists()
    template = json.loads((output / "submission_receipt_template.json").read_text(encoding="utf-8"))
    assert template["receipts"][0]["receipt_id"] == "receipt.local_submission_candidate.r001"
    assert manifest.read_bytes() == original_manifest
    assert submitted.read_bytes() == original_submitted
    assert manifest_data["status"] == "frozen"


def test_cli_recorded_receipt_exit_0_and_rejected_outcome_still_complete(tmp_path: Path):
    manifest_data, manifest, archive, submitted = frozen_files(tmp_path)
    receipt_path = tmp_path / "private" / "submission_receipt_intake.json"
    write_receipt(receipt_path, manifest_data, archive, submitted, platform_status="rejected")
    output = tmp_path / "generated"
    result = run_cli(manifest, archive, submitted, output, receipt_path)
    assert result.returncode == 0
    assert "- Audit status: complete" in result.stdout
    audit = json.loads((output / "post_submission_audit.json").read_text(encoding="utf-8"))
    assert audit["platform_outcome"]["platform_status"] == "rejected"
    assert audit["status"] == "complete"


def test_cli_pending_stale_conflicting_retracted_and_missing_archive_exit_2(tmp_path: Path):
    manifest_data, manifest, archive, submitted = frozen_files(tmp_path)
    for name, update, expected in [
        ("pending", {"receipt_status": "pending"}, "pending"),
        ("stale", {"expected_candidate_digest": "sha256:" + "9" * 64}, "stale"),
        ("retracted", {"receipt_status": "retracted", "receipt_id": "receipt.local_submission_candidate.r002", "supersedes": "receipt.local_submission_candidate.r001"}, "retracted"),
    ]:
        receipt_path = tmp_path / f"{name}.json"
        intake = write_receipt(receipt_path, manifest_data, archive, submitted)
        entry = intake["receipts"][0]
        entry.update(update)
        if name == "pending":
            entry.update({"platform": None, "submission_identifier": None, "submitted_at": None, "uploaded_filename": None, "platform_status": "unknown", "rationale": ""})
        if name == "retracted":
            prior = dict(entry, receipt_id="receipt.local_submission_candidate.r001", receipt_status="recorded", platform="internal_mock", submission_identifier="SUB-2026-0001", submitted_at="2026-06-22T14:30:00+09:00", uploaded_filename="submission.csv", platform_status="submitted", rationale="Prior record.", supersedes=None)
            entry.update({"platform": None, "submission_identifier": None, "submitted_at": None, "uploaded_filename": None, "platform_status": "unknown", "score": None, "evidence_ids": [], "rationale": "Retracted.", "supersedes": "receipt.local_submission_candidate.r001"})
            intake["receipts"] = [prior, entry]
        receipt_path.write_text(json.dumps(intake, ensure_ascii=False, indent=2), encoding="utf-8")
        result = run_cli(manifest, archive, submitted, tmp_path / f"out_{name}", receipt_path)
        assert result.returncode == 2
        assert f"- Audit status: {expected}" in result.stdout

    missing = run_cli(manifest, tmp_path / "missing.zip", submitted, tmp_path / "out_missing")
    assert missing.returncode == 2
    assert "- Audit status: blocked" in missing.stdout


def test_cli_malformed_manifest_or_receipt_exit_1_without_output(tmp_path: Path):
    manifest_data, manifest, archive, submitted = frozen_files(tmp_path)
    bad_manifest = tmp_path / "bad_manifest.json"
    bad_manifest.write_text("{bad", encoding="utf-8")
    output = tmp_path / "bad_output"
    result = run_cli(bad_manifest, archive, submitted, output)
    assert result.returncode == 1
    assert not output.exists()

    bad_receipt = tmp_path / "bad_receipt.json"
    bad_receipt.write_text("{bad", encoding="utf-8")
    output = tmp_path / "bad_receipt_output"
    result = run_cli(manifest, archive, submitted, output, bad_receipt)
    assert result.returncode == 1
    assert not output.exists()
    assert manifest_data["status"] == "frozen"


def test_cli_deterministic_rerun_no_absolute_paths_or_timestamps(tmp_path: Path):
    manifest_data, manifest, archive, submitted = frozen_files(tmp_path)
    receipt_path = tmp_path / "private" / "submission_receipt_intake.json"
    write_receipt(receipt_path, manifest_data, archive, submitted)
    output = tmp_path / "generated"
    first = run_cli(manifest, archive, submitted, output, receipt_path)
    first_bytes = {path.name: path.read_bytes() for path in output.iterdir()}
    second = run_cli(manifest, archive, submitted, output, receipt_path)
    second_bytes = {path.name: path.read_bytes() for path in output.iterdir()}
    assert first.returncode == 0
    assert second.returncode == 0
    assert first_bytes == second_bytes
    joined = b"\n".join(second_bytes.values())
    assert str(tmp_path).encode() not in joined
    assert b"created_at" not in joined
    assert b"generated_at" not in joined
