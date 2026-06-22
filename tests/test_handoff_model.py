from __future__ import annotations

from pathlib import Path
import copy

import pytest

from factory.handoff_model import (
    HandoffModelError,
    sha256_bytes,
    sha256_file,
    validate_freeze_confirmation_entry,
    validate_freeze_confirmation_intake,
    validate_handoff_manifest,
    validate_package_path,
)


DIGEST = "sha256:" + "1" * 64


def confirmation(confirmation_id="freeze.local_submission_candidate.r001", *, status="pending", supersedes=None):
    return {
        "confirmation_id": confirmation_id,
        "scope": "local_submission_candidate",
        "expected_candidate_digest": DIGEST,
        "actor": "human",
        "confirmation_status": status,
        "rationale": "" if status == "pending" else "I confirm this candidate digest.",
        "supersedes": supersedes,
        "notes": [],
    }


def intake(*entries):
    return {
        "schema_version": "v0.12",
        "artifact_type": "freeze_confirmation_intake",
        "scope": "local_submission_candidate",
        "candidate_digest": DIGEST,
        "confirmations": list(entries),
        "notes": [],
    }


def manifest(entries=None):
    entries = entries or [
        {
            "package_path": "submission/submission.csv",
            "role": "submission",
            "media_type": "text/csv",
            "sha256": DIGEST,
            "size_bytes": 3,
            "source_canonical_digest": None,
        }
    ]
    return {
        "schema_version": "v0.12",
        "artifact_type": "submission_handoff_manifest",
        "scope": "local_submission_candidate",
        "status": "prepared",
        "preflight": {"status": "pass", "blocker_count": 0, "warning_count": 0, "checks": []},
        "candidate": {"candidate_digest": DIGEST, "entry_count": len(entries), "total_size_bytes": sum(e["size_bytes"] for e in entries), "entries": entries},
    }


def test_byte_digest_deterministic_and_file_digest_matches(tmp_path: Path):
    data = b"a,b\n1,2\n"
    target = tmp_path / "submission.csv"
    target.write_bytes(data)

    assert sha256_bytes(data) == sha256_bytes(data)
    assert sha256_file(target) == sha256_bytes(data)


@pytest.mark.parametrize("path", ["submission/submission.csv", "HANDOFF.md", "a/b/c.json"])
def test_package_path_allows_posix_relative(path):
    validate_package_path(path)


@pytest.mark.parametrize("path", ["/abs/file", "C:/x/file", "../x", "a/../b", "a\\b", "a//b", "a/./b", ""])
def test_package_path_rejects_unsafe(path):
    with pytest.raises(HandoffModelError):
        validate_package_path(path)


@pytest.mark.parametrize("status", ["pending", "confirmed", "rejected"])
def test_valid_confirmation_status_shapes(status):
    validate_freeze_confirmation_entry(confirmation(status=status))


def test_confirmation_rejects_non_human_and_r000_and_missing_rationale():
    bad = confirmation()
    bad["actor"] = "ai"
    with pytest.raises(HandoffModelError):
        validate_freeze_confirmation_entry(bad)

    bad = confirmation("freeze.local_submission_candidate.r000")
    with pytest.raises(HandoffModelError):
        validate_freeze_confirmation_entry(bad)

    for status in ["confirmed", "rejected"]:
        bad = confirmation(status=status)
        bad["rationale"] = ""
        with pytest.raises(HandoffModelError):
            validate_freeze_confirmation_entry(bad)


def test_supersession_validation_duplicate_unknown_self_revision_and_cycle():
    first = confirmation()
    duplicate = confirmation()
    with pytest.raises(HandoffModelError):
        validate_freeze_confirmation_intake(intake(first, duplicate))

    second = confirmation("freeze.local_submission_candidate.r002", supersedes="freeze.local_submission_candidate.r404")
    with pytest.raises(HandoffModelError):
        validate_freeze_confirmation_intake(intake(first, second))

    self_ref = confirmation("freeze.local_submission_candidate.r002", supersedes="freeze.local_submission_candidate.r002")
    with pytest.raises(HandoffModelError):
        validate_freeze_confirmation_intake(intake(self_ref))

    lower = confirmation("freeze.local_submission_candidate.r001", supersedes="freeze.local_submission_candidate.r002")
    with pytest.raises(HandoffModelError):
        validate_freeze_confirmation_intake(intake(lower), known_confirmation_ids={"freeze.local_submission_candidate.r002"})

    a = confirmation("freeze.local_submission_candidate.r001", supersedes="freeze.local_submission_candidate.r002")
    b = confirmation("freeze.local_submission_candidate.r002", supersedes="freeze.local_submission_candidate.r001")
    with pytest.raises(HandoffModelError):
        validate_freeze_confirmation_intake(intake(a, b))


def test_manifest_summary_counts_sorting_duplicate_and_candidate_digest_validation():
    validate_handoff_manifest(manifest())

    bad = manifest()
    bad["candidate"]["entry_count"] = 2
    with pytest.raises(HandoffModelError):
        validate_handoff_manifest(bad)

    bad = manifest(
        [
            {
                "package_path": "z/file.json",
                "role": "requirements",
                "media_type": "application/json",
                "sha256": DIGEST,
                "size_bytes": 1,
                "source_canonical_digest": DIGEST,
            },
            {
                "package_path": "a/file.json",
                "role": "submission",
                "media_type": "text/csv",
                "sha256": DIGEST,
                "size_bytes": 1,
                "source_canonical_digest": None,
            },
        ]
    )
    with pytest.raises(HandoffModelError):
        validate_handoff_manifest(bad)

    bad = manifest()
    bad["candidate"]["entries"] = [copy.deepcopy(bad["candidate"]["entries"][0]), copy.deepcopy(bad["candidate"]["entries"][0])]
    bad["candidate"]["entry_count"] = 2
    bad["candidate"]["total_size_bytes"] = 6
    with pytest.raises(HandoffModelError):
        validate_handoff_manifest(bad)

    bad = manifest()
    bad["candidate"]["candidate_digest"] = "sha256:bad"
    with pytest.raises(HandoffModelError):
        validate_handoff_manifest(bad)
