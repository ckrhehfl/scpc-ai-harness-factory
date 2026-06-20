# SCPC AI Harness Factory

2026 Samsung Collegiate Programming Challenge : AI 챌린지 대응을 위한 **Meta-Harness Factory MVP**입니다.

이 프로젝트의 목표는 대회 시작 후 공개되는 문제 설명, 규칙, 평가 기준, 데이터 파일, `sample_submission.csv`를 바탕으로 다음 산출물을 빠르게 생성하는 것입니다.

```text
contest folder
→ contest_spec.yaml
→ gap_report.md
→ generated/final_harness/
→ submission.csv
```

## 현재 MVP 범위

포함합니다.

- mock contest 기반 end-to-end 실행
- ContestSpec 생성
- Gap Report 생성
- base harness scaffold 생성
- submission.csv 생성
- 간단한 pytest 테스트
- 규칙/사람 개입 체크리스트 문서

포함하지 않습니다.

- GitHub PR 자동화
- 자동 리뷰픽스
- 자동 머지
- 복잡한 CI
- 대회용 최종 solver 성능 최적화
- 외부 LLM API 런타임 사용 확정

## 폴더 구조

```text
factory/                  # 하네스를 만드는 공장 코드
templates/base_harness/   # 생성될 하네스의 기본 템플릿
examples/mock_contest_01/ # 실제 문제 공개 전 테스트용 가짜 대회 데이터
generated/                # factory 실행 결과물
docs/                     # 설계/규칙/사람 개입 문서
skills/                   # Claude/Codex에게 읽힐 작업 절차서
tests/                    # MVP 검증용 테스트
```

## `.venv` 관리 원칙

`.venv`는 로컬 전용 Python 가상환경입니다. GitHub에 올리지 않고, 각 개발 환경에서 새로 만듭니다.

- Windows에서 만든 `.venv`와 WSL/Linux에서 만든 `.venv`는 내부 구조가 다르므로 서로 재사용하지 않습니다.
- PC와 노트북을 오갈 때 `.venv` 폴더를 복사하지 않습니다. 각 기기에서 `python -m venv .venv` 또는 `python3 -m venv .venv`로 새로 만듭니다.
- 동일 환경을 재현하는 기준은 `.venv` 폴더가 아니라 `requirements.txt`입니다.
- `generated/`와 `runs/`는 실행 산출물이므로 기본적으로 GitHub에 올리지 않습니다. `factory/run_factory.py`를 실행하면 다시 생성할 수 있어야 합니다.

## 빠른 실행

### Windows CMD

```bat
cd /d C:\Dev\scpc-ai-harness-factory
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python factory\run_factory.py --contest examples\mock_contest_01
python generated\final_harness\run.py
pytest
```

### PowerShell

```powershell
cd C:\Dev\scpc-ai-harness-factory
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python factory\run_factory.py --contest examples\mock_contest_01
python generated\final_harness\run.py
pytest
```

### WSL/Linux

```bash
cd /mnt/c/Dev/scpc-ai-harness-factory
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python factory/run_factory.py --contest examples/mock_contest_01
python generated/final_harness/run.py
pytest
```

정상 실행되면 다음 파일들이 생성됩니다.

```text
generated/contest_spec.yaml
generated/gap_report.md
generated/final_harness/
generated/final_harness/outputs/submission.csv
runs/run_001/run_log.json
```

## 대회 시작 후 사용법

실제 대회 데이터가 공개되면 다음처럼 별도 폴더를 만들어 넣습니다.

```text
contests/scpc_2026_round1/
  description.md
  rules.md
  evaluation.md
  train.csv
  test.csv
  sample_submission.csv
```

그 후 실행합니다.

```bat
python factory\run_factory.py --contest contests\scpc_2026_round1
python generated\final_harness\run.py
```

먼저 `generated/gap_report.md`를 확인하고, 규칙상 애매한 부분은 `docs/HUMAN_DECISION_LOG.md`에 기록한 뒤 solver를 개선합니다.
