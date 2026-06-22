from __future__ import annotations

from pathlib import Path
from typing import Any
import copy
import json
import os
import tempfile
import zipfile

from factory.decision_model import canonical_json_digest
from factory.handoff_model import HandoffModelError, sha256_bytes, sha256_file, validate_handoff_manifest, validate_package_path
from factory.receipt_model import (
    EVIDENCE_INDEX_ARTIFACT_TYPE,
    POST_SUBMISSION_AUDIT_ARTIFACT_TYPE,
    RECEIPT_INTAKE_ARTIFACT_TYPE,
    SCHEMA_VERSION,
    SCOPE,
    ReceiptModelError,
    receipt_revision,
    validate_post_submission_audit,
    validate_receipt_evidence_index,
    validate_submission_receipt_intake,
)
from factory.utils import write_json, write_text


PACKAGE_ALLOWLIST = {
    "submission/submission.csv",
    "evidence/validation_evidence.json",
    "governance/human_approval_summary.json",
    "governance/decision_ledger.json",
    "requirements/contest_requirements.json",
    "requirements/requirement_capability_match.json",
    "capabilities/capability_registry.json",
    "HANDOFF.md",
    "freeze_manifest.json",
    "governance/freeze_confirmation.json",
}
SUBSTANTIVE_PATHS = {
    "submission/submission.csv",
    "evidence/validation_evidence.json",
    "governance/human_approval_summary.json",
    "governance/decision_ledger.json",
    "requirements/contest_requirements.json",
    "requirements/requirement_capability_match.json",
    "capabilities/capability_registry.json",
}
RECEIPT_EVIDENCE_WARNING = "No receipt evidence file was provided; the receipt relies on manually entered metadata."


def load_submission_receipt_intake(
    path: str | Path | None,
) -> tuple[dict[str, Any] | None, Path | None]:
    if path is None:
        return None, None
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ReceiptModelError(f"Malformed receipt intake JSON: {exc}") from exc
    except OSError as exc:
        raise ReceiptModelError(f"Could not read receipt intake: {exc}") from exc
    if not isinstance(data, dict):
        raise ReceiptModelError("Receipt intake must be a JSON object")
    validate_submission_receipt_intake(data)
    return data, source.parent


def build_receipt_evidence_index(
    intake: dict[str, Any] | None,
    *,
    evidence_base_dir: str | Path | None,
) -> dict[str, Any]:
    if intake is not None:
        validate_submission_receipt_intake(intake)
    items = []
    warnings = []
    base = Path(evidence_base_dir) if evidence_base_dir is not None else None
    for declaration in (intake or {}).get("evidence_files", []):
        path = base / declaration["relative_path"] if base is not None else Path(declaration["relative_path"])
        filename = Path(declaration["relative_path"]).name
        try:
            is_symlink = path.is_symlink()
            is_file = path.is_file() and not is_symlink
            size = path.stat().st_size if is_file else 0
        except OSError:
            is_symlink = False
            is_file = False
            size = 0
        if not is_file or size <= 0:
            warnings.append(f"Receipt evidence file is missing or invalid: {declaration['evidence_id']}")
            continue
        items.append(
            {
                "evidence_id": declaration["evidence_id"],
                "filename": filename,
                "media_type": declaration["media_type"],
                "description": declaration["description"],
                "sha256": sha256_file(path),
                "size_bytes": size,
            }
        )
    index = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": EVIDENCE_INDEX_ARTIFACT_TYPE,
        "scope": SCOPE,
        "items": sorted(items, key=lambda item: item["evidence_id"]),
        "warnings": sorted(set(warnings)),
    }
    validate_receipt_evidence_index(index)
    return index


