from __future__ import annotations

from pathlib import Path
from typing import Any
import copy
import csv
import io
import json
import os
import shutil
import stat
import tempfile
import zipfile

from factory.approval_model import build_readiness_digest, validate_human_approval_summary
from factory.decision_model import canonical_json_digest
from factory.handoff_model import (
    FREEZE_CONFIRMATION_ARTIFACT_TYPE,
    HANDOFF_MANIFEST_ARTIFACT_TYPE,
    HANDOFF_SCOPE,
    SCHEMA_VERSION,
    HandoffModelError,
    freeze_confirmation_revision,
    sha256_bytes,
    validate_freeze_confirmation_intake,
    validate_handoff_manifest,
    validate_package_path,
)
from factory.utils import write_json, write_text


SOURCE_DIGEST_KEYS = [
    "contest_requirements",
    "requirement_capability_match",
    "decision_ledger",
    "capability_registry",
    "validation_report",
]
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


def load_freeze_confirmation_intake(path: str | Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    source = Path(path)
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HandoffModelError(f"Malformed freeze confirmation JSON: {exc}") from exc
    except OSError as exc:
        raise HandoffModelError(f"Could not read freeze confirmation: {exc}") from exc
    if not isinstance(data, dict):
        raise HandoffModelError("Freeze confirmation intake must be a JSON object")
    validate_freeze_confirmation_intake(data)
    return data


def build_submission_handoff(
    *,
    submission_path: str | Path,
    validation_report: dict[str, Any],
    human_approval_summary: dict[str, Any],
    decision_ledger: dict[str, Any],
    requirements: dict[str, Any],
    matches: dict[str, Any],
    capabilities: dict[str, Any],
    freeze_confirmation: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    validate_human_approval_summary(human_approval_summary)
    _validate_validation_report_shape(validation_report)
    if freeze_confirmation is not None:
        validate_freeze_confirmation_intake(freeze_confirmation)

    submission = Path(submission_path)
    source_digests = {
        "human_approval_summary": canonical_json_digest(human_approval_summary),
        "decision_ledger": canonical_json_digest(decision_ledger),
        "contest_requirements": canonical_json_digest(requirements),
        "requirement_capability_match": canonical_json_digest(matches),
        "capability_registry": canonical_json_digest(capabilities),
        "validation_report": canonical_json_digest(validation_report),
    }
    checks = _preflight_checks(
        submission,
        validation_report,
        human_approval_summary,
        source_digests,
    )
    preflight = _preflight_summary(checks)

    package_files: dict[str, bytes] = {}
    candidate = {"candidate_digest": None, "entry_count": 0, "total_size_bytes": 0, "entries": []}
    freeze_state = _empty_freeze_state()
    status = "blocked" if preflight["blocker_count"] else "prepared"
    warnings: list[str] = []

    if preflight["blocker_count"] == 0:
        sanitized = _sanitized_validation_evidence(validation_report, source_digests["validation_report"])
        package_files = {
            "submission/submission.csv": submission.read_bytes(),
            "evidence/validation_evidence.json": _json_bytes(sanitized),
            "governance/human_approval_summary.json": _json_bytes(human_approval_summary),
            "governance/decision_ledger.json": _json_bytes(decision_ledger),
            "requirements/contest_requirements.json": _json_bytes(requirements),
            "requirements/requirement_capability_match.json": _json_bytes(matches),
            "capabilities/capability_registry.json": _json_bytes(capabilities),
        }
        entries = _package_entries(
            package_files,
            {
                "evidence/validation_evidence.json": source_digests["validation_report"],
                "governance/human_approval_summary.json": source_digests["human_approval_summary"],
                "governance/decision_ledger.json": source_digests["decision_ledger"],
                "requirements/contest_requirements.json": source_digests["contest_requirements"],
                "requirements/requirement_capability_match.json": source_digests["requirement_capability_match"],
                "capabilities/capability_registry.json": source_digests["capability_registry"],
            },
        )
        approval = human_approval_summary["human_approval"]
        candidate_payload = {
            "schema_version": SCHEMA_VERSION,
            "scope": HANDOFF_SCOPE,
            "approval_readiness_digest": human_approval_summary["readiness_digest"],
            "current_approval_id": approval["current_approval_id"],
            "validation_source_digest": source_digests["validation_report"],
            "entries": entries,
        }
        candidate_digest = canonical_json_digest(candidate_payload)
        candidate = {
            "candidate_digest": candidate_digest,
            "entry_count": len(entries),
            "total_size_bytes": sum(entry["size_bytes"] for entry in entries),
            "entries": entries,
        }
        freeze_state = _freeze_confirmation_state(freeze_confirmation, candidate_digest)
        status = _handoff_status(preflight, freeze_state)
        if freeze_state["warnings"]:
            warnings.extend(freeze_state["warnings"])

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": HANDOFF_MANIFEST_ARTIFACT_TYPE,
        "scope": HANDOFF_SCOPE,
        "status": status,
        "source_artifacts": {
            "human_approval_summary": "human_approval_summary.json",
            "decision_ledger": "decision_ledger.json",
            "contest_requirements": "contest_requirements.json",
            "requirement_capability_match": "requirement_capability_match.json",
            "capability_registry": "capability_registry.json",
            "validation_report": "validation_report.json",
            "submission": "submission.csv",
            "freeze_confirmation": "freeze_confirmation_intake.json" if freeze_confirmation is not None else None,
        },
        "source_digests": source_digests,
        "approval_binding": {
            "overall_gate_status": human_approval_summary["overall_gate"]["status"],
            "readiness_digest": human_approval_summary["readiness_digest"],
            "current_approval_id": human_approval_summary["human_approval"]["current_approval_id"],
            "authoritative": human_approval_summary["human_approval"]["authoritative"],
            "approval_granted": human_approval_summary["human_approval"]["approval_granted"],
        },
        "preflight": preflight,
        "candidate": candidate,
        "freeze_confirmation": freeze_state,
        "package": {
            "directory": "submission_handoff_package" if candidate["candidate_digest"] else None,
            "archive": "submission_handoff_package.zip" if candidate["candidate_digest"] else None,
            "archive_format": "zip_stored",
            "deterministic": True,
        },
        "warnings": sorted(set(warnings)),
    }
    if package_files:
        freeze_manifest = _freeze_manifest(manifest)
        package_files["freeze_manifest.json"] = _json_bytes(freeze_manifest)
        if freeze_confirmation is not None:
            package_files["governance/freeze_confirmation.json"] = _json_bytes(freeze_confirmation)
        package_files["HANDOFF.md"] = render_submission_handoff_markdown(manifest).encode("utf-8")
    _validate_package_allowlist(package_files)
    validate_handoff_manifest(manifest)
    return manifest, package_files


def build_freeze_confirmation_template(manifest: dict[str, Any]) -> dict[str, Any]:
    validate_handoff_manifest(manifest)
    confirmations = []
    notes: list[str] = []
    candidate_digest = manifest["candidate"]["candidate_digest"]
    if manifest["preflight"]["blocker_count"]:
        notes.append("Handoff preflight is blocked; freeze confirmation cannot be requested.")
    elif manifest["freeze_confirmation"]["status"] == "conflicting":
        notes.append("Manual freeze confirmation conflict resolution is required.")
    elif manifest["freeze_confirmation"]["status"] in {"confirmed", "rejected"}:
        pass
    else:
        leaf = _single_leaf(manifest["freeze_confirmation"]["history"])
        supersedes = None
        if leaf and manifest["freeze_confirmation"]["status"] in {"pending", "stale", "not_provided"}:
            supersedes = leaf["confirmation_id"]
        revision = freeze_confirmation_revision(supersedes) + 1 if supersedes else 1
        confirmations.append(
            {
                "confirmation_id": f"freeze.local_submission_candidate.r{revision:03d}",
                "scope": HANDOFF_SCOPE,
                "expected_candidate_digest": candidate_digest,
                "actor": "human",
                "confirmation_status": "pending",
                "rationale": "",
                "supersedes": supersedes,
                "notes": [],
            }
        )
    template = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": FREEZE_CONFIRMATION_ARTIFACT_TYPE,
        "scope": HANDOFF_SCOPE,
        "candidate_digest": candidate_digest or "sha256:" + "0" * 64,
        "confirmations": confirmations,
        "notes": sorted(set(notes)),
    }
    known_ids = {item["confirmation_id"] for item in manifest["freeze_confirmation"]["history"]}
    validate_freeze_confirmation_intake(template, known_confirmation_ids=known_ids)
    return template


