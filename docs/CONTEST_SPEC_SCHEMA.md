# Contest Spec Schema

`contest_spec.yaml`은 대회 공개 정보를 공장이 이해할 수 있는 고정 양식으로 변환한 파일이다.

## 기본 구조

```yaml
contest:
  name: string
  source_path: string
  phase: unknown | round1 | round2 | final

problem:
  task_type: unknown | multiple_choice | classification | text_qa | multimodal | retrieval_qa
  input_modalities:
    - text
    - table
    - image
  output_type: unknown | choice | label | text | number
  evaluation_metric: unknown | accuracy | f1 | logloss | custom

files:
  train:
    path: string
    exists: true | false
    columns: [string]
    row_count: number
  test:
    path: string
    exists: true | false
    columns: [string]
    row_count: number
  sample_submission:
    path: string
    exists: true | false
    columns: [string]
    row_count: number

rules:
  allowed_language: Python | unknown
  external_api_allowed: true | false | unknown
  external_data_allowed: true | false | unknown
  pretrained_model_allowed: true | false | unknown
  internet_allowed: true | false | unknown
  manual_labeling_allowed: true | false | unknown
  leakage_policy: unknown | strict

output:
  required_file: submission.csv
  required_columns: [string]
  id_column: string | unknown
  target_column: string | unknown
  value_constraints: unknown | description

unknowns:
  - item: string
    why_it_matters: string
    action_required: string

human_decisions:
  - decision: string
    status: pending | decided
    options: [string]
    selected: string | null
    reason: string | null
```

## 원칙

- 모르면 추정하지 말고 `unknown`으로 남긴다.
- 규칙상 위험한 것은 자동으로 진행하지 않는다.
- `sample_submission.csv`가 있으면 출력 스키마는 이를 우선한다.
- `test.csv` 정답 패턴 추정, 수작업 라벨링, leaderboard 기반 과최적화는 별도 위험으로 기록한다.