def build_post_submission_audit(
    *,
    handoff_manifest: dict[str, Any],
    handoff_archive_path: str | Path,
    submitted_file_path: str | Path,
    receipt_intake: dict[str, Any] | None = None,
    receipt_evidence_index: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if receipt_intake is not None:
        validate_submission_receipt_intake(receipt_intake)
    if receipt_evidence_index is None:
        receipt_evidence_index = build_receipt_evidence_index(receipt_intake, evidence_base_dir=None)
    validate_receipt_evidence_index(receipt_evidence_index)

    checks: list[dict[str, Any]] = []
    warnings: list[str] = []
    archive_path = Path(handoff_archive_path)
    submitted_path = Path(submitted_file_path)
    manifest_digest = canonical_json_digest(handoff_manifest)
    archive_digest = sha256_file(archive_path) if _regular_non_symlink(archive_path) else None
    submitted_digest = sha256_file(submitted_path) if _regular_non_symlink(submitted_path) else None
    archive_entries: dict[str, bytes] = {}
    archive_entry_count = 0
    archive_names: list[str] = []
    archive_error: str | None = None
    zip_policy_errors: list[str] = []

    try:
        validate_handoff_manifest(handoff_manifest)
    except HandoffModelError as exc:
        raise ReceiptModelError(f"Malformed handoff manifest: {exc}") from exc

    checks.extend(_handoff_checks(handoff_manifest))
    archive_regular = archive_path.exists() and archive_path.is_file() and not archive_path.is_symlink() and archive_path.suffix == ".zip" and _safe_size(archive_path) > 0
    checks.append(_check("audit.archive.regular_file", "archive", archive_regular, _file_observed(archive_path), {"regular_file": True, "suffix": ".zip", "size_bytes": ">0"}))
    checks.append(_check("audit.archive.not_symlink", "archive", not archive_path.is_symlink(), archive_path.is_symlink(), False))
    if archive_regular:
        try:
            with zipfile.ZipFile(archive_path) as archive:
                infos = archive.infolist()
                archive_names = [info.filename for info in infos]
                duplicate_names = sorted(name for name in set(archive_names) if archive_names.count(name) > 1)
                if duplicate_names:
                    raise ReceiptModelError(f"Duplicate ZIP filename(s): {', '.join(duplicate_names)}")
                directory_entries = sorted(info.filename for info in infos if info.is_dir() or info.filename.endswith("/"))
                if directory_entries:
                    zip_policy_errors.append(f"directory entry: {directory_entries[0]}")
                compressed = sorted(info.filename for info in infos if info.compress_type != zipfile.ZIP_STORED)
                if compressed:
                    zip_policy_errors.append(f"compressed entry: {compressed[0]}")
                for name in archive_names:
                    try:
                        validate_package_path(name)
                    except HandoffModelError as exc:
                        zip_policy_errors.append(str(exc))
                archive_entries = {info.filename: archive.read(info.filename) for info in infos}
                archive_entry_count = len(archive_entries)
        except zipfile.BadZipFile as exc:
            raise ReceiptModelError(f"Malformed handoff archive ZIP: {exc}") from exc
        except OSError as exc:
            archive_error = type(exc).__name__
    checks.append(_check("audit.archive.zip_readable", "archive", bool(archive_regular and archive_entries and archive_error is None), archive_error or bool(archive_entries), "readable ZIP"))
    allowlist_exact = set(archive_entries) == PACKAGE_ALLOWLIST
    checks.append(_check("audit.archive.allowlist_exact", "archive", allowlist_exact, sorted(archive_entries), sorted(PACKAGE_ALLOWLIST)))
    entries_stored = bool(archive_entries) and not zip_policy_errors and all(name in archive_entries for name in PACKAGE_ALLOWLIST)
    checks.append(_check("audit.archive.entries_stored", "archive", entries_stored, {"entries": sorted(archive_entries), "policy_errors": sorted(zip_policy_errors)}, "all entries ZIP_STORED and required paths present"))
    checks.append(_candidate_entries_check(handoff_manifest, archive_entries))
    checks.append(_freeze_manifest_check(handoff_manifest, archive_entries))

    submitted_regular = submitted_path.exists() and submitted_path.is_file() and not submitted_path.is_symlink() and _safe_size(submitted_path) > 0
    checks.append(_check("audit.submission.regular_file", "submission", submitted_regular, _file_observed(submitted_path), {"regular_file": True, "size_bytes": ">0"}))
    checks.append(_check("audit.submission.not_symlink", "submission", not submitted_path.is_symlink(), submitted_path.is_symlink(), False))
    checks.append(_check("audit.submission.csv_extension", "submission", submitted_path.suffix == ".csv", submitted_path.suffix, ".csv"))
    submission_binding = _submission_binding(handoff_manifest, archive_entries, submitted_path, submitted_digest)
    checks.append(submission_binding)

    candidate_digest = handoff_manifest["candidate"].get("candidate_digest")
    manifest_submission_entry = _submission_entry(handoff_manifest)
    submission_sha256 = submitted_digest or (manifest_submission_entry or {}).get("sha256")
    source_digest_check = _receipt_source_digest_check(receipt_intake, manifest_digest, archive_digest)
    checks.append(source_digest_check)
    receipt_state = _receipt_state(receipt_intake, candidate_digest, submission_sha256, receipt_evidence_index)
    checks.append(_receipt_current_check("audit.receipt.candidate_digest_current", "candidate_digest", receipt_state, receipt_intake))
    checks.append(_receipt_current_check("audit.receipt.submission_digest_current", "submission_sha256", receipt_state, receipt_intake))
    checks.append(_receipt_evidence_check(receipt_state, receipt_intake, receipt_evidence_index))

    if receipt_state["warnings"]:
        warnings.extend(receipt_state["warnings"])
    if source_digest_check["status"] == "warning":
        warnings.extend(source_digest_check["notes"])

    artifact_blocker = any(check["category"] in {"handoff", "archive", "submission"} and check["severity"] == "blocker" and check["status"] == "fail" for check in checks)
    artifact_binding = "blocked" if artifact_blocker else "matched"
    evidence_blocker = any(check["check_id"] == "audit.receipt.evidence_files_valid" and check["status"] == "fail" for check in checks)
    status = _audit_status(artifact_binding, receipt_state["status"], receipt_state["authoritative"], evidence_blocker)
    platform_outcome = _platform_outcome(receipt_state)
    blocker_count = sum(1 for check in checks if check["severity"] == "blocker" and check["status"] == "fail")
    warning_count = sum(1 for check in checks if check["status"] == "warning" or check["severity"] == "warning")
    evidence_items = receipt_evidence_index["items"]
    audit = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": POST_SUBMISSION_AUDIT_ARTIFACT_TYPE,
        "scope": SCOPE,
        "status": status,
        "source_artifacts": {
            "handoff_manifest": "submission_handoff_manifest.json",
            "handoff_archive": "submission_handoff_package.zip",
            "submitted_file": submitted_path.name,
            "receipt_intake": "submission_receipt_intake.json" if receipt_intake is not None else None,
        },
        "source_digests": {
            "handoff_manifest": manifest_digest,
            "handoff_archive": archive_digest,
            "submitted_file": submitted_digest,
        },
        "handoff_binding": {
            "status": artifact_binding,
            "candidate_digest": candidate_digest,
            "submission_sha256": submission_sha256,
            "current_freeze_confirmation_id": handoff_manifest["freeze_confirmation"].get("current_confirmation_id"),
            "archive_entry_count": archive_entry_count,
        },
        "receipt_state": receipt_state,
        "platform_outcome": platform_outcome,
        "evidence_summary": {
            "declared_count": len((receipt_intake or {}).get("evidence_files", [])),
            "verified_count": len(evidence_items),
            "missing_count": max(0, len((receipt_intake or {}).get("evidence_files", [])) - len(evidence_items)),
            "items": evidence_items,
        },
        "checks": sorted(checks, key=lambda item: item["check_id"]),
        "summary": {
            "blocker_count": blocker_count,
            "warning_count": warning_count,
            "receipt_history_count": len(receipt_state["history"]),
            "evidence_count": len(evidence_items),
        },
        "warnings": sorted(set(warnings + receipt_evidence_index["warnings"])),
    }
    validate_post_submission_audit(audit)
    return audit


