# Rule Guard Skill

## Purpose

대회 규칙 위반 가능성을 차단한다.

## Inputs

- rules.md
- generated/contest_spec.yaml
- docs/RULE_CHECKLIST.md

## Outputs

- warning list
- human decision items

## Procedure

1. 외부 API 사용 가능 여부를 확인한다.
2. 외부 데이터 사용 가능 여부를 확인한다.
3. pretrained model 제한을 확인한다.
4. test/eval 수작업 라벨링, 정답 분포 추정, leaderboard 과최적화 위험을 기록한다.
5. 불명확하면 final config에서 비활성화한다.
