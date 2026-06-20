from __future__ import annotations

from typing import Any
from pathlib import Path
from factory.contest_reader import read_contest_folder
from factory.utils import write_text, write_json, to_simple_yaml


def infer_scalar_type(value: Any) -> str:
    if value in {None, ""}:
        return "empty"
    text = str(value)
    try:
        int(text)
    except ValueError:
        pass
    else:
        return "integer"
    try:
        float(text)
    except ValueError:
        return "string"
    return "number"


def build_column_details(meta: dict[str, Any]) -> list[dict[str, Any]]:
    first_row = meta.get("first_row") or {}
    details: list[dict[str, Any]] = []
    for index, name in enumerate(meta.get("columns", [])):
        first_value = first_row.get(name, "")
        details.append({
            "name": name,
            "index": index,
            "first_value": first_value,
            "inferred_type_from_first_row": infer_scalar_type(first_value),
        })
    return details


def enrich_file_metadata(files: dict[str, Any]) -> dict[str, Any]:
    enriched: dict[str, Any] = {}
    for key, meta in files.items():
        next_meta = dict(meta)
        next_meta["column_count"] = len(next_meta.get("columns", []))
        next_meta["column_details"] = build_column_details(next_meta)
        enriched[key] = next_meta
    return enriched


def build_schema_summary(files: dict[str, Any]) -> dict[str, Any]:
    train_cols = files.get("train", {}).get("columns", [])
    test_cols = files.get("test", {}).get("columns", [])
    sample_cols = files.get("sample_submission", {}).get("columns", [])

    train_set = set(train_cols)
    test_set = set(test_cols)
    sample_set = set(sample_cols)

    return {
        "common_columns": [c for c in train_cols if c in test_set],
        "common_all_files_columns": [c for c in train_cols if c in test_set and c in sample_set],
        "train_only_columns": [c for c in train_cols if c not in test_set],
        "test_only_columns": [c for c in test_cols if c not in train_set],
        "sample_submission_only_columns": [c for c in sample_cols if c not in train_set and c not in test_set],
        "train_missing_from_test": [c for c in train_cols if c not in test_set],
        "test_missing_from_train": [c for c in test_cols if c not in train_set],
    }


def infer_task_type(files: dict[str, Any]) -> tuple[str, list[str], str, list[str]]:
    train_cols = [c.lower() for c in files.get("train", {}).get("columns", [])]
    test_cols = [c.lower() for c in files.get("test", {}).get("columns", [])]
    sample_cols = [c.lower() for c in files.get("sample_submission", {}).get("columns", [])]
    all_cols = train_cols + test_cols + sample_cols
    evidence: list[str] = []

    has_choices = any(c.startswith("choice") or c in {"option1", "option2", "a", "b", "c", "d"} for c in all_cols)
    has_question = any(c in {"question", "query", "prompt", "request"} for c in all_cols)
    has_image = any(c in {"image", "image_path", "img_path", "file", "filename"} for c in all_cols)

    if has_choices:
        evidence.append("choice-like columns were found in train/test/sample schema.")
        if has_question:
            evidence.append("question-like text column was found.")
        if has_image:
            evidence.append("image-like column was found.")
        return "multiple_choice", ["text"] + (["image"] if has_image else []), "choice", evidence
    if has_question:
        evidence.append("question-like text column was found without choice columns.")
        if has_image:
            evidence.append("image-like column was found.")
        return "text_qa", ["text"] + (["image"] if has_image else []), "text", evidence
    if files.get("sample_submission", {}).get("exists"):
        evidence.append("sample_submission.csv exists and no more specific task pattern was detected.")
        return "classification", ["table"], "label", evidence
    evidence.append("No sample_submission.csv or recognizable task columns were found.")
    return "unknown", [], "unknown", evidence


def infer_id_target_columns(sample_columns: list[str]) -> tuple[str, str, list[str]]:
    evidence: list[str] = []
    if not sample_columns:
        return "unknown", "unknown", ["sample_submission.csv has no columns."]
    id_candidates = [c for c in sample_columns if c.lower() in {"id", "index", "sample_id", "uid"}]
    if id_candidates:
        id_col = id_candidates[0]
        evidence.append(f"id_column inferred from known identifier column name: {id_col}.")
    else:
        id_col = sample_columns[0]
        evidence.append(f"id_column fell back to first sample_submission column: {id_col}.")
    target_candidates = [c for c in sample_columns if c != id_col]
    if len(target_candidates) == 1:
        target_col = target_candidates[0]
        evidence.append(f"target_column inferred as the only non-id sample_submission column: {target_col}.")
    elif target_candidates:
        target_col = target_candidates[0]
        evidence.append(f"target_column fell back to the first non-id sample_submission column: {target_col}.")
    else:
        target_col = "unknown"
        evidence.append("target_column could not be inferred because sample_submission only has an id column.")
    return id_col, target_col, evidence


