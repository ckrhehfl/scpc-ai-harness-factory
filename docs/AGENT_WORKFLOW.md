# Agent Workflow

이 문서는 Codex/Claude Code에게 작업을 시킬 때 읽히는 절차서다.

## 핵심 역할

### PM Agent

- 현재 범위가 MVP를 벗어나는지 확인한다.
- GitHub PR 자동화, 자동 머지, 복잡한 CI를 이번 범위에서 제외한다.
- 다음 작은 작업 단위만 지시한다.

### Architect Agent

- ContestSpec과 GapReport를 기준으로 구조를 설계한다.
- 모듈 인터페이스가 단순한지 확인한다.

### Code Agent

- Python 코드 작성/수정
- 테스트 작성
- 실행 오류 수정
- 템플릿 복사 구조 유지

### Rule Guard Agent

- 규칙 위반 가능성을 체크한다.
- 불명확한 항목을 임의로 결정하지 않는다.
- 외부 API/데이터/인터넷/pretrained model 사용 여부를 `unknowns` 또는 `human_decisions`에 남긴다.

### Report Agent

- `gap_report.md`
- `solution_log.md`
- `human_decision_log.md`
- 본선 PT용 설명 초안

## Codex 작업 원칙

1. 한 번에 큰 자동화 시스템을 만들지 않는다.
2. 먼저 `mock_contest_01`에서 실행되는지 확인한다.
3. 실패하면 최소 수정한다.
4. 기능 추가보다 `python factory/run_factory.py --contest examples/mock_contest_01` 성공을 우선한다.
5. GitHub 자동 PR/리뷰픽스/머지는 만들지 않는다.

## 리뷰 프롬프트

```text
방금 만든 MVP를 리뷰해줘.

기준:
1. README/PRD/ARCHITECTURE와 코드 구조가 일치하는가?
2. factory/run_factory.py가 mock contest에서 end-to-end로 실행되는가?
3. contest_spec.yaml과 gap_report.md가 의미 있게 생성되는가?
4. generated/final_harness/run.py가 submission.csv를 생성하는가?
5. 불필요한 GitHub PR 자동화나 과한 구조가 들어가 있지 않은가?
6. 대회 규칙이 불명확한 항목을 unknowns/human_decisions로 남기는가?

수정이 필요하면 최소 수정으로 고쳐줘.
```
