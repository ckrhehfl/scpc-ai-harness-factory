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
    assert spec["problem"]["input_modalities"] == ["table"]
    assert spec["output"]["required_columns"] == ["id", "label"]
    assert spec["output"]["id_column"] == "id"
    assert spec["output"]["target_column"] == "label"
    assert spec["output"]["default_value"] == "positive"
    assert spec["schema"]["common_columns"] == ["id", "text"]
    assert spec["schema"]["train_only_columns"] == ["label"]
    assert spec["schema"]["sample_submission_only_columns"] == []
    assert any("default_value copied" in item for item in spec["output"]["inference"]["evidence"])
    assert spec["files"]["test"]["row_count"] == 3


def test_simple_yaml_renders_empty_lists_explicitly():
    text = to_simple_yaml({"schema": {"test_only_columns": []}})
    assert "test_only_columns: []" in text
