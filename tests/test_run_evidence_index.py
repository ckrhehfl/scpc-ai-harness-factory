from __future__ import annotations

from pathlib import Path
import json

from factory.run_evidence_index import main


def write_scan(path: Path, files: list[dict]) -> None:
    path.write_text(
        json.dumps({"contest_path": "contest", "files": files}, ensure_ascii=False),
        encoding="utf-8",
    )


def valid_file_item() -> dict:
    return {
        "path": "train.csv",
        "absolute_path": "/local/train.csv",
        "name": "train.csv",
        "extension": ".csv",
        "size_bytes": 42,
        "file_kind": "csv",
        "role_candidates": ["train_data"],
        "csv_preview": {
            "columns": ["id", "label"],
            "column_count": 2,
            "row_count": 1,
            "first_row_preview": {"id": "1", "label": "A"},
            "preview_rows": [{"id": "1", "label": "A"}],
        },
    }


def run_cli(monkeypatch, input_scan: Path, output_dir: Path) -> int:
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_evidence_index.py",
            "--input-scan",
            str(input_scan),
            "--output",
            str(output_dir),
        ],
    )
    return main()


def test_cli_generates_json_and_markdown_for_valid_input(tmp_path, monkeypatch, capsys):
    input_scan = tmp_path / "input_scan_report.json"
    output_dir = tmp_path / "generated"
    write_scan(input_scan, [valid_file_item()])
    original_input = input_scan.read_text(encoding="utf-8")

    code = run_cli(monkeypatch, input_scan, output_dir)
    captured = capsys.readouterr()

    assert code == 0
    assert "[OK] Evidence index generated" in captured.out
    assert (output_dir / "evidence_index.json").exists()
    assert (output_dir / "evidence_index.md").exists()
    assert input_scan.read_text(encoding="utf-8") == original_input

    data = json.loads((output_dir / "evidence_index.json").read_text(encoding="utf-8"))
    assert data["record_count"] == 2
    assert any(record["key"].endswith(":csv_structure") for record in data["records"])


def test_cli_returns_nonzero_for_malformed_json_without_outputs(tmp_path, monkeypatch, capsys):
    input_scan = tmp_path / "input_scan_report.json"
    output_dir = tmp_path / "generated"
    input_scan.write_text("{bad json", encoding="utf-8")

    code = run_cli(monkeypatch, input_scan, output_dir)
    captured = capsys.readouterr()

    assert code == 1
    assert "[ERROR]" in captured.err
    assert not (output_dir / "evidence_index.json").exists()
    assert not (output_dir / "evidence_index.md").exists()


def test_cli_returns_nonzero_for_non_object_json_without_outputs(tmp_path, monkeypatch):
    input_scan = tmp_path / "input_scan_report.json"
    output_dir = tmp_path / "generated"
    input_scan.write_text("[]", encoding="utf-8")

    assert run_cli(monkeypatch, input_scan, output_dir) == 1
    assert not (output_dir / "evidence_index.json").exists()
    assert not (output_dir / "evidence_index.md").exists()


def test_cli_returns_nonzero_when_files_is_not_list_without_outputs(tmp_path, monkeypatch):
    input_scan = tmp_path / "input_scan_report.json"
    output_dir = tmp_path / "generated"
    input_scan.write_text('{"contest_path": "contest", "files": {}}', encoding="utf-8")

    assert run_cli(monkeypatch, input_scan, output_dir) == 1
    assert not (output_dir / "evidence_index.json").exists()
    assert not (output_dir / "evidence_index.md").exists()


def test_cli_returns_nonzero_for_unsafe_file_path_without_outputs(tmp_path, monkeypatch):
    input_scan = tmp_path / "input_scan_report.json"
    output_dir = tmp_path / "generated"
    item = valid_file_item()
    item["path"] = "../train.csv"
    write_scan(input_scan, [item])

    assert run_cli(monkeypatch, input_scan, output_dir) == 1
    assert not (output_dir / "evidence_index.json").exists()
    assert not (output_dir / "evidence_index.md").exists()


def test_cli_does_not_modify_contest_source_or_overrides_on_failure(tmp_path, monkeypatch):
    contest = tmp_path / "contest"
    contest.mkdir()
    source = contest / "train.csv"
    overrides = contest / "contest_overrides.yaml"
    source.write_text("id,label\n1,A\n", encoding="utf-8")
    overrides.write_text("task_type: classification\n", encoding="utf-8")
    source_before = source.read_text(encoding="utf-8")
    overrides_before = overrides.read_text(encoding="utf-8")

    input_scan = tmp_path / "input_scan_report.json"
    output_dir = tmp_path / "generated"
    item = valid_file_item()
    item["path"] = "/absolute/train.csv"
    write_scan(input_scan, [item])

    assert run_cli(monkeypatch, input_scan, output_dir) == 1
    assert source.read_text(encoding="utf-8") == source_before
    assert overrides.read_text(encoding="utf-8") == overrides_before
    assert not (output_dir / "evidence_index.json").exists()
    assert not (output_dir / "evidence_index.md").exists()
