from __future__ import annotations

from pathlib import Path
import copy
import json
import zipfile

from factory.decision_model import canonical_json_digest
from factory.handoff_model import sha256_file
from factory.post_submission_audit import (
    build_post_submission_audit,
    build_receipt_evidence_index,
    build_submission_receipt_template,
    render_post_submission_audit_markdown,
    save_post_submission_outputs,
)
from factory.submission_handoff_builder import save_submission_handoff_outputs
from test_submission_handoff_builder import build, freeze


def frozen_fixture(tmp_path: Path):
    tmp_path.mkdir(parents=True, exist_ok=True)
    prepared, _ = build(tmp_path)
    digest = prepared["candidate"]["candidate_digest"]
    manifest, package = build(tmp_path, freeze=freeze(digest))
    output = tmp_path / "generated"
    save_submission_handoff_outputs(manifest, {"schema_version": "v0.12", "artifact_type": "freeze_confirmation_intake", "scope": "local_submission_candidate", "candidate_digest": digest, "confirmations": [], "notes": []}, package, output)
    submitted = tmp_path / "submitted.csv"
    submitted.write_bytes(package["submission/submission.csv"])
    return manifest, output / "submission_handoff_package.zip", submitted


def receipt_intake(manifest: dict, archive: Path, submitted: Path, receipts: list[dict], evidence_files=None) -> dict:
    return {
        "schema_version": "v0.13",
        "artifact_type": "submission_receipt_intake",
        "scope": "local_submission_candidate",
        "source_digests": {"handoff_manifest": canonical_json_digest(manifest), "handoff_archive": sha256_file(archive)},
        "candidate_digest": manifest["candidate"]["candidate_digest"],
        "submission_sha256": sha256_file(submitted),
        "evidence_files": evidence_files or [],
        "receipts": receipts,
        "notes": [],
    }


def receipt(manifest: dict, submitted: Path, receipt_id="receipt.local_submission_candidate.r001", *, status="recorded", supersedes=None, platform_status="submitted", score=None) -> dict:
    return {
        "receipt_id": receipt_id,
        "scope": "local_submission_candidate",
        "expected_candidate_digest": manifest["candidate"]["candidate_digest"],
        "expected_submission_sha256": sha256_file(submitted),
        "actor": "human",
        "receipt_status": status,
        "platform": "internal_mock" if status == "recorded" else None,
        "submission_identifier": "SUB-2026-0001" if status == "recorded" else None,
        "submitted_at": "2026-06-22T14:30:00+09:00" if status == "recorded" else None,
        "uploaded_filename": "submission.csv" if status == "recorded" else None,
        "platform_status": platform_status if status == "recorded" else "unknown",
        "score": score,
        "evidence_ids": [],
        "rationale": "The frozen submission file was uploaded manually." if status != "pending" else "",
        "supersedes": supersedes,
        "notes": [],
    }


def audit_for(tmp_path: Path, intake: dict | None = None, submitted_mutation=None, manifest_mutation=None, archive_path: Path | None = None):
    manifest, archive, submitted = frozen_fixture(tmp_path)
    if submitted_mutation:
        submitted_mutation(submitted)
    if manifest_mutation:
        manifest_mutation(manifest)
    evidence_index = build_receipt_evidence_index(intake, evidence_base_dir=tmp_path) if intake else None
    return build_post_submission_audit(
        handoff_manifest=manifest,
        handoff_archive_path=archive_path or archive,
        submitted_file_path=submitted,
        receipt_intake=intake,
        receipt_evidence_index=evidence_index,
    )


def test_frozen_manifest_valid_archive_matching_submitted_file_is_matched_and_awaits_receipt(tmp_path: Path):
    audit = audit_for(tmp_path)
    assert audit["handoff_binding"]["status"] == "matched"
    assert audit["receipt_state"]["status"] == "not_provided"
    assert audit["status"] == "awaiting_receipt"
    template = build_submission_receipt_template(audit)
    assert template["receipts"][0]["receipt_id"] == "receipt.local_submission_candidate.r001"
    assert template["receipts"][0]["expected_candidate_digest"] == audit["handoff_binding"]["candidate_digest"]


