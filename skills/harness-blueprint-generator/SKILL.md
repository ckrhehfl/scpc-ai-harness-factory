# Harness Blueprint Generator Skill

## Purpose

ContestSpec을 기반으로 대회용 하네스 구조를 설계한다.

## Inputs

- generated/contest_spec.yaml
- generated/gap_report.md

## Outputs

- generated/final_harness/
- generated/solution_log.md 초안

## Procedure

1. 문제 유형 후보를 확인한다.
2. base_harness로 시작한다.
3. solver는 처음에 baseline으로 둔다.
4. loader, verifier, submitter가 먼저 작동하게 한다.
5. 성능 개선은 submission 생성 후 진행한다.
