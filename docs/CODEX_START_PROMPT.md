# Codex Start Prompt

아래 프롬프트를 Codex 앱에 넣고 작업을 시작한다.

```text
이 레포는 2026 SCPC AI Challenge용 Meta-Harness Factory MVP다.

현재 목표:
- GitHub PR 자동화, 자동 리뷰픽스, 자동 머지는 하지 않는다.
- mock contest 기준으로 end-to-end 실행을 확인한다.
- 먼저 구조를 이해하고, 불필요한 과설계를 하지 않는다.

실행해야 할 명령:
1. python -m venv .venv
2. .venv\Scripts\activate
3. pip install -r requirements.txt
4. python factory\run_factory.py --contest examples\mock_contest_01
5. python generated\final_harness\run.py
6. pytest

검증 기준:
- generated/contest_spec.yaml 생성
- generated/gap_report.md 생성
- generated/final_harness 생성
- generated/final_harness/outputs/submission.csv 생성
- pytest 통과

작업 요청:
위 명령을 실행하고 실패하는 부분이 있으면 최소 수정으로 고쳐라.
범위를 넘겨 GitHub 자동화/CI/멀티에이전트 대형 구조를 만들지 마라.
수정 후 README의 실행 방법과 실제 코드가 일치하는지 확인하라.
```
