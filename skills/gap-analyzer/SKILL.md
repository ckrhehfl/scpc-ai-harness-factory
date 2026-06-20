# Gap Analyzer Skill

## Purpose

공장이 필요한 필수 정보와 현재 contest spec을 비교해 빈칸과 위험 요소를 정리한다.

## Inputs

- generated/contest_spec.yaml
- docs/CONTEST_SPEC_SCHEMA.md
- docs/RULE_CHECKLIST.md

## Outputs

- generated/gap_report.md
- docs/HUMAN_DECISION_LOG.md 업데이트 제안

## Procedure

1. evaluation_metric, output_schema, allowed_tools를 우선 확인한다.
2. unknown 값은 임의로 채우지 않는다.
3. 외부 API/데이터/인터넷/pretrained model이 불명확하면 위험 요소로 남긴다.
4. 사람이 확인해야 하는 항목과 자동 진행 가능한 항목을 분리한다.
