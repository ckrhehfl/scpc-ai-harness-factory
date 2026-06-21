from factory.spec_builder import build_contest_spec
from factory.utils import to_simple_yaml


def test_build_contest_spec_mock_contest():
    spec = build_contest_spec("examples/mock_contest_01")
    assert spec["problem"]["task_type"] == "multiple_choice"
    assert spec["problem"]["task_type_evidence"]
    assert spec["output"]["required_columns"] == ["id", "answer"]
    assert spec["output"]["id_column"] == "id"
    assert spec["output"]["target_column"] == "answer"
    assert spec["output"]["inference"]["required_columns_source"] == "sample_submission.csv"
    assert spec["schema"]["common_columns"] == ["id", "question", "choice1", "choice2", "choice3", "choice4"]
    assert spec["schema"]["train_only_columns"] == ["answer"]
    assert spec["schema"]["test_only_columns"] == []
    assert spec["schema"]["sample_submission_only_columns"] == []
    assert spec["files"]["train"]["column_count"] == 7
    assert spec["files"]["train"]["column_details"][0]["name"] == "id"
    assert spec["files"]["train"]["column_details"][0]["inferred_type_from_first_row"] == "integer"
    assert spec["files"]["test"]["row_count"] == 2


def test_build_contest_spec_mock_contest_text_classification():
    spec = build_contest_spec("examples/mock_contest_02")
    assert spec["problem"]["task_type"] == "classification"
    assert spec["problem"]["evaluation_metric"] == "accuracy"
    assert spec["problem"]["input_modalities"] == ["table"]
    assert spec["rules"]["external_api_allowed"] is False
    assert spec["rules"]["internet_allowed"] is False
    assert spec["output"]["required_columns"] == ["id", "label"]
    assert spec["output"]["id_column"] == "id"
    assert spec["output"]["target_column"] == "label"
    assert spec["output"]["default_value"] == "positive"
    assert spec["output"]["value_constraints"] == {"allowed_labels": ["positive", "negative"]}
    assert spec["human_decision_values"]["final_solver_policy"] == "local_baseline_only"
    assert spec["human_decision_values"]["use_external_llm_api"] is False
    assert any(item["item"] == "problem.evaluation_metric" for item in spec["decision_overrides"]["applied"])
    assert spec["schema"]["common_columns"] == ["id", "text"]
    assert spec["schema"]["train_only_columns"] == ["label"]
    assert spec["schema"]["sample_submission_only_columns"] == []
    assert any("default_value copied" in item for item in spec["output"]["inference"]["evidence"])
    assert spec["files"]["test"]["row_count"] == 3


def test_contest_overrides_resolve_unknowns_for_supported_fields():
    spec = build_contest_spec("examples/mock_contest_02")
    unknown_items = {item["item"] for item in spec["unknowns"]}

    assert "problem.evaluation_metric" not in unknown_items
    assert "rules.external_api_allowed" not in unknown_items
    assert "rules.external_data_allowed" not in unknown_items
    assert "rules.internet_allowed" not in unknown_items
    assert "output.value_constraints" not in unknown_items
    assert "rules.pretrained_model_allowed" in unknown_items


def test_allowed_language_is_unknown_without_python_in_rules(tmp_path):
    contest = tmp_path / "contest"
    contest.mkdir()
    (contest / "rules.md").write_text("", encoding="utf-8")
    (contest / "train.csv").write_text("id,label\n1,A\n", encoding="utf-8")
    (contest / "test.csv").write_text("id\n2\n", encoding="utf-8")
    (contest / "sample_submission.csv").write_text("id,label\n2,A\n", encoding="utf-8")

    spec = build_contest_spec(contest)
    assert spec["rules"]["allowed_language"] == "unknown"
    assert any(item["item"] == "rules.allowed_language" for item in spec["unknowns"])


def test_allowed_language_is_python_only_when_rules_mention_python(tmp_path):
    contest = tmp_path / "contest"
    contest.mkdir()
    (contest / "rules.md").write_text("Submissions must use Python.", encoding="utf-8")
    (contest / "train.csv").write_text("id,label\n1,A\n", encoding="utf-8")
    (contest / "test.csv").write_text("id\n2\n", encoding="utf-8")
    (contest / "sample_submission.csv").write_text("id,label\n2,A\n", encoding="utf-8")

    assert build_contest_spec(contest)["rules"]["allowed_language"] == "Python"


def test_new_rule_overrides_apply_only_from_contest_overrides(tmp_path):
    contest = tmp_path / "contest"
    contest.mkdir()
    (contest / "rules.md").write_text("No language listed.", encoding="utf-8")
    (contest / "train.csv").write_text("id,label\n1,A\n", encoding="utf-8")
    (contest / "test.csv").write_text("id\n2\n", encoding="utf-8")
    (contest / "sample_submission.csv").write_text("id,label\n2,A\n", encoding="utf-8")

    spec_without_override = build_contest_spec(contest)
    assert spec_without_override["rules"]["allowed_language"] == "unknown"
    assert spec_without_override["rules"]["manual_labeling_allowed"] == "unknown"

    (contest / "contest_overrides.yaml").write_text(
        "rules:\n  allowed_language: Python\n  manual_labeling_allowed: false\n",
        encoding="utf-8",
    )
    spec = build_contest_spec(contest)
    assert spec["rules"]["allowed_language"] == "Python"
    assert spec["rules"]["manual_labeling_allowed"] is False
    applied = {item["item"] for item in spec["decision_overrides"]["applied"]}
    assert "rules.allowed_language" in applied
    assert "rules.manual_labeling_allowed" in applied


def test_simple_yaml_renders_empty_lists_explicitly():
    text = to_simple_yaml({"schema": {"test_only_columns": []}})
    assert "test_only_columns: []" in text