def test_handoff_archive_and_submission_blockers(tmp_path: Path):
    def preflight_blocker(manifest: dict):
        manifest["status"] = "blocked"
        manifest["preflight"]["checks"][0]["status"] = "fail"
        manifest["preflight"]["status"] = "fail"
        manifest["preflight"]["blocker_count"] = 1

    for mutate in [
        lambda manifest: manifest.update({"status": "prepared"}),
        preflight_blocker,
        lambda manifest: manifest["freeze_confirmation"].update({"authoritative": False}),
        lambda manifest: manifest["candidate"].update({"candidate_digest": None}),
    ]:
        audit = audit_for(tmp_path / str(id(mutate)), manifest_mutation=mutate)
        assert audit["handoff_binding"]["status"] == "blocked"
        assert audit["status"] == "blocked"

    audit = audit_for(tmp_path / "missing_archive", archive_path=tmp_path / "missing.zip")
    assert audit["status"] == "blocked"

    audit = audit_for(tmp_path / "byte_mismatch", submitted_mutation=lambda path: path.write_bytes(b"id,label\n1,Z\n"))
    assert audit["status"] == "blocked"
    assert _check(audit, "audit.submission.byte_binding")["status"] == "fail"


def test_zip_safety_and_freeze_manifest_binding_blockers(tmp_path: Path):
    manifest, archive, submitted = frozen_fixture(tmp_path)
    bad_archive = tmp_path / "bad.zip"
    with zipfile.ZipFile(archive) as src, zipfile.ZipFile(bad_archive, "w", compression=zipfile.ZIP_DEFLATED) as dst:
        for name in src.namelist():
            dst.writestr(name, src.read(name))
    audit = build_post_submission_audit(handoff_manifest=manifest, handoff_archive_path=bad_archive, submitted_file_path=submitted)
    assert _check(audit, "audit.archive.entries_stored")["status"] == "fail"

    mutated_archive = tmp_path / "mutated.zip"
    with zipfile.ZipFile(archive) as src, zipfile.ZipFile(mutated_archive, "w", compression=zipfile.ZIP_STORED) as dst:
        for name in src.namelist():
            data = src.read(name)
            if name == "freeze_manifest.json":
                freeze_manifest = json.loads(data.decode("utf-8"))
                freeze_manifest["candidate_digest"] = "sha256:" + "9" * 64
                data = (json.dumps(freeze_manifest, sort_keys=True) + "\n").encode("utf-8")
            dst.writestr(name, data)
    audit = build_post_submission_audit(handoff_manifest=manifest, handoff_archive_path=mutated_archive, submitted_file_path=submitted)
    assert _check(audit, "audit.archive.freeze_manifest_match")["status"] == "fail"


def test_receipt_states_platform_outcomes_and_templates(tmp_path: Path):
    manifest, archive, submitted = frozen_fixture(tmp_path)
    current = receipt(manifest, submitted, platform_status="rejected")
    audit = build_post_submission_audit(handoff_manifest=manifest, handoff_archive_path=archive, submitted_file_path=submitted, receipt_intake=receipt_intake(manifest, archive, submitted, [current]))
    assert audit["status"] == "complete"
    assert audit["receipt_state"]["status"] == "recorded"
    assert audit["platform_outcome"]["platform_status"] == "rejected"
    assert build_submission_receipt_template(audit)["receipts"] == []

    pending = receipt(manifest, submitted, status="pending")
    pending["rationale"] = ""
    audit = build_post_submission_audit(handoff_manifest=manifest, handoff_archive_path=archive, submitted_file_path=submitted, receipt_intake=receipt_intake(manifest, archive, submitted, [pending]))
    assert audit["status"] == "pending"
    assert build_submission_receipt_template(audit)["receipts"][0]["receipt_id"] == "receipt.local_submission_candidate.r002"

    stale = copy.deepcopy(current)
    stale["expected_candidate_digest"] = "sha256:" + "9" * 64
    audit = build_post_submission_audit(handoff_manifest=manifest, handoff_archive_path=archive, submitted_file_path=submitted, receipt_intake=receipt_intake(manifest, archive, submitted, [stale]))
    assert audit["status"] == "stale"

    other = receipt(manifest, submitted, "receipt.local_submission_candidate.r002")
    audit = build_post_submission_audit(handoff_manifest=manifest, handoff_archive_path=archive, submitted_file_path=submitted, receipt_intake=receipt_intake(manifest, archive, submitted, [current, other]))
    assert audit["status"] == "conflicting"
    assert "Manual receipt conflict resolution is required." in build_submission_receipt_template(audit)["notes"]


