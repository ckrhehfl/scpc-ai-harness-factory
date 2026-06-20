# PROJECT PRD: SCPC AI Harness Factory

## 1. 목적

2026 SCPC AI Challenge 문제 공개 후 처음부터 코딩하지 않고, 공개된 문제 설명/규칙/평가/데이터/제출 형식을 빠르게 분석하여 대회용 AI Agent Harness 뼈대를 생성한다.

## 2. 핵심 가설

대회 문제의 구체 도메인은 공개 전까지 알 수 없지만, 대부분의 경진대회 대응 흐름은 다음 공통 구조를 가진다.

```text
입력 구조 파악
→ 제출 형식 파악
→ 규칙/위험 요소 확인
→ baseline harness 생성
→ 제출 파일 생성
→ 실험 로그 관리
```

따라서 문제 공개 전에 이 공통 구조를 공장화해두면 대응 속도를 높일 수 있다.

## 3. 사용자

- 대회 참가자 본인
- Claude Code / Codex 같은 코드에이전트
- 본선 발표자료를 준비할 Report Agent

## 4. MVP 목표

`examples/mock_contest_01`을 입력으로 넣었을 때 다음이 자동 생성되어야 한다.

1. `generated/contest_spec.yaml`
2. `generated/gap_report.md`
3. `generated/final_harness/`
4. `generated/final_harness/outputs/submission.csv`
5. `runs/run_001/run_log.json`

## 5. 자동화 대상

- 대회 폴더 파일 탐색
- CSV 컬럼/행 수 분석
- 문제 유형 후보 추정
- 제출 파일 스키마 추출
- 미확정 규칙/위험 요소 추출
- base harness scaffold 생성
- baseline submission 생성
- 실행 로그 저장

## 6. 자동화하지 않는 것

- GitHub PR 자동화
- 자동 머지
- 자동 리뷰픽스
- 외부 API 사용 여부 임의 결정
- 평가 데이터 기반 누수 튜닝
- 최종 제출 파일 자동 선택
- 본선 Q&A를 대신하는 설명

## 7. 성공 기준

```bat
python factory\run_factory.py --contest examples\mock_contest_01
python generated\final_harness\run.py
pytest
```

위 명령이 모두 성공하면 MVP 완료로 본다.

## 8. P0 범위

- 로컬 실행 기준
- mock contest 기준
- Python 표준 라이브러리 중심
- template copy 방식의 harness generator
- 간단한 verifier 포함

## 9. P1 후보

- 문제 유형별 템플릿 확장
- text QA / classification / multimodal template 추가
- 로컬 validation split
- prompt/solver experiment manager
- solution_log 자동 생성 강화

## 10. 위험 관리

가장 큰 위험은 성능 부족이 아니라 규칙 위반이다. 외부 API, 외부 데이터, pretrained model, 인터넷 접근, leaderboard 기반 과최적화, test/eval 수작업 라벨링은 반드시 `RULE_CHECKLIST.md`와 `HUMAN_DECISION_LOG.md`로 관리한다.
