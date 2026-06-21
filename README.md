# SCPC AI Harness Factory

2026 Samsung Collegiate Programming Challenge : AI 챌린지 대응을 위한 **Meta-Harness Factory MVP**입니다.

이 프로젝트의 목표는 대회 시작 후 공개되는 문제 설명, 규칙, 평가 기준, 데이터 파일, `sample_submission.csv`를 바탕으로 다음 산출물을 빠르게 생성하는 것입니다.

```text
contest folder
→ contest_spec.yaml
→ gap_report.md
→ harness_blueprint.yaml / harness_blueprint.md
→ generated/final_harness/
→ submission.csv
```

## 현재 MVP 범위

포함합니다.

- mock contest 기반 end-to-end 실행
- ContestSpec 생성
- Gap Report 생성
- Harness Blueprint 생성
- base harness scaffold 생성
- submission.csv 생성
- submission.csv 형식 검증 및 validation_report 생성
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
examples/mock_contest_01/ # 다지선다형 테스트용 가짜 대회 데이터
examples/mock_contest_02/ # 텍스트 분류 테스트용 가짜 대회 데이터
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

v0.1 안정화용 텍스트 분류 mock contest도 같은 흐름으로 검증합니다.

```bash
python factory/run_factory.py --contest examples/mock_contest_02
python generated/final_harness/run.py
pytest
```

v0.2 ContestSpec 스키마 분석 검증은 두 mock contest를 모두 실행한 뒤 `generated/contest_spec.yaml`과
`generated/gap_report.md`에서 컬럼 상세, train/test/sample_submission 컬럼 차이, 제출 형식 추론 근거를 확인합니다.

v0.3 Harness Blueprint 단계는 `ContestSpec`과 `GapReport`를 기반으로 `generated/harness_blueprint.yaml` 및
`generated/harness_blueprint.md`를 생성한 뒤 final harness 생성을 진행합니다. Blueprint에는 task type, 추천 템플릿,
loader/solver/verifier/submitter 요구사항, 사람 확인 필요 항목, 알려진 위험이 포함됩니다.

v0.4 Decision Override 단계는 contest 폴더의 선택 파일인 `contest_overrides.yaml`을 읽어 사람이 확인한 규칙,
평가 지표, 출력 제약, solver 정책을 `ContestSpec`, `GapReport`, `HarnessBlueprint`에 반영합니다.

v0.5 Submission Verifier 단계는 final harness가 `submission.csv`를 생성한 뒤 `sample_submission.csv` 컬럼 순서,
`test.csv` 행 수/id 목록, 필수 컬럼, 빈 값, 중복 id, `allowed_labels` 제약을 검증하고
`outputs/validation_report.json` 및 `outputs/validation_report.md`를 생성합니다.

v0.6 Input Scanner + AI Problem Analyzer 단계는 contest 폴더 전체를 스캔해
`generated/input_scan_report.json`, `generated/input_scan_report.md`,
`generated/ai_problem_analysis_prompt.md`를 생성합니다. 이 프롬프트는 사람이 ChatGPT, Claude, Codex 등에
직접 넣기 위한 오프라인 산출물이며 factory가 LLM API를 호출하지 않습니다.

v0.7 AI Analysis Result Intake + Human Review Pack 단계는 사람이 저장한
`generated/ai_problem_analysis_response.md`를 읽어 후보 정보를 구조화합니다. 실제 `contest_overrides.yaml`,
`ContestSpec`, `HarnessBlueprint`는 자동 수정하지 않고, 검토용 산출물과
`generated/contest_overrides.proposed.yaml`만 생성합니다.

v0.8 Code Agent Work Package 단계는 v0.7의 후보 JSON과 현재 factory 산출물을 모아 사람이 Codex에 직접
붙여넣을 수 있는 구현 프롬프트를 생성합니다. Codex, shell command, git, LLM API를 자동 실행하지 않고,
실제 source나 `contest_overrides.yaml`도 수정하지 않습니다.

v0.9A Evidence Contract + Evidence Index 단계는 기존 Input Scanner 산출물인
`generated/input_scan_report.json`을 읽어 기계적으로 관찰된 사실만 공통 Evidence Record로 정규화합니다.
Decision Ledger, AI 추론, 사람 결정은 아직 포함하지 않으며, `factory/run_factory.py` 흐름에도 자동 결합하지 않습니다.

정상 실행되면 다음 파일들이 생성됩니다.

