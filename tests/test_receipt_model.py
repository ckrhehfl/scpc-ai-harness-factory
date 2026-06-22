from __future__ import annotations

import copy

import pytest

from factory.receipt_model import (
    ReceiptModelError,
    validate_post_submission_audit,
    validate_receipt_evidence_declaration,
    validate_submission_receipt_entry,
    validate_submission_receipt_intake,
)


DIGEST = "sha256:" + "1" * 64
SUBMISSION = "sha256:" + "2" * 64


def pending(receipt_id: str = "receipt.local_submission_candidate.r001") -> dict:
    return {
        "receipt_id": receipt_id,
        "scope": "local_submission_candidate",
        "expected_candidate_digest": DIGEST,
        "expected_submission_sha256": SUBMISSION,
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
        "supersedes": None,
        "notes": [],
    }


def recorded(receipt_id: str = "receipt.local_submission_candidate.r001", *, supersedes=None, platform_status="submitted", score=None) -> dict:
    item = pending(receipt_id)
    item.update(
        {
            "receipt_status": "recorded",
            "platform": "internal_mock",
            "submission_identifier": "SUB-2026-0001",
            "submitted_at": "2026-06-22T14:30:00+09:00",
            "uploaded_filename": "submission.csv",
            "platform_status": platform_status,
            "score": score,
            "rationale": "The frozen submission file was uploaded manually.",
            "supersedes": supersedes,
        }
    )
    return item


def retracted() -> dict:
    item = pending("receipt.local_submission_candidate.r002")
    item.update({"receipt_status": "retracted", "rationale": "The prior manual record was entered in error.", "supersedes": "receipt.local_submission_candidate.r001"})
    return item


def intake(receipts: list[dict], evidence_files: list[dict] | None = None) -> dict:
    return {
        "schema_version": "v0.13",
        "artifact_type": "submission_receipt_intake",
        "scope": "local_submission_candidate",
        "source_digests": {"handoff_manifest": DIGEST, "handoff_archive": SUBMISSION},
        "candidate_digest": DIGEST,
        "submission_sha256": SUBMISSION,
        "evidence_files": evidence_files or [],
        "receipts": receipts,
        "notes": [],
    }


def test_valid_pending_recorded_retracted_entries():
    validate_submission_receipt_entry(pending())
    validate_submission_receipt_entry(recorded())
    validate_submission_receipt_entry(retracted())


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda item: item.update({"receipt_id": "receipt.local_submission_candidate.r000"}), "revision"),
        (lambda item: item.update({"scope": "other"}), "scope"),
        (lambda item: item.update({"actor": "ai"}), "actor"),
        (lambda item: item.update({"platform": "internal_mock"}), "pending"),
    ],
)
def test_pending_rejects_invalid_shapes(mutate, message):
    item = pending()
    mutate(item)
    with pytest.raises(ReceiptModelError, match=message):
        validate_submission_receipt_entry(item)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda item: item.update({"platform": None}),
        lambda item: item.update({"submission_identifier": ""}),
        lambda item: item.update({"submitted_at": "2026-06-22T14:30:00"}),
        lambda item: item.update({"uploaded_filename": "../submission.csv"}),
        lambda item: item.update({"platform_status": "done"}),
        lambda item: item.update({"platform_status": "scored", "score": None}),
        lambda item: item.update({"score": {"value": "0.1", "metric": "accuracy", "scope": "public"}}),
    ],
)
def test_recorded_rejects_invalid_metadata(mutate):
    item = recorded()
    mutate(item)
    with pytest.raises(ReceiptModelError):
        validate_submission_receipt_entry(item)


def test_scored_score_shape_is_preserved_and_validated():
    item = recorded(platform_status="scored", score={"value": "0.81234", "metric": "accuracy", "scope": "public"})
    validate_submission_receipt_entry(item)
    bad = copy.deepcopy(item)
    bad["score"]["value"] = ""
    with pytest.raises(ReceiptModelError, match="score.value"):
        validate_submission_receipt_entry(bad)


def test_intake_rejects_duplicate_unknown_self_lower_supersession_and_cycle():
    with pytest.raises(ReceiptModelError, match="Duplicate receipt_id"):
        validate_submission_receipt_intake(intake([pending(), pending()]))
    with pytest.raises(ReceiptModelError, match="unknown"):
        validate_submission_receipt_intake(intake([recorded("receipt.local_submission_candidate.r002", supersedes="receipt.local_submission_candidate.r001")]))
    self_ref = recorded("receipt.local_submission_candidate.r001", supersedes="receipt.local_submission_candidate.r001")
    with pytest.raises(ReceiptModelError, match="itself"):
        validate_submission_receipt_intake(intake([self_ref]))
    lower = recorded("receipt.local_submission_candidate.r001", supersedes="receipt.local_submission_candidate.r002")
    with pytest.raises(ReceiptModelError, match="greater"):
        validate_submission_receipt_intake(intake([pending("receipt.local_submission_candidate.r002"), lower]))
    first = recorded("receipt.local_submission_candidate.r001", supersedes="receipt.local_submission_candidate.r002")
    second = recorded("receipt.local_submission_candidate.r002", supersedes="receipt.local_submission_candidate.r001")
    with pytest.raises(ReceiptModelError, match="greater|cycle"):
        validate_submission_receipt_intake(intake([first, second]))


def test_evidence_declaration_path_safety_and_reference_validation():
    declaration = {
        "evidence_id": "receipt_ev.confirmation_page",
        "relative_path": "confirmation.png",
        "media_type": "image/png",
        "description": "Submission confirmation page captured manually.",
    }
    validate_receipt_evidence_declaration(declaration)
    for path in ["/tmp/confirmation.png", "../confirmation.png", "folder\\confirmation.png"]:
        bad = dict(declaration, relative_path=path)
        with pytest.raises(ReceiptModelError):
            validate_receipt_evidence_declaration(bad)
    with pytest.raises(ReceiptModelError, match="duplicate"):
        validate_submission_receipt_intake(intake([], [declaration, copy.deepcopy(declaration)]))
    item = recorded()
    item["evidence_ids"] = ["receipt_ev.missing"]
    with pytest.raises(ReceiptModelError, match="unknown evidence"):
        validate_submission_receipt_intake(intake([item], [declaration]))


def test_audit_schema_and_history_sorting_validation():
    audit = {
        "schema_version": "v0.13",
        "artifact_type": "post_submission_audit",
        "scope": "local_submission_candidate",
        "status": "awaiting_receipt",
        "handoff_binding": {"status": "matched"},
        "receipt_state": {"status": "not_provided", "authoritative": False, "history": []},
        "checks": [],
    }
    validate_post_submission_audit(audit)
    audit["receipt_state"]["history"] = [
        {"receipt_id": "receipt.local_submission_candidate.r002"},
        {"receipt_id": "receipt.local_submission_candidate.r001"},
    ]
    with pytest.raises(ReceiptModelError, match="sorted"):
        validate_post_submission_audit(audit)