def build_submission_receipt_template(audit: dict[str, Any]) -> dict[str, Any]:
    validate_post_submission_audit(audit)
    receipts = []
    notes = []
    warnings = []
    state = audit["receipt_state"]["status"]
    if audit["handoff_binding"]["status"] == "blocked":
        notes.append("Artifact binding is blocked; a submission receipt cannot be requested.")
    elif state == "conflicting":
        warnings.append("Manual receipt conflict resolution is required.")
    elif state in {"recorded", "retracted"}:
        pass
    else:
        leaf = _single_leaf(audit["receipt_state"]["history"])
        supersedes = leaf["receipt_id"] if leaf and state in {"pending", "stale"} else None
        revision = receipt_revision(supersedes) + 1 if supersedes else 1
        receipts.append(
            {
                "receipt_id": f"receipt.local_submission_candidate.r{revision:03d}",
                "scope": SCOPE,
                "expected_candidate_digest": audit["handoff_binding"]["candidate_digest"],
                "expected_submission_sha256": audit["handoff_binding"]["submission_sha256"],
                "actor": "human",
                "receipt_status": "pending",
                "platform": None,
                "submission_identifier": None,
                "submitted_at": None,
                "uploaded_filename": None,
                "platform_status": "unknown",
                "score": None,
                "evidence_ids": [],
                "rationale": "",
                "supersedes": supersedes,
                "notes": [],
            }
        )
    template = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": RECEIPT_INTAKE_ARTIFACT_TYPE,
        "scope": SCOPE,
        "source_digests": {
            "handoff_manifest": audit["source_digests"]["handoff_manifest"],
            "handoff_archive": audit["source_digests"]["handoff_archive"] or "sha256:" + "0" * 64,
        },
        "candidate_digest": audit["handoff_binding"]["candidate_digest"] or "sha256:" + "0" * 64,
        "submission_sha256": audit["handoff_binding"]["submission_sha256"] or "sha256:" + "0" * 64,
        "evidence_files": [],
        "receipts": receipts,
        "notes": sorted(set(notes + warnings)),
    }
    validate_submission_receipt_intake(template, known_receipt_ids={item["receipt_id"] for item in audit["receipt_state"]["history"]})
    return template