```text
generated/contest_spec.yaml
generated/gap_report.md
generated/harness_blueprint.yaml
generated/harness_blueprint.md
generated/final_harness/
generated/final_harness/outputs/submission.csv
generated/final_harness/outputs/validation_report.json
generated/final_harness/outputs/validation_report.md
runs/run_001/run_log.json
```

## 대회 시작 후 사용법

실제 대회 데이터가 공개되면 다음처럼 별도 폴더를 만들어 넣습니다.

```text
contests/scpc_2026_round1/
  description.md
  rules.md
  evaluation.md
  contest_overrides.yaml  # 선택: 사람이 확인한 규칙/평가/출력/solver 결정
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

### AI 분석 응답 검토

`generated/ai_problem_analysis_prompt.md`를 외부 AI 도구에 직접 입력한 뒤 응답을 다음 파일로 저장합니다.

```text
generated/ai_problem_analysis_response.md
```

그 다음 별도 review CLI를 실행합니다.

```bash
python factory/run_ai_analysis_review.py \
  --contest examples/mock_contest_02 \
  --analysis-response generated/ai_problem_analysis_response.md \
  --output generated
```

생성되는 파일은 모두 검토용 후보입니다.

```text
generated/ai_analysis_candidates.json
generated/ai_analysis_review.md
generated/contest_overrides.proposed.yaml
generated/code_agent_task_plan.md
```

`contest_overrides.proposed.yaml`은 실제 contest 폴더가 아니라 output 디렉터리에만 생성됩니다.
승인된 항목만 사람이 contest 폴더의 `contest_overrides.yaml`에 직접 반영해야 합니다.

### Code Agent 구현 프롬프트 생성

v0.7 review 산출물이 준비된 뒤 별도 CLI를 실행합니다.

```bash
python factory/run_code_agent_prompt.py \
  --contest examples/mock_contest_02 \
  --analysis-candidates generated/ai_analysis_candidates.json \
  --output generated
```

생성되는 파일은 사람이 Codex에 전달하기 위한 offline work package입니다.

```text
generated/code_agent_implementation_prompt.md
generated/code_agent_context.json
```

이 단계는 `generated/contest_spec.json`, `generated/gap_report.md`,
`generated/harness_blueprint.md`, `generated/code_agent_task_plan.md`를 읽고,
있으면 `generated/ai_analysis_review.md`도 포함합니다. 필수 파일이나 JSON이 잘못된 경우 non-zero로 실패하며
부분적인 최종 prompt 파일을 만들지 않습니다.

### Evidence Index 생성

v0.9A Evidence Index는 `run_factory.py`가 만든 `generated/input_scan_report.json`을 입력으로 사용하는
독립 CLI입니다.

```bash
python factory/run_evidence_index.py \
  --input-scan generated/input_scan_report.json \
  --output generated
```

생성 산출물은 검토용 projection입니다.

```text
generated/evidence_index.json
generated/evidence_index.md
```

Evidence Index에는 파일 inventory, CSV/JSON/JSONL preview 구조, 문서 excerpt, preview error처럼
scanner가 결정적으로 관찰한 값만 포함합니다. `absolute_path`, `role_candidates`, `file_kind`는 관찰 사실
Evidence로 승격하지 않습니다. 이 단계는 `ContestSpec`, `GapReport`, `HarnessBlueprint`,
`contest_overrides.yaml`, AI analysis candidates, final harness source를 수정하지 않습니다.

향후 Decision Ledger는 Evidence Record의 `evidence_id`를 참조할 수 있지만, Decision Ledger 자체는
v0.9A 범위에 포함되지 않습니다.

### `contest_overrides.yaml`

대회 시작 후 사람이 확인한 결정은 contest 폴더 안의 `contest_overrides.yaml`에 기록합니다. 지원 항목은 다음과 같습니다.

```yaml
rules:
  external_api_allowed: false
  external_data_allowed: false
  pretrained_model_allowed: unknown
  internet_allowed: false

problem:
  evaluation_metric: accuracy
  task_type: classification

output:
  value_constraints:
    allowed_labels:
      - positive
      - negative

human_decisions:
  final_solver_policy: local_baseline_only
  use_external_llm_api: false
```

적용된 override는 `generated/contest_spec.yaml`의 `decision_overrides`, `generated/gap_report.md`의
`Override 적용`, `generated/harness_blueprint.md`의 `Override Applied`에서 확인합니다.
