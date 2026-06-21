# Architecture

## 전체 구조

```text
Contest Folder
  description.md
  rules.md
  evaluation.md
  contest_overrides.yaml (optional)
  train.csv
  test.csv
  sample_submission.csv
        ↓
factory/run_factory.py
        ↓
Spec Builder
  + contest_overrides.yaml 반영
        ↓
generated/contest_spec.yaml
        ↓
Gap Analyzer
        ↓
generated/gap_report.md
        ↓
Blueprint Generator
        ↓
generated/harness_blueprint.yaml
generated/harness_blueprint.md
        ↓
Harness Generator
        ↓
generated/final_harness/
        ↓
Final Harness Run
        ↓
outputs/submission.csv
outputs/validation_report.json
outputs/validation_report.md
```

## 모듈 설명

### 1. `factory/contest_reader.py`

대회 폴더 안의 파일 목록과 텍스트 문서, CSV 메타데이터를 읽는다. 선택 파일인 `contest_overrides.yaml`이 있으면
지원되는 작은 YAML subset으로 읽는다.

### 2. `factory/spec_builder.py`

읽은 정보를 `contest_spec` 딕셔너리로 정리한다. 현재 MVP에서는 규칙 기반으로 문제 유형을 추정한다.
`contest_overrides.yaml`에 기록된 사람이 확인한 규칙, 평가 지표, 출력 제약, solver 정책은 `unknowns` 계산 전에 반영한다.

### 3. `factory/gap_analyzer.py`

공장이 필요로 하는 필수 정보와 현재 spec을 비교해 확인 완료/빈칸/위험/사람 확인 필요 항목을 생성한다.
override로 해결된 항목은 불명확 항목 대신 적용 완료 항목으로 표시한다.

### 4. `factory/blueprint_generator.py`

`ContestSpec`과 `GapReport`를 기준으로 실제 하네스 생성 전에 사용할 설계도인 `HarnessBlueprint`를 만든다.
task type, 입력/출력 컬럼 요약, 추천 템플릿, loader/solver/verifier/submitter 요구사항, 사람 확인 필요 항목과 위험을 정리한다.
override 적용 항목도 남겨 final harness 생성 전 결정 근거를 확인할 수 있게 한다.

### 5. `factory/harness_generator.py`

`harness_blueprint`를 선택적으로 참고해 final harness 설정에 추천 템플릿, verifier 요구사항, 사람 확인 필요 항목, 위험 정보를 남긴다.
`templates/base_harness`를 `generated/final_harness`로 복사하고, `configs/default.json`을 현재 spec에 맞춰 작성한다.
verifier가 제출 파일을 검증할 수 있도록 `test.csv`, `sample_submission.csv`, required columns, id/target column, value constraints를
final harness 설정에 포함한다.

### 6. `templates/base_harness`

실제 대회용 하네스의 최소 구조다.

```text
run.py
src/loader.py
src/solver.py
src/verifier.py
src/submitter.py
src/logger.py
configs/default.json
```

`src/verifier.py`는 solver가 만든 `submission.csv`를 파일 단위로 다시 읽어 `sample_submission.csv`의 컬럼 순서,
`test.csv`의 row count/id 목록, 필수 컬럼, 빈 id/target, 중복 id, `allowed_labels` 제약을 검사한다.
검증 결과는 `outputs/validation_report.json`과 사람이 읽기 쉬운 `outputs/validation_report.md`로 저장된다.

### 7. `factory/ai_problem_analyzer.py`

입력 스캔 결과, 현재 `ContestSpec`, `GapReport`, `HarnessBlueprint` 요약을 바탕으로 사람이 외부 AI 도구에
붙여넣을 프롬프트를 생성한다. 이 단계는 offline-only이며 LLM API를 호출하지 않는다.

### 8. `factory/ai_analysis_intake.py`

사람이 저장한 AI 응답 Markdown에서 `## Machine-readable Analysis Payload` heading 뒤의 첫 `json` fenced code block만
표준 라이브러리 `json`으로 파싱한다. 필수 필드와 override 후보를 검증하고, 지원되지 않는 path, 낮은 confidence,
`unknown` 값, 중복 path, 기존 `contest_overrides.yaml`과 충돌하는 값은 실제 proposed override에서 제외한다.
실제 `contest_overrides.yaml`, `ContestSpec`, `HarnessBlueprint`는 수정하지 않는다.

### 9. `factory/run_ai_analysis_review.py`

AI 응답 intake를 독립 실행하는 CLI다. `factory/run_factory.py` 흐름에 결합하지 않고 다음 검토 산출물만 생성한다.

```text
generated/ai_analysis_candidates.json
generated/ai_analysis_review.md
generated/contest_overrides.proposed.yaml
generated/code_agent_task_plan.md
```

### 10. `factory/experiment_manager.py`

factory 실행 이력을 `runs/run_001` 형태로 저장한다.

## 설계 원칙

- 먼저 작동하는 end-to-end를 만든다.
- solver 성능보다 구조/재현성/규칙 안전을 우선한다.
- GitHub 자동화는 P0에서 제외한다.
- 외부 LLM/API는 optional adapter로만 둔다.