def render_post_submission_audit_markdown(audit: dict[str, Any]) -> str:
    validate_post_submission_audit(audit)
    failed_blockers = [check for check in audit["checks"] if check["severity"] == "blocker" and check["status"] == "fail"]
    lines = [
        "# Post-Submission Audit",
        "",
        "이 문서는 사람이 수행한 온라인 제출의 receipt metadata와 실제 submitted file byte를",
        "frozen local handoff candidate에 결합하여 감사한다.",
        "audit status=complete는 기록 결합이 완전함을 뜻할 뿐,",
        "플랫폼 합격, 점수 확정, 규칙 준수 또는 최종 순위를 보장하지 않는다.",
        "",
        "## Audit Status",
        f"- status: {audit['status']}",
        f"- blockers: {audit['summary']['blocker_count']}",
        f"- warnings: {audit['summary']['warning_count']}",
        "",
        "## Artifact Binding",
        f"- status: {audit['handoff_binding']['status']}",
        f"- archive entries: {audit['handoff_binding']['archive_entry_count']}",
        "",
        "## Handoff Candidate",
        f"- candidate digest: {audit['handoff_binding']['candidate_digest'] or 'none'}",
        f"- freeze confirmation: {audit['handoff_binding']['current_freeze_confirmation_id'] or 'none'}",
        "",
        "## Submitted File Digest",
        f"- sha256: {audit['handoff_binding']['submission_sha256'] or 'none'}",
        "",
        "## Receipt State",
        f"- status: {audit['receipt_state']['status']}",
        f"- authoritative: {audit['receipt_state']['authoritative']}",
        f"- current receipt: {audit['receipt_state']['current_receipt_id'] or 'none'}",
        "",
        "## Platform Outcome",
        f"- platform: {audit['platform_outcome']['platform'] or 'none'}",
        f"- submission identifier: {audit['platform_outcome']['submission_identifier'] or 'none'}",
        f"- submitted at: {audit['platform_outcome']['submitted_at'] or 'none'}",
        f"- uploaded filename: {audit['platform_outcome']['uploaded_filename'] or 'none'}",
        f"- platform status: {audit['platform_outcome']['platform_status']}",
        f"- score: {json.dumps(audit['platform_outcome']['score'], ensure_ascii=False, sort_keys=True) if audit['platform_outcome']['score'] is not None else 'none'}",
        "",
        "## Receipt History",
    ]
    if audit["receipt_state"]["history"]:
        for item in audit["receipt_state"]["history"]:
            lines.append(f"- {item['receipt_id']}: {item['receipt_status']}, digest={item['digest_status']}, leaf={item['is_leaf']}, evidence={item['evidence_status']}")
    else:
        lines.append("- none")
    lines.extend(["", "## Evidence Summary"])
    lines.append(f"- declared: {audit['evidence_summary']['declared_count']}")
    lines.append(f"- verified: {audit['evidence_summary']['verified_count']}")
    lines.append(f"- missing: {audit['evidence_summary']['missing_count']}")
    for item in audit["evidence_summary"]["items"]:
        lines.append(f"- {item['evidence_id']}: {item['filename']}, {item['media_type']}, {item['sha256']}, {item['size_bytes']} bytes")
    lines.extend(["", "## Blocking Checks"])
    if failed_blockers:
        for check in failed_blockers:
            lines.append(f"- {check['check_id']}: observed={_md_value(check['observed'])}; expected={_md_value(check['expected'])}")
    else:
        lines.append("- none")
    lines.extend(["", "## Warnings"])
    if audit["warnings"]:
        lines.extend(f"- {warning}" for warning in audit["warnings"])
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Source Digests",
            f"- handoff manifest: {audit['source_digests']['handoff_manifest']}",
            f"- handoff archive: {audit['source_digests']['handoff_archive'] or 'none'}",
            f"- submitted file: {audit['source_digests']['submitted_file'] or 'none'}",
            "",
            "## Caveats",
            "- Receipt metadata and human identity are manually declared and are not independently authenticated.",
            "- Evidence files are hashed only; OCR and semantic interpretation are not performed.",
            "- Platform outcome values are preserved as declared and are not queried from the platform.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def save_post_submission_outputs(
    audit: dict[str, Any],
    template: dict[str, Any],
    evidence_index: dict[str, Any],
    output_dir: str | Path,
) -> dict[str, Path]:
    validate_post_submission_audit(audit)
    validate_submission_receipt_intake(template, known_receipt_ids={item["receipt_id"] for item in audit["receipt_state"]["history"]})
    validate_receipt_evidence_index(evidence_index)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "audit_json": out / "post_submission_audit.json",
        "audit_md": out / "post_submission_audit.md",
        "receipt_template": out / "submission_receipt_template.json",
        "evidence_index": out / "submission_receipt_evidence_index.json",
    }
    with tempfile.TemporaryDirectory(dir=out) as tmp_name:
        tmp_dir = Path(tmp_name)
        staged = {
            "audit_json": tmp_dir / "post_submission_audit.json",
            "audit_md": tmp_dir / "post_submission_audit.md",
            "receipt_template": tmp_dir / "submission_receipt_template.json",
            "evidence_index": tmp_dir / "submission_receipt_evidence_index.json",
        }
        write_json(staged["audit_json"], audit)
        write_text(staged["audit_md"], render_post_submission_audit_markdown(audit))
        write_json(staged["receipt_template"], template)
        write_json(staged["evidence_index"], evidence_index)
        for key, source in staged.items():
            os.replace(source, paths[key])
    return paths


