# Architecture

## 전체 구조

```text
Contest Folder
  description.md
  rules.md
  evaluation.md
  train.csv
  test.csv
  sample_submission.csv
        ↓
factory/run_factory.py
        ↓
Spec Builder
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
```

## 모듈 설명

### 1. `factory/contest_reader.py`

대회 폴더 안의 파일 목록과 텍스트 문서, CSV 메타데이터를 읽는다.

### 2. `factory/spec_builder.py`

읽은 정보를 `contest_spec` 딕셔너리로 정리한다. 현재 MVP에서는 규칙 기반으로 문제 유형을 추정한다.

### 3. `factory/gap_analyzer.py`

공장이 필요로 하는 필수 정보와 현재 spec을 비교해 확인 완료/빈칸/위험/사람 확인 필요 항목을 생성한다.

### 4. `factory/blueprint_generator.py`

`ContestSpec`과 `GapReport`를 기준으로 실제 하네스 생성 전에 사용할 설계도인 `HarnessBlueprint`를 만든다.
task type, 입력/출력 컬럼 요약, 추천 템플릿, loader/solver/verifier/submitter 요구사항, 사람 확인 필요 항목과 위험을 정리한다.

### 5. `factory/harness_generator.py`

`harness_blueprint`를 선택적으로 참고해 final harness 설정에 추천 템플릿, verifier 요구사항, 사람 확인 필요 항목, 위험 정보를 남긴다.
`templates/base_harness`를 `generated/final_harness`로 복사하고, `configs/default.json`을 현재 spec에 맞춰 작성한다.

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

### 7. `factory/experiment_manager.py`

factory 실행 이력을 `runs/run_001` 형태로 저장한다.

## 설계 원칙

- 먼저 작동하는 end-to-end를 만든다.
- solver 성능보다 구조/재현성/규칙 안전을 우선한다.
- GitHub 자동화는 P0에서 제외한다.
- 외부 LLM/API는 optional adapter로만 둔다.
