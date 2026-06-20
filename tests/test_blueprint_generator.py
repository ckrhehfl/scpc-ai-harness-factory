from factory.blueprint_generator import (
    build_harness_blueprint,
    render_harness_blueprint_markdown,
    save_harness_blueprint,
)
from factory.gap_analyzer import analyze_gaps
from factory.spec_builder import build_contest_spec


def test_build_harness_blueprint_from_multiple_choice_spec(tmp_path):
    spec = build_contest_spec("examples/mock_contest_01")
    gap_report = analyze_gaps(spec)

    blueprint = build_harness_blueprint(spec, gap_report, templates_dir=tmp_path)

    assert blueprint["contest_name"] == "SCPC AI Challenge Draft Contest"
    assert blueprint["task_type"] == "multiple_choice"
    assert blueprint["task_type_evidence"]
    assert blueprint["output_required_columns"] == ["id", "answer"]
    assert blueprint["id_column"] == "id"
    assert blueprint["target_column"] == "answer"
    assert blueprint["recommended_template"] == "base_harness"
    assert blueprint["verifier_requirements"]
    assert blueprint["human_decisions_required"]
    assert blueprint["known_risks"]
    assert blueprint["input_columns_summary"]["train"]["column_count"] == 7


def test_save_harness_blueprint_writes_yaml_and_markdown(tmp_path):
    spec = build_contest_spec("examples/mock_contest_02")
    gap_report = analyze_gaps(spec)
    blueprint = build_harness_blueprint(spec, gap_report, templates_dir=tmp_path)

    yaml_path, md_path = save_harness_blueprint(blueprint, tmp_path)

    yaml_text = yaml_path.read_text(encoding="utf-8")
    md_text = md_path.read_text(encoding="utf-8")

    assert "task_type: classification" in yaml_text
    assert "recommended_template: base_harness" in yaml_text
    assert "verifier_requirements:" in yaml_text
    assert "human_decisions_required:" in yaml_text
    assert "override_applied:" in yaml_text
    assert "# Harness Blueprint" in md_text
    assert "## Verifier Requirements" in md_text
    assert "## Override Applied" in md_text


def test_render_harness_blueprint_markdown_includes_required_sections(tmp_path):
    spec = build_contest_spec("examples/mock_contest_02")
    blueprint = build_harness_blueprint(spec, analyze_gaps(spec), templates_dir=tmp_path)

    text = render_harness_blueprint_markdown(blueprint)

    assert "task_type: classification" in text
    assert "recommended_template: base_harness" in text
    assert "## Human Decisions Required" in text


def test_blueprint_tracks_overrides_and_reduces_human_decisions(tmp_path):
    spec = build_contest_spec("examples/mock_contest_02")
    blueprint = build_harness_blueprint(spec, analyze_gaps(spec), templates_dir=tmp_path)

    assert any("problem.evaluation_metric" in item for item in blueprint["override_applied"])
    assert any("Final solver policy: local_baseline_only." in item for item in blueprint["solver_requirements"])
    assert not any("외부 LLM API" in item for item in blueprint["human_decisions_required"])
    assert not any("최종 제출 solver 선택" in item for item in blueprint["human_decisions_required"])
    assert any("pretrained_model_allowed" in item for item in blueprint["human_decisions_required"])
