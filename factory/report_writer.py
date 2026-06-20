from __future__ import annotations

from pathlib import Path
from typing import Any
from factory.utils import write_text


def write_solution_log_stub(spec: dict[str, Any], output_dir: str | Path = "generated") -> Path:
    text = f"""# Solution Log

## 1. 문제 유형 후보

- `{spec['problem']['task_type']}`

## 2. 입력 모달리티

- {', '.join(spec['problem'].get('input_modalities', [])) or 'unknown'}

## 3. 제출 형식

- required columns: {spec['output'].get('required_columns')}
- id column: {spec['output'].get('id_column')}
- target column: {spec['output'].get('target_column')}

## 4. 현재 solver

- baseline constant solver

## 5. 다음 작업

1. gap_report.md 확인
2. rules unknown 항목 확인
3. 실제 문제 유형에 맞는 solver 추가
4. verifier 강화
5. 실험 로그 기록
"""
    return write_text(Path(output_dir) / "solution_log.md", text)