def render_submission_handoff_markdown(manifest: dict[str, Any]) -> str:
    validate_handoff_manifest(manifest)
    lines = [
        "# Submission Handoff Package",
        "",
        "이 package는 local_submission_candidate의 전달용 동결 자료다.",
        "status=frozen은 현재 package byte가 Human Freeze Confirmation과 일치함을 뜻한다.",
        "공식 대회 제출 완료, 제출 허용, solver 성능 또는 leaderboard 결과를 보장하지 않는다.",
        "온라인 제출은 사람이 별도로 수행해야 한다.",
        "",
    ]
    if manifest["status"] != "frozen":
        lines.extend(["**NOT FROZEN - DO NOT SUBMIT AS FINAL**", ""])
    lines.extend(
        [
            "## Status",
            "",
            f"- handoff status: {manifest['status']}",
            f"- candidate digest: {manifest['candidate']['candidate_digest'] or 'none'}",
            f"- approval readiness digest: {manifest['approval_binding']['readiness_digest']}",
            f"- current approval ID: {manifest['approval_binding']['current_approval_id'] or 'none'}",
            f"- freeze confirmation ID: {manifest['freeze_confirmation']['current_confirmation_id'] or 'none'}",
            "",
            "## Validation Summary",
            "",
            f"- preflight status: {manifest['preflight']['status']}",
            f"- blockers: {manifest['preflight']['blocker_count']}",
            f"- warnings: {manifest['preflight']['warning_count']}",
            "",
            "## Package Entries",
            "",
        ]
    )
    if not manifest["candidate"]["entries"]:
        lines.append("- none")
    for entry in manifest["candidate"]["entries"]:
        label = entry["package_path"]
        if entry["role"] == "submission":
            label += f" (submission digest: {entry['sha256']})"
        lines.append(f"- {label} | {entry['role']} | {entry['size_bytes']} bytes | `{entry['sha256']}`")
    lines.extend(
        [
            "",
            "## Caveats",
            "",
            "- frozen은 local handoff package byte와 candidate digest에 대한 확인만 의미한다.",
            "- raw validation report는 로컬 경로와 세부 메시지를 포함할 수 있어 package에서 제외된다.",
            "- solver 성능, 공식 규칙 준수, 실제 업로드 성공은 별도 확인 대상이다.",
            "",
            "## Manual Verification",
            "",
            "```bash",
            "python -m zipfile -l generated/submission_handoff_package.zip",
            "python factory/run_submission_handoff.py --help",
            "```",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def save_submission_handoff_outputs(
    manifest: dict[str, Any],
    template: dict[str, Any],
    package_files: dict[str, bytes],
    output_dir: str | Path,
) -> dict[str, Path]:
    validate_handoff_manifest(manifest)
    validate_freeze_confirmation_intake(template, known_confirmation_ids={item["confirmation_id"] for item in manifest["freeze_confirmation"]["history"]})
    _validate_package_allowlist(package_files)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    package_dir = out / "submission_handoff_package"
    package_zip = out / "submission_handoff_package.zip"

    paths = {
        "manifest_json": out / "submission_handoff_manifest.json",
        "manifest_md": out / "submission_handoff.md",
        "freeze_template": out / "freeze_confirmation_template.json",
        "package_dir": package_dir,
        "package_zip": package_zip,
    }
    if package_files:
        with tempfile.TemporaryDirectory(dir=out) as tmp_name:
            tmp_dir = Path(tmp_name)
            staged_package = tmp_dir / "submission_handoff_package"
            for package_path, data in sorted(package_files.items()):
                validate_package_path(package_path)
                target = staged_package / package_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                target.chmod(0o644)
            staged_zip = tmp_dir / "submission_handoff_package.zip"
            _write_deterministic_zip(staged_zip, package_files)
            _replace_path(package_dir, staged_package)
            _replace_path(package_zip, staged_zip)
    else:
        _remove_path(package_dir)
        _remove_path(package_zip)

    write_json(paths["manifest_json"], manifest)
    write_text(paths["manifest_md"], render_submission_handoff_markdown(manifest))
    write_json(paths["freeze_template"], template)
    return paths


def _preflight_checks(
    submission: Path,
    validation_report: dict[str, Any],
    summary: dict[str, Any],
    source_digests: dict[str, str],
) -> list[dict[str, Any]]:
    checks = []
    overall = summary["overall_gate"]
    machine = summary["machine_readiness"]
    human = summary["human_approval"]
    checks.append(_check("handoff.approval.summary_approved", overall["status"] == "approved", overall["status"], "approved"))
    checks.append(_check("handoff.approval.machine_reviewable", machine["status"] == "reviewable", machine["status"], "reviewable"))
    checks.append(_check("handoff.approval.human_authoritative", human["authoritative"] is True, human["authoritative"], True))
    checks.append(_check("handoff.approval.granted", human["approval_granted"] is True, human["approval_granted"], True))

    for check_id, summary_key, current_key in [
        ("handoff.sources.requirements_digest_current", "contest_requirements", "contest_requirements"),
        ("handoff.sources.match_digest_current", "requirement_capability_match", "requirement_capability_match"),
        ("handoff.sources.ledger_digest_current", "decision_ledger", "decision_ledger"),
        ("handoff.sources.capabilities_digest_current", "capability_registry", "capability_registry"),
        ("handoff.sources.validation_digest_current", "validation_report", "validation_report"),
    ]:
        expected = summary["source_digests"].get(summary_key)
        observed = source_digests[current_key]
        checks.append(_check(check_id, observed == expected, observed, expected))

    recomputed = build_readiness_digest(summary["source_digests"], summary["machine_readiness"])
    checks.append(_check("handoff.approval.readiness_digest_current", recomputed == summary["readiness_digest"], recomputed, summary["readiness_digest"]))
    current = _current_approval(summary)
    expected_readiness = current.get("expected_readiness_digest") if current else None
    checks.append(
        _check(
            "handoff.approval.expected_readiness_digest_current",
            expected_readiness == summary["readiness_digest"],
            expected_readiness,
            summary["readiness_digest"],
        )
    )

    safety = _submission_safety(submission)
    checks.extend(safety["checks"])
    report_path_match = _report_path_matches(submission, validation_report)
    checks.append(_check("handoff.submission.report_path_matches", report_path_match, report_path_match, True))
    checks.append(_snapshot_check(submission, validation_report, safety["columns"], safety["row_count"]))
    validation_passed = validation_report.get("passed") is True and validation_report.get("error_count") == 0
    checks.append(_check("handoff.validation.passed", validation_passed, {"passed": validation_report.get("passed"), "error_count": validation_report.get("error_count")}, {"passed": True, "error_count": 0}))
    return sorted(checks, key=lambda item: item["check_id"])


def _submission_safety(submission: Path) -> dict[str, Any]:
    checks = []
    columns: list[str] | None = None
    row_count: int | None = None
    exists = submission.exists()
    is_symlink = submission.is_symlink()
    is_file = exists and submission.is_file() and not is_symlink
    size = submission.stat().st_size if is_file else 0
    checks.append(_check("handoff.submission.regular_file", bool(is_file and size > 0 and submission.suffix == ".csv"), {"exists": exists, "regular_file": is_file, "size_bytes": size, "suffix": submission.suffix}, {"regular_file": True, "size_bytes": ">0", "suffix": ".csv"}))
    checks.append(_check("handoff.submission.not_symlink", not is_symlink, is_symlink, False))
    readable = False
    notes: list[str] = []
    if is_file and size > 0:
        try:
            raw = submission.read_bytes()
            text = raw.decode("utf-8-sig")
            reader = csv.reader(io.StringIO(text, newline=""))
            rows = list(reader)
            if rows and rows[0]:
                columns = rows[0]
                row_count = max(0, len(rows) - 1)
                readable = True
        except (OSError, UnicodeDecodeError, csv.Error) as exc:
            notes.append(type(exc).__name__)
    checks.append(_check("handoff.submission.csv_readable", readable, {"readable": readable, "column_count": len(columns or [])}, {"readable": True, "column_count": ">=1"}, notes=notes))
    return {"checks": checks, "columns": columns, "row_count": row_count}


def _report_path_matches(submission: Path, validation_report: dict[str, Any]) -> bool:
    report_path = validation_report.get("submission_path")
    if not isinstance(report_path, str) or not report_path:
        for check in validation_report.get("checks", []):
            if isinstance(check, dict):
                details = check.get("details", {})
                if isinstance(details, dict) and isinstance(details.get("submission_path"), str):
                    report_path = details["submission_path"]
                    break
    if not isinstance(report_path, str) or not report_path:
        return False
    try:
        return Path(report_path).resolve() == submission.resolve()
    except OSError:
        return False


def _snapshot_check(submission: Path, report: dict[str, Any], columns: list[str] | None, row_count: int | None) -> dict[str, Any]:
    expected_columns = _check_detail(report, "required_columns_present", "submission_columns")
    expected_row_count = _check_detail(report, "row_count_matches_test", "submission_row_count")
    notes = []
    passed = True
    observed: dict[str, Any] = {}
    expected: dict[str, Any] = {}
    if expected_columns is None:
        notes.append("validation report did not expose submission_columns snapshot")
    else:
        observed["submission_columns"] = columns
        expected["submission_columns"] = expected_columns
        passed = passed and columns == expected_columns
    if expected_row_count is None:
        notes.append("validation report did not expose submission_row_count snapshot")
    else:
        observed["submission_row_count"] = row_count
        expected["submission_row_count"] = expected_row_count
        passed = passed and row_count == expected_row_count
    status = "pass" if passed else "fail"
    severity = "blocker" if not passed else ("warning" if notes else "blocker")
    if passed and notes:
        status = "warning"
    return _check("handoff.submission.snapshot_consistent", passed and not notes, observed or None, expected or "snapshot details present", status=status, severity=severity, notes=notes)


def _check_detail(report: dict[str, Any], name: str, key: str) -> Any:
    for check in report.get("checks", []):
        if isinstance(check, dict) and check.get("name") == name:
            details = check.get("details")
            if isinstance(details, dict) and key in details:
                return details[key]
    return None


def _validate_validation_report_shape(report: dict[str, Any]) -> None:
    if not isinstance(report, dict):
        raise HandoffModelError("Validation report must be a JSON object")
    if not isinstance(report.get("passed"), bool):
        raise HandoffModelError("validation_report.passed must be a bool")
    for field in ["error_count", "warning_count"]:
        if not isinstance(report.get(field), int) or report[field] < 0:
            raise HandoffModelError(f"validation_report.{field} must be a non-negative int")
    if not isinstance(report.get("checks"), list):
        raise HandoffModelError("validation_report.checks must be a list")


def _sanitized_validation_evidence(report: dict[str, Any], source_digest: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "sanitized_validation_evidence",
        "source_digest": source_digest,
        "passed": report["passed"],
        "error_count": report["error_count"],
        "warning_count": report["warning_count"],
        "checks": sorted(
            [
                {
                    "name": check["name"],
                    "passed": check["passed"],
                    "severity": check["severity"],
                }
                for check in report["checks"]
                if isinstance(check, dict)
            ],
            key=lambda item: item["name"],
        ),
    }


def _package_entries(package_files: dict[str, bytes], source_digests: dict[str, str]) -> list[dict[str, Any]]:
    roles = {
        "submission/submission.csv": ("submission", "text/csv"),
        "evidence/validation_evidence.json": ("validation_evidence", "application/json"),
        "governance/human_approval_summary.json": ("human_approval", "application/json"),
        "governance/decision_ledger.json": ("decision_ledger", "application/json"),
        "requirements/contest_requirements.json": ("requirements", "application/json"),
        "requirements/requirement_capability_match.json": ("requirement_match", "application/json"),
        "capabilities/capability_registry.json": ("capability_registry", "application/json"),
    }
    entries = []
    for path, data in sorted(package_files.items()):
        if path not in SUBSTANTIVE_PATHS:
            continue
        role, media_type = roles[path]
        entries.append(
            {
                "package_path": path,
                "role": role,
                "media_type": media_type,
                "sha256": sha256_bytes(data),
                "size_bytes": len(data),
                "source_canonical_digest": source_digests.get(path),
            }
        )
    return entries


def _freeze_confirmation_state(freeze: dict[str, Any] | None, candidate_digest: str) -> dict[str, Any]:
    if freeze is None:
        return _empty_freeze_state()
    superseded = {entry["supersedes"] for entry in freeze["confirmations"] if entry["supersedes"] is not None}
    history = []
    for entry in freeze["confirmations"]:
        item = copy.deepcopy(entry)
        item["notes"] = sorted(set(item["notes"]))
        item["digest_status"] = "current" if item["expected_candidate_digest"] == candidate_digest else "stale"
        item["is_leaf"] = item["confirmation_id"] not in superseded
        history.append(item)
    history.sort(key=lambda item: (freeze_confirmation_revision(item["confirmation_id"]), item["confirmation_id"]))
    leaves = [item for item in history if item["is_leaf"]]
    warnings = []
    if freeze["candidate_digest"] != candidate_digest:
        warnings.append("Freeze confirmation intake candidate_digest does not match current candidate digest.")
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
        elif current["confirmation_status"] == "pending":
            status = "pending"
            authoritative = False
        else:
            status = current["confirmation_status"]
            authoritative = current["actor"] == "human" and current["confirmation_status"] == "confirmed"
    return {
        "status": status,
        "authoritative": authoritative,
        "current_confirmation_id": current["confirmation_id"] if current is not None else None,
        "history": history,
        "warnings": sorted(set(warnings)),
    }


def _empty_freeze_state() -> dict[str, Any]:
    return {
        "status": "not_provided",
        "authoritative": False,
        "current_confirmation_id": None,
        "history": [],
        "warnings": [],
    }


def _handoff_status(preflight: dict[str, Any], freeze: dict[str, Any]) -> str:
    if preflight["blocker_count"]:
        return "blocked"
    if freeze["status"] == "conflicting":
        return "conflicting"
    if freeze["status"] == "stale":
        return "stale"
    if freeze["status"] == "rejected":
        return "rejected"
    if freeze["status"] == "confirmed" and freeze["authoritative"]:
        return "frozen"
    return "prepared"


def _preflight_summary(checks: list[dict[str, Any]]) -> dict[str, Any]:
    blocker_count = sum(1 for item in checks if item["severity"] == "blocker" and item["status"] == "fail")
    warning_count = sum(1 for item in checks if item["severity"] == "warning" or item["status"] == "warning")
    return {
        "status": "fail" if blocker_count else ("warning" if warning_count else "pass"),
        "blocker_count": blocker_count,
        "warning_count": warning_count,
        "checks": checks,
    }


def _check(
    check_id: str,
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
        "status": status or ("pass" if passed else "fail"),
        "severity": severity,
        "observed": observed,
        "expected": expected,
        "notes": sorted(set(notes or [])),
    }


def _current_approval(summary: dict[str, Any]) -> dict[str, Any] | None:
    current_id = summary["human_approval"]["current_approval_id"]
    for item in summary["human_approval"]["history"]:
        if item["approval_id"] == current_id:
            return item
    return None


def _freeze_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "freeze_manifest",
        "scope": HANDOFF_SCOPE,
        "status": manifest["status"],
        "candidate_digest": manifest["candidate"]["candidate_digest"],
        "approval_readiness_digest": manifest["approval_binding"]["readiness_digest"],
        "current_approval_id": manifest["approval_binding"]["current_approval_id"],
        "freeze_confirmation_status": manifest["freeze_confirmation"]["status"],
        "current_confirmation_id": manifest["freeze_confirmation"]["current_confirmation_id"],
        "entries": copy.deepcopy(manifest["candidate"]["entries"]),
    }


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _validate_package_allowlist(package_files: dict[str, bytes]) -> None:
    for path in package_files:
        validate_package_path(path)
        if path not in PACKAGE_ALLOWLIST:
            raise HandoffModelError(f"Package path is not allowlisted: {path}")
    if package_files and not SUBSTANTIVE_PATHS.issubset(package_files):
        missing = sorted(SUBSTANTIVE_PATHS - set(package_files))
        raise HandoffModelError(f"Package missing required path(s): {', '.join(missing)}")


def _write_deterministic_zip(path: Path, package_files: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.comment = b""
        for package_path, data in sorted(package_files.items()):
            info = zipfile.ZipInfo(package_path, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.extra = b""
            archive.writestr(info, data)


def _replace_path(target: Path, source: Path) -> None:
    _remove_path(target)
    os.replace(source, target)


def _remove_path(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    elif path.exists() or path.is_symlink():
        path.unlink()


def _single_leaf(history: list[dict[str, Any]]) -> dict[str, Any] | None:
    leaves = [item for item in history if item.get("is_leaf")]
    return leaves[0] if len(leaves) == 1 else None
