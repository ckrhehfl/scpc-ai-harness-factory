# Contest Spec Builder Skill

## Purpose

대회 공개 정보를 `contest_spec.yaml`로 변환한다.

## Inputs

- description.md
- rules.md
- evaluation.md
- train.csv
- test.csv
- sample_submission.csv

## Outputs

- generated/contest_spec.yaml
- generated/contest_spec.json

## Procedure

1. 대회 폴더 파일 목록을 확인한다.
2. train/test/sample_submission CSV의 컬럼과 행 수를 확인한다.
3. sample_submission을 기준으로 출력 스키마를 정한다.
4. 문제 유형을 추정하되, 확신이 없으면 unknown으로 둔다.
5. 외부 API/외부 데이터/인터넷/사전학습 모델 사용 여부는 규칙이 명확할 때만 확정한다.