def test_scored_supersession_history_and_source_digest_warning(tmp_path: Path):
    manifest, archive, submitted = frozen_fixture(tmp_path)
    first = receipt(manifest, submitted)
    second = receipt(
        manifest,
        submitted,
        "receipt.local_submission_candidate.r002",
        supersedes="receipt.local_submission_candidate.r001",
        platform_status="scored",
        score={"value": "0.81234", "metric": "accuracy", "scope": "public"},
    )
    intake = receipt_intake(manifest, archive, submitted, [first, second])
    intake["source_digests"]["handoff_archive"] = "sha256:" + "8" * 64
    audit = build_post_submission_audit(handoff_manifest=manifest, handoff_archive_path=archive, submitted_file_path=submitted, receipt_intake=intake)
    assert audit["status"] == "complete"
    assert audit["receipt_state"]["current_receipt_id"] == "receipt.local_submission_candidate.r002"
    assert audit["platform_outcome"]["score"]["value"] == "0.81234"
    assert _check(audit, "audit.receipt.source_digests_current")["status"] == "warning"


def test_evidence_index_hash_only_no_paths_or_raw_contents_and_missing_blocks(tmp_path: Path):
    manifest, archive, submitted = frozen_fixture(tmp_path)
    evidence = tmp_path / "confirmation.png"
    evidence.write_bytes(b"not really an image but preserved bytes")
    evidence_decl = {"evidence_id": "receipt_ev.confirmation_page", "relative_path": "confirmation.png", "media_type": "image/png", "description": "Submission confirmation page captured manually."}
    item = receipt(manifest, submitted)
    item["evidence_ids"] = ["receipt_ev.confirmation_page"]
    intake = receipt_intake(manifest, archive, submitted, [item], [evidence_decl])
    evidence_index = build_receipt_evidence_index(intake, evidence_base_dir=tmp_path)
    audit = build_post_submission_audit(handoff_manifest=manifest, handoff_archive_path=archive, submitted_file_path=submitted, receipt_intake=intake, receipt_evidence_index=evidence_index)
    rendered = json.dumps(audit, ensure_ascii=False, sort_keys=True)
    assert audit["status"] == "complete"
    assert audit["evidence_summary"]["verified_count"] == 1
    assert "confirmation.png" in rendered
    assert "relative_path" not in rendered
    assert str(tmp_path) not in rendered
    assert "not really an image" not in rendered

    evidence.unlink()
    missing_index = build_receipt_evidence_index(intake, evidence_base_dir=tmp_path)
    audit = build_post_submission_audit(handoff_manifest=manifest, handoff_archive_path=archive, submitted_file_path=submitted, receipt_intake=intake, receipt_evidence_index=missing_index)
    assert audit["status"] == "blocked"
    assert _check(audit, "audit.receipt.evidence_files_valid")["status"] == "fail"


def test_save_outputs_deterministic_markdown_and_no_absolute_paths(tmp_path: Path):
    manifest, archive, submitted = frozen_fixture(tmp_path)
    intake = receipt_intake(manifest, archive, submitted, [receipt(manifest, submitted)])
    evidence_index = build_receipt_evidence_index(intake, evidence_base_dir=tmp_path)
    audit = build_post_submission_audit(handoff_manifest=manifest, handoff_archive_path=archive, submitted_file_path=submitted, receipt_intake=intake, receipt_evidence_index=evidence_index)
    template = build_submission_receipt_template(audit)
    output = tmp_path / "out"
    paths = save_post_submission_outputs(audit, template, evidence_index, output)
    first = {key: path.read_bytes() for key, path in paths.items()}
    paths = save_post_submission_outputs(audit, template, evidence_index, output)
    second = {key: path.read_bytes() for key, path in paths.items()}
    assert first == second
    assert "생성" not in render_post_submission_audit_markdown(audit)
    for payload in second.values():
        assert str(tmp_path).encode() not in payload


def _check(audit: dict, check_id: str) -> dict:
    return next(check for check in audit["checks"] if check["check_id"] == check_id)
