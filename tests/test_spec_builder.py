from factory.spec_builder import build_contest_spec


def test_build_contest_spec_mock_contest():
    spec = build_contest_spec("examples/mock_contest_01")
    assert spec["problem"]["task_type"] == "multiple_choice"
    assert spec["output"]["required_columns"] == ["id", "answer"]
    assert spec["files"]["test"]["row_count"] == 2