def infer_default_output_value(sample_submission: dict[str, Any], target_col: str) -> tuple[str, str]:
    first_row = sample_submission.get("first_row") or {}
    value = first_row.get(target_col)
    if value not in {None, ""}:
        return str(value), f"default_value copied from first sample_submission row for {target_col}."
    return "1", "default_value fell back to '1' because sample_submission target value was empty or unavailable."


def build_contest_spec(contest_path: str | Path) -> dict[str, Any]:
    raw = read_contest_folder(contest_path)
    files = enrich_file_metadata(raw["files"])
    schema = build_schema_summary(files)
    task_type, modalities, output_type, task_type_evidence = infer_task_type(files)
    sample_columns = files["sample_submission"]["columns"]
    id_col, target_col, output_evidence = infer_id_target_columns(sample_columns)
    default_output_value, default_value_evidence = infer_default_output_value(files["sample_submission"], target_col)

    rules_text = (raw.get("rules") or "").lower()
    allowed_language = "Python" if "python" in rules_text or not rules_text else "unknown"

    spec: dict[str, Any] = {
        "contest": {
            "name": "SCPC AI Challenge Draft Contest",
            "source_path": str(contest_path),
            "phase": "unknown",
        },
        "problem": {
            "task_type": task_type,
            "task_type_evidence": task_type_evidence,
            "input_modalities": modalities,
            "output_type": output_type,
            "evaluation_metric": "unknown",
        },
        "files": files,
        "schema": schema,
        "rules": {
            "allowed_language": allowed_language,
            "external_api_allowed": "unknown",
            "external_data_allowed": "unknown",
            "pretrained_model_allowed": "unknown",
            "internet_allowed": "unknown",
            "manual_labeling_allowed": "unknown",
            "leakage_policy": "strict",
        },
        "output": {
            "required_file": "submission.csv",
            "required_columns": sample_columns,
            "id_column": id_col,
            "target_column": target_col,
            "default_value": default_output_value,
            "inference": {
                "evidence": output_evidence + [default_value_evidence],
                "required_columns_source": "sample_submission.csv",
            },
            "value_constraints": "unknown",
        },
        "unknowns": [],
        "human_decisions": [],
        "source_documents": {
            "description_present": bool(raw.get("description")),
            "rules_present": bool(raw.get("rules")),
            "evaluation_present": bool(raw.get("evaluation")),
            "all_files": raw.get("all_files", []),
        },
    }
    spec["unknowns"] = build_unknowns(spec)
    spec["human_decisions"] = build_human_decisions(spec)
    return spec


def build_unknowns(spec: dict[str, Any]) -> list[dict[str, str]]:
    unknowns: list[dict[str, str]] = []
    checks = [
        ("problem.evaluation_metric", spec["problem"].get("evaluation_metric"), "평가 지표에 따라 solver와 validation 전략이 달라진다."),
        ("rules.external_api_allowed", spec["rules"].get("external_api_allowed"), "외부 LLM API solver를 사용할 수 있는지 결정해야 한다."),
        ("rules.external_data_allowed", spec["rules"].get("external_data_allowed"), "외부 데이터/RAG 사용 가능 여부를 결정해야 한다."),
        ("rules.pretrained_model_allowed", spec["rules"].get("pretrained_model_allowed"), "사용 가능한 모델 범위를 결정해야 한다."),
        ("rules.internet_allowed", spec["rules"].get("internet_allowed"), "런타임 검색/크롤링 가능 여부를 결정해야 한다."),
        ("output.value_constraints", spec["output"].get("value_constraints"), "제출 값 범위 검증이 필요하다."),
    ]
    for item, value, why in checks:
        if value in {"unknown", None, ""}:
            unknowns.append({
                "item": item,
                "why_it_matters": why,
                "action_required": "대회 공식 규칙/평가 탭 공개 후 확인하고 human decision log에 기록한다.",
            })
    return unknowns


def build_human_decisions(spec: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "decision": "외부 LLM API를 final solver에 포함할지 여부",
            "status": "pending",
            "options": ["사용", "미사용", "optional adapter만 유지"],
            "selected": None,
            "reason": None,
        },
        {
            "decision": "최종 제출 solver 선택",
            "status": "pending",
            "options": ["baseline", "improved", "ensemble"],
            "selected": None,
            "reason": None,
        },
    ]


def save_contest_spec(spec: dict[str, Any], output_dir: str | Path) -> tuple[Path, Path]:
    out = Path(output_dir)
    yaml_path = write_text(out / "contest_spec.yaml", to_simple_yaml(spec) + "\n")
    json_path = write_json(out / "contest_spec.json", spec)
    return yaml_path, json_path
