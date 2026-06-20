from __future__ import annotations

from pathlib import Path
import csv
import sys


HARNESS_TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "base_harness"
if str(HARNESS_TEMPLATE) not in sys.path:
    sys.path.insert(0, str(HARNESS_TEMPLATE))

from src.verifier import build_validation_report


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def make_config(tmp_path: Path) -> dict:
    test_path = tmp_path / "test.csv"
    sample_path = tmp_path / "sample_submission.csv"
    write_csv(test_path, ["id", "text"], [{"id": "1", "text": "a"}, {"id": "2", "text": "b"}])
    write_csv(sample_path, ["id", "label"], [{"id": "1", "label": "positive"}])
    return {
        "output": {
            "required_columns": ["id", "label"],
            "id_column": "id",
            "target_column": "label",
            "value_constraints": {"allowed_labels": ["positive", "negative"]},
        },
        "verifier": {
            "test_csv_path": str(test_path),
            "sample_submission_csv_path": str(sample_path),
        },
    }


def failed_check_names(report: dict) -> set[str]:
    return {check["name"] for check in report["checks"] if not check["passed"] and check["severity"] == "error"}


def test_valid_submission_passes(tmp_path: Path):
    config = make_config(tmp_path)
    submission_path = tmp_path / "submission.csv"
    write_csv(
        submission_path,
        ["id", "label"],
        [{"id": "1", "label": "positive"}, {"id": "2", "label": "negative"}],
    )

    report = build_validation_report(submission_path, config)

    assert report["passed"] is True
    assert report["error_count"] == 0


def test_missing_required_column_fails(tmp_path: Path):
    config = make_config(tmp_path)
    submission_path = tmp_path / "submission.csv"
    write_csv(submission_path, ["id"], [{"id": "1"}, {"id": "2"}])

    report = build_validation_report(submission_path, config)

    assert report["passed"] is False
    assert "required_columns_present" in failed_check_names(report)


def test_row_count_mismatch_fails(tmp_path: Path):
    config = make_config(tmp_path)
    submission_path = tmp_path / "submission.csv"
    write_csv(submission_path, ["id", "label"], [{"id": "1", "label": "positive"}])

    report = build_validation_report(submission_path, config)

    assert report["passed"] is False
    assert "row_count_matches_test" in failed_check_names(report)


def test_duplicate_id_fails(tmp_path: Path):
    config = make_config(tmp_path)
    submission_path = tmp_path / "submission.csv"
    write_csv(
        submission_path,
        ["id", "label"],
        [{"id": "1", "label": "positive"}, {"id": "1", "label": "negative"}],
    )

    report = build_validation_report(submission_path, config)

    assert report["passed"] is False
    assert "id_column_unique" in failed_check_names(report)


def test_allowed_labels_outside_value_fails(tmp_path: Path):
    config = make_config(tmp_path)
    submission_path = tmp_path / "submission.csv"
    write_csv(
        submission_path,
        ["id", "label"],
        [{"id": "1", "label": "positive"}, {"id": "2", "label": "maybe"}],
    )

    report = build_validation_report(submission_path, config)

    assert report["passed"] is False
    assert "target_values_in_allowed_labels" in failed_check_names(report)


def test_extra_columns_are_reported_as_warning(tmp_path: Path):
    config = make_config(tmp_path)
    submission_path = tmp_path / "submission.csv"
    write_csv(
        submission_path,
        ["id", "label", "confidence"],
        [{"id": "1", "label": "positive", "confidence": "0.9"}, {"id": "2", "label": "negative", "confidence": "0.8"}],
    )

    report = build_validation_report(submission_path, config)

    assert report["passed"] is True
    assert report["warning_count"] == 1
    warning = next(check for check in report["checks"] if check["name"] == "no_extra_columns")
    assert warning["severity"] == "warning"
    assert warning["details"]["extra_columns"] == ["confidence"]
