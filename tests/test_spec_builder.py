from factory.spec_builder import build_contest_spec


def test_build_contest_spec_mock_contest():
    spec = build_contest_spec("examples/mock_contest_01")
    assert spec["problem"]["task_type"] == "multiple_choice"
    assert spec["output"]["required_columns"] == ["id", "answer"]
    assert spec["files"]["test"]["row_count"] == 2


def test_build_contest_spec_mock_contest_text_classification():
    spec = build_contest_spec("examples/mock_contest_02")
    assert spec["problem"]["task_type"] == "classification"
    assert spec["problem"]["input_modalities"] == ["table"]
    assert spec["output"]["required_columns"] == ["id", "label"]
    assert spec["output"]["id_column"] == "id"
    assert spec["output"]["target_column"] == "label"
    assert spec["output"]["default_value"] == "positive"
    assert spec["files"]["test"]["row_count"] == 3