def _handoff_checks(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    freeze = manifest["freeze_confirmation"]
    return [
        _check("audit.handoff.status_frozen", "handoff", manifest["status"] == "frozen", manifest["status"], "frozen"),
        _check("audit.handoff.preflight_clear", "handoff", manifest["preflight"]["blocker_count"] == 0, manifest["preflight"]["blocker_count"], 0),
        _check(
            "audit.handoff.freeze_confirmed",
            "handoff",
            freeze.get("status") == "confirmed" and freeze.get("authoritative") is True and freeze.get("current_confirmation_id") is not None,
            {"status": freeze.get("status"), "authoritative": freeze.get("authoritative"), "current_confirmation_id": freeze.get("current_confirmation_id")},
            {"status": "confirmed", "authoritative": True, "current_confirmation_id": "non-null"},
        ),
        _check("audit.handoff.candidate_digest_present", "handoff", manifest["candidate"].get("candidate_digest") is not None, manifest["candidate"].get("candidate_digest"), "sha256 digest"),
    ]


def _candidate_entries_check(manifest: dict[str, Any], archive_entries: dict[str, bytes]) -> dict[str, Any]:
    failures = []
    manifest_paths = {entry["package_path"] for entry in manifest["candidate"]["entries"]}
    extra = sorted(path for path in SUBSTANTIVE_PATHS if path in archive_entries and path not in manifest_paths)
    if extra:
        failures.append(f"extra substantive archive entries: {', '.join(extra)}")
    for entry in manifest["candidate"]["entries"]:
        data = archive_entries.get(entry["package_path"])
        if data is None:
            failures.append(f"missing {entry['package_path']}")
            continue
        if sha256_bytes(data) != entry["sha256"]:
            failures.append(f"digest mismatch {entry['package_path']}")
        if len(data) != entry["size_bytes"]:
            failures.append(f"size mismatch {entry['package_path']}")
    return _check("audit.archive.candidate_entries_match", "archive", not failures, failures or "matched", "manifest candidate entries match archive")


def _freeze_manifest_check(manifest: dict[str, Any], archive_entries: dict[str, bytes]) -> dict[str, Any]:
    data = archive_entries.get("freeze_manifest.json")
    if data is None:
        return _check("audit.archive.freeze_manifest_match", "archive", False, "missing", "freeze_manifest.json matches manifest")
    try:
        freeze_manifest = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return _check("audit.archive.freeze_manifest_match", "archive", False, type(exc).__name__, "valid freeze_manifest.json")
    expected = {
        "schema_version": "v0.12",
        "artifact_type": "freeze_manifest",
        "scope": SCOPE,
        "status": "frozen",
        "candidate_digest": manifest["candidate"]["candidate_digest"],
        "approval_readiness_digest": manifest["approval_binding"]["readiness_digest"],
        "current_approval_id": manifest["approval_binding"]["current_approval_id"],
        "freeze_confirmation_status": "confirmed",
        "current_confirmation_id": manifest["freeze_confirmation"]["current_confirmation_id"],
        "entries": manifest["candidate"]["entries"],
    }
    mismatches = sorted(key for key, value in expected.items() if freeze_manifest.get(key) != value)
    return _check("audit.archive.freeze_manifest_match", "archive", not mismatches, mismatches or "matched", "freeze_manifest fields match manifest")


def _submission_binding(manifest: dict[str, Any], archive_entries: dict[str, bytes], submitted_path: Path, submitted_digest: str | None) -> dict[str, Any]:
    entry = _submission_entry(manifest)
    package_data = archive_entries.get("submission/submission.csv")
    observed = {
        "submitted_file_sha256": submitted_digest,
        "package_submission_sha256": sha256_bytes(package_data) if package_data is not None else None,
        "manifest_submission_sha256": entry.get("sha256") if entry else None,
        "submitted_size_bytes": _safe_size(submitted_path) if _regular_non_symlink(submitted_path) else None,
        "package_size_bytes": len(package_data) if package_data is not None else None,
        "manifest_size_bytes": entry.get("size_bytes") if entry else None,
    }
    passed = bool(
        entry
        and package_data is not None
        and submitted_digest is not None
        and observed["submitted_file_sha256"] == observed["package_submission_sha256"] == observed["manifest_submission_sha256"]
        and observed["submitted_size_bytes"] == observed["package_size_bytes"] == observed["manifest_size_bytes"]
    )
    return _check("audit.submission.byte_binding", "submission", passed, observed, "submitted file, package submission, and manifest submission bytes match")


def _receipt_state(intake: dict[str, Any] | None, candidate_digest: str | None, submission_sha256: str | None, evidence_index: dict[str, Any]) -> dict[str, Any]:
    if intake is None:
        return {"status": "not_provided", "authoritative": False, "current_receipt_id": None, "history": [], "warnings": []}
    superseded = {entry["supersedes"] for entry in intake["receipts"] if entry["supersedes"] is not None}
    verified_evidence_ids = {item["evidence_id"] for item in evidence_index["items"]}
    declared_evidence_ids = {item["evidence_id"] for item in intake["evidence_files"]}
    history = []
    warnings = []
    if intake["source_digests"]:
        pass
    for entry in intake["receipts"]:
        item = copy.deepcopy(entry)
        item["notes"] = sorted(set(item["notes"]))
        item["digest_status"] = "current" if entry["expected_candidate_digest"] == candidate_digest and entry["expected_submission_sha256"] == submission_sha256 else "stale"
        item["is_leaf"] = entry["receipt_id"] not in superseded
        if not entry["evidence_ids"]:
            item["evidence_status"] = "not_declared"
            if entry["receipt_status"] == "recorded":
                warnings.append(RECEIPT_EVIDENCE_WARNING)
        elif not set(entry["evidence_ids"]).issubset(declared_evidence_ids):
            item["evidence_status"] = "invalid"
        elif set(entry["evidence_ids"]).issubset(verified_evidence_ids):
            item["evidence_status"] = "verified"
        else:
            item["evidence_status"] = "missing"
        history.append(item)
    history.sort(key=lambda item: (receipt_revision(item["receipt_id"]), item["receipt_id"]))
    leaves = [item for item in history if item["is_leaf"]]
    if intake["candidate_digest"] != candidate_digest:
        warnings.append("Receipt intake candidate_digest does not match current candidate digest.")
    if intake["submission_sha256"] != submission_sha256:
        warnings.append("Receipt intake submission_sha256 does not match current submitted file digest.")
    if len(leaves) > 1:
        status = "conflicting"
        current = None
        authoritative = False
    elif not leaves:
        status = "not_provided"
        current = None
        authoritative = False
    else:
        current = leaves[0]
        if current["digest_status"] == "stale":
            status = "stale"
            authoritative = False
        else:
            status = current["receipt_status"]
            authoritative = current["actor"] == "human" and current["receipt_status"] in {"recorded", "retracted"}
    return {
        "status": status,
        "authoritative": authoritative,
        "current_receipt_id": current["receipt_id"] if current is not None else None,
        "history": history,
        "warnings": sorted(set(warnings)),
    }


def _receipt_source_digest_check(intake: dict[str, Any] | None, manifest_digest: str, archive_digest: str | None) -> dict[str, Any]:
    if intake is None:
        return _check("audit.receipt.source_digests_current", "receipt", True, "not_provided", "receipt intake source digests current", severity="informational")
    notes = []
    expected_archive = archive_digest or "missing"
    passed = intake["source_digests"]["handoff_manifest"] == manifest_digest and intake["source_digests"]["handoff_archive"] == archive_digest
    if not passed:
        notes.append("Receipt intake source_digests do not match current handoff manifest/archive digests.")
    return _check(
        "audit.receipt.source_digests_current",
        "receipt",
        passed,
        intake["source_digests"],
        {"handoff_manifest": manifest_digest, "handoff_archive": expected_archive},
        status="pass" if passed else "warning",
        severity="warning" if not passed else "informational",
        notes=notes,
    )


def _receipt_current_check(check_id: str, digest_name: str, state: dict[str, Any], intake: dict[str, Any] | None) -> dict[str, Any]:
    if intake is None or not state["history"]:
        return _check(check_id, "receipt", True, "not_provided", f"{digest_name} current", severity="informational")
    leaf = _single_leaf(state["history"])
    if leaf is None:
        return _check(check_id, "receipt", False, "multiple leaf receipts", "single current leaf", severity="warning")
    field = "expected_candidate_digest" if digest_name == "candidate_digest" else "expected_submission_sha256"
    passed = leaf["digest_status"] == "current"
    return _check(check_id, "receipt", passed, leaf[field], f"current {digest_name}", severity="warning" if not passed else "informational")


def _receipt_evidence_check(state: dict[str, Any], intake: dict[str, Any] | None, evidence_index: dict[str, Any]) -> dict[str, Any]:
    if intake is None:
        return _check("audit.receipt.evidence_files_valid", "receipt", True, "not_provided", "receipt evidence files valid", severity="informational")
    invalid = [item["receipt_id"] for item in state["history"] if item["evidence_status"] in {"missing", "invalid"}]
    declared = len(intake["evidence_files"])
    verified = len(evidence_index["items"])
    return _check(
        "audit.receipt.evidence_files_valid",
        "receipt",
        not invalid and declared == verified,
        {"declared": declared, "verified": verified, "invalid_receipts": invalid},
        "all declared evidence files are verified",
    )


def _audit_status(artifact_binding: str, receipt_status: str, authoritative: bool, evidence_blocker: bool) -> str:
    if artifact_binding == "blocked" or evidence_blocker:
        return "blocked"
    if receipt_status == "conflicting":
        return "conflicting"
    if receipt_status == "stale":
        return "stale"
    if receipt_status == "retracted":
        return "retracted"
    if receipt_status == "not_provided":
        return "awaiting_receipt"
    if receipt_status == "pending":
        return "pending"
    if receipt_status == "recorded" and authoritative:
        return "complete"
    return "conflicting"


def _platform_outcome(state: dict[str, Any]) -> dict[str, Any]:
    current = None
    if state["current_receipt_id"] is not None:
        for item in state["history"]:
            if item["receipt_id"] == state["current_receipt_id"]:
                current = item
                break
    if current is None or current["receipt_status"] != "recorded" or current["digest_status"] != "current":
        return {"platform": None, "submission_identifier": None, "submitted_at": None, "uploaded_filename": None, "platform_status": "unknown", "score": None}
    return {
        "platform": current["platform"],
        "submission_identifier": current["submission_identifier"],
        "submitted_at": current["submitted_at"],
        "uploaded_filename": current["uploaded_filename"],
        "platform_status": current["platform_status"],
        "score": current["score"],
    }


def _submission_entry(manifest: dict[str, Any]) -> dict[str, Any] | None:
    matches = [entry for entry in manifest["candidate"]["entries"] if entry["role"] == "submission"]
    return matches[0] if len(matches) == 1 else None


def _single_leaf(history: list[dict[str, Any]]) -> dict[str, Any] | None:
    leaves = [item for item in history if item.get("is_leaf")]
    return leaves[0] if len(leaves) == 1 else None


def _check(
    check_id: str,
    category: str,
    passed: bool,
    observed: Any,
    expected: Any,
    *,
    status: str | None = None,
    severity: str = "blocker",
    notes: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "category": category,
        "status": status or ("pass" if passed else "fail"),
        "severity": severity,
        "observed": observed,
        "expected": expected,
        "notes": sorted(set(notes or [])),
    }


def _regular_non_symlink(path: Path) -> bool:
    return path.exists() and path.is_file() and not path.is_symlink() and _safe_size(path) > 0


def _safe_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _file_observed(path: Path) -> dict[str, Any]:
    return {"exists": path.exists(), "regular_file": path.is_file() and not path.is_symlink(), "symlink": path.is_symlink(), "suffix": path.suffix, "size_bytes": _safe_size(path)}


def _md_value(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)
