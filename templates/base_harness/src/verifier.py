from __future__ import annotations

from pathlib import Path
import csv
import json
from typing import Any


def verify_submission_rows(rows: list[dict[str, Any]], config: dict[str, Any]) -> list[dict[str, Any]]:
    output = config.get("output", {})
    required_columns = output.get("required_columns") or []
    if not required_columns:
        raise ValueError("No required_columns in config.output")

    for idx, row in enumerate(rows):
        missing = [col for col in required_columns if col not in row]
        if missing:
            raise ValueError(f"Row {idx} missing required columns: {missing}")
        for col in required_columns:
            if row.get(col) is None or str(row.get(col)) == "":
                raise ValueError(f"Row {idx} has empty value for column: {col}")
    return rows


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader.fieldnames or []), list(reader)


def _resolve_path(value: str | None, root: Path) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    cwd_path = Path.cwd() / path
    if cwd_path.exists():
        return cwd_path
    return root / path


def _check(
    checks: list[dict[str, Any]],
    name: str,
    passed: bool,
    message: str,
    *,
    severity: str = "error",
    details: dict[str, Any] | None = None,
) -> None:
    checks.append({
        "name": name,
        "passed": passed,
        "severity": severity,
        "message": message,
        "details": details or {},
    })


def build_validation_report(
    submission_path: str | Path,
    config: dict[str, Any],
    *,
    root: str | Path | None = None,
) -> dict[str, Any]:
    root_path = Path(root) if root is not None else Path.cwd()
    output = config.get("output", {})
    verifier = config.get("verifier", {})

    required_columns = list(output.get("required_columns") or verifier.get("required_columns") or [])
    id_column = output.get("id_column") or verifier.get("id_column")
    target_column = output.get("target_column") or verifier.get("target_column")
    value_constraints = output.get("value_constraints")
    if not isinstance(value_constraints, dict):
        value_constraints = verifier.get("value_constraints")
    if not isinstance(value_constraints, dict):
        value_constraints = {}

    submission = Path(submission_path)
    test_path = _resolve_path(verifier.get("test_csv_path"), root_path)
    sample_path = _resolve_path(verifier.get("sample_submission_csv_path"), root_path)
    checks: list[dict[str, Any]] = []

    submission_exists = submission.exists()
    _check(
        checks,
        "submission_file_exists",
        submission_exists,
        f"submission.csv exists: {submission}" if submission_exists else f"submission.csv not found: {submission}",
    )
    if not submission_exists:
        return _finalize_report(submission, test_path, sample_path, checks)

    submission_columns, submission_rows = _read_csv(submission)
    sample_columns: list[str] = []
    test_rows: list[dict[str, str]] = []

    if sample_path is None:
        _check(checks, "sample_submission_file_exists", False, "sample_submission_csv_path is missing in config.verifier")
    else:
        sample_exists = sample_path.exists()
        _check(
            checks,
            "sample_submission_file_exists",
            sample_exists,
            f"sample_submission.csv exists: {sample_path}" if sample_exists else f"sample_submission.csv not found: {sample_path}",
        )
        if sample_exists:
            sample_columns, _ = _read_csv(sample_path)

    if test_path is None:
        _check(checks, "test_file_exists", False, "test_csv_path is missing in config.verifier")
    else:
        test_exists = test_path.exists()
        _check(
            checks,
            "test_file_exists",
            test_exists,
            f"test.csv exists: {test_path}" if test_exists else f"test.csv not found: {test_path}",
        )
        if test_exists:
            _, test_rows = _read_csv(test_path)

    missing_columns = [col for col in required_columns if col not in submission_columns]
    _check(
        checks,
        "required_columns_present",
        not missing_columns,
        "All required columns are present." if not missing_columns else f"Missing required columns: {missing_columns}",
        details={"required_columns": required_columns, "submission_columns": submission_columns},
    )

    if sample_columns:
        order_matches = submission_columns[:len(sample_columns)] == sample_columns
        _check(
            checks,
            "column_order_matches_sample_submission",
            order_matches,
            "Submission column order matches sample_submission.csv."
            if order_matches
            else "Submission column order does not match sample_submission.csv.",
            details={"sample_submission_columns": sample_columns, "submission_columns": submission_columns},
        )

    extra_columns = [col for col in submission_columns if col not in required_columns]
    _check(
        checks,
        "no_extra_columns",
        not extra_columns,
        "No extra columns found." if not extra_columns else f"Extra columns found: {extra_columns}",
        severity="warning",
        details={"extra_columns": extra_columns},
    )

    if test_rows:
        row_count_matches = len(submission_rows) == len(test_rows)
        _check(
            checks,
            "row_count_matches_test",
            row_count_matches,
            f"Submission row_count matches test.csv: {len(submission_rows)}"
            if row_count_matches
            else f"Submission row_count {len(submission_rows)} does not match test.csv row_count {len(test_rows)}.",
            details={"submission_row_count": len(submission_rows), "test_row_count": len(test_rows)},
        )

    if id_column:
        empty_id_rows = [idx for idx, row in enumerate(submission_rows) if not str(row.get(id_column, "")).strip()]
        _check(
            checks,
            "id_column_not_empty",
            not empty_id_rows,
            f"{id_column} has no empty values." if not empty_id_rows else f"{id_column} has empty values at rows: {empty_id_rows}",
            details={"id_column": id_column, "row_indexes": empty_id_rows},
        )

        ids = [str(row.get(id_column, "")).strip() for row in submission_rows]
        duplicate_ids = sorted({item for item in ids if item and ids.count(item) > 1})
        _check(
            checks,
            "id_column_unique",
            not duplicate_ids,
            f"{id_column} has no duplicate values." if not duplicate_ids else f"Duplicate {id_column} values found: {duplicate_ids}",
            details={"id_column": id_column, "duplicate_ids": duplicate_ids},
        )

        if test_rows and all(id_column in row for row in test_rows):
            test_ids = [str(row.get(id_column, "")).strip() for row in test_rows]
            missing_from_submission = sorted(set(test_ids) - set(ids))
            extra_in_submission = sorted(set(ids) - set(test_ids))
            id_sets_match = not missing_from_submission and not extra_in_submission
            _check(
                checks,
                "id_values_match_test",
                id_sets_match,
                f"Submission {id_column} values match test.csv."
                if id_sets_match
                else f"Submission {id_column} values do not match test.csv.",
                details={
                    "id_column": id_column,
                    "missing_from_submission": missing_from_submission,
                    "extra_in_submission": extra_in_submission,
                },
            )

    if target_column:
        empty_target_rows = [idx for idx, row in enumerate(submission_rows) if not str(row.get(target_column, "")).strip()]
        _check(
            checks,
            "target_column_not_empty",
            not empty_target_rows,
            f"{target_column} has no empty values."
            if not empty_target_rows
            else f"{target_column} has empty values at rows: {empty_target_rows}",
            details={"target_column": target_column, "row_indexes": empty_target_rows},
        )

        allowed_labels = value_constraints.get("allowed_labels") or []
        if allowed_labels:
            allowed = {str(label) for label in allowed_labels}
            invalid_values = sorted({
                str(row.get(target_column, "")).strip()
                for row in submission_rows
                if str(row.get(target_column, "")).strip() not in allowed
            })
            _check(
                checks,
                "target_values_in_allowed_labels",
                not invalid_values,
                f"{target_column} values are within allowed_labels."
                if not invalid_values
                else f"{target_column} has values outside allowed_labels: {invalid_values}",
                details={"target_column": target_column, "allowed_labels": sorted(allowed), "invalid_values": invalid_values},
            )

    return _finalize_report(submission, test_path, sample_path, checks)


def _finalize_report(
    submission_path: Path,
    test_path: Path | None,
    sample_path: Path | None,
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    errors = [check for check in checks if not check["passed"] and check["severity"] == "error"]
    warnings = [check for check in checks if not check["passed"] and check["severity"] == "warning"]
    return {
        "passed": not errors,
        "error_count": len(errors),
        "warning_count": len(warnings),
        "submission_path": str(submission_path),
        "test_csv_path": str(test_path) if test_path is not None else None,
        "sample_submission_csv_path": str(sample_path) if sample_path is not None else None,
        "checks": checks,
    }


def write_validation_report(report: dict[str, Any], json_path: str | Path, md_path: str | Path | None = None) -> None:
    json_out = Path(json_path)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    if md_path is not None:
        Path(md_path).write_text(render_validation_report_markdown(report), encoding="utf-8")


def render_validation_report_markdown(report: dict[str, Any]) -> str:
    status = "PASSED" if report.get("passed") else "FAILED"
    lines = [
        "# Submission Validation Report",
        "",
        f"- status: {status}",
        f"- errors: {report.get('error_count', 0)}",
        f"- warnings: {report.get('warning_count', 0)}",
        "",
        "## Checks",
        "",
    ]
    for check in report.get("checks", []):
        mark = "PASS" if check.get("passed") else ("WARN" if check.get("severity") == "warning" else "FAIL")
        lines.append(f"- {mark} `{check.get('name')}`: {check.get('message')}")
    lines.append("")
    return "\n".join(lines)
