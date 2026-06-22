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

v0.9B Official Contest Package Intake + Coverage Audit 단계는 공개된 공식 안내 원문과 UI 캡처를
local Contest Package source로 등록하고, Input Scanner/Evidence Index/ContestSpec에 반영된 범위를
별도 coverage report로 점검합니다. 공식 문구나 manifest 선언은 자동으로 승인된 결정이 아니며,
`contest_overrides.yaml`을 자동 수정하지 않습니다. 이 단계도 `factory/run_factory.py` 흐름에 자동 결합하지 않습니다.

v0.10A Capability Registry 단계는 현재 factory와 생성되는 base harness가 실제로 제공하는 좁은 능력을
stable Capability ID로 선언하고, 각 capability의 구현 코드와 테스트 symbol이 저장소에 존재하는지
표준 라이브러리 `ast`로 정적으로 검증합니다. Contest Requirement와 Capability를 자동 매칭하지 않고,
Blueprint, GapReport, final harness, `contest_overrides.yaml`도 변경하지 않습니다. 이 단계는
`factory/run_factory.py` 흐름에 자동 결합하지 않습니다.

```bash
python factory/run_capability_registry.py \
  --registry capabilities/registry.json \
  --repo-root . \
  --output generated
```

생성 산출물:

```text
generated/capability_registry.json
generated/capability_registry.md
```

Capability Registry와 Contest Requirement는 다릅니다. Capability Registry는 "공장이 현재 무엇을 할 수
있고 그 코드/테스트 근거가 저장소에 있는가"를 선언하고 감사합니다. Contest Requirement는 특정 대회가
요구하거나 금지하는 조건입니다.

상태 의미:

- `declared_status`: maintainer가 선언한 구현 상태입니다. `implemented`, `partial`, `planned`, `deprecated`를 사용합니다.
- `verification_status`: 선언된 code/test evidence path와 Python top-level symbol 존재 여부입니다. `verified`, `incomplete`, `not_applicable`를 사용합니다.
- `matching_eligibility`: 향후 matcher가 사용할 수 있는 정도입니다. `eligible`, `limited`, `ineligible`를 사용합니다.

`verified`는 코드 및 테스트 근거가 저장소에서 확인됐다는 뜻입니다. 공식 대회 규칙 확인, 사람 승인,
모든 대회 지원 또는 solver 성능 보장을 뜻하지 않습니다.

초기 registry 범위는 manifest validation, input scanning, ContestSpec/override/gap/blueprint/harness 생성,
Evidence Index, coverage audit, AI prompt/intake/review, Code Agent work-package, base harness의 CSV loading,
constant baseline prediction, submission writing, submission verification, validation report emission입니다.

v0.10B Requirement Contract + Deterministic Requirement-Capability Matcher 단계는 특정 대회의
구조화된 산출물(`contest_spec.json`, `evidence_index.json`, 선택 `contest_package_coverage.json`)에서
Contest Requirement를 생성하고, v0.10A Capability Registry의 `provides` token과 정확히 비교합니다.
자연어 원문, 이미지 의미, AI 판단, fuzzy matching, substring matching, alias 추론은 사용하지 않습니다.

Requirement와 Capability는 분리됩니다.

- Requirement: 특정 대회가 요구하거나 금지하거나 아직 공개하지 않은 조건입니다.
- Capability: 현재 factory 또는 generated harness가 실제 코드와 테스트 근거로 제공하는 좁은 능력입니다.
- `harness.baseline.constant.predict`는 constant baseline일 뿐이며 `solver.classification.predict` 같은
  task-specific solver requirement를 충족하지 않습니다.

Requirement 상태는 세 축으로 나뉩니다.

- `provenance_status`: `observed`, `inferred`, `proposed`, `confirmed`, `unknown`, `conflicting`
- `applicability`: `active`, `pending`, `not_modeled`
- matcher 결과: `satisfied`, `partial`, `unmet`, `blocked`, `not_evaluated`, `not_applicable`

`constraint`, `prohibition`, `unresolved` requirement는 Capability token matching으로 준수를 증명할 수 없으므로
`not_evaluated`로 보고합니다. 예를 들어 외부 API capability가 Registry에 없다는 사실만으로 외부 API 금지 준수를
확정하지 않습니다. 이 산출물은 Human Approval, 공식 제출 가능 여부, solver 성능을 보장하지 않습니다.

독립 CLI:

```bash
python factory/run_requirement_match.py \
  --contest-spec generated/contest_spec.json \
  --evidence-index generated/evidence_index.json \
  --capabilities generated/capability_registry.json \
  --coverage generated/contest_package_coverage.json \
  --output generated
```

`--coverage`는 선택입니다. 생성 산출물:

```text
generated/contest_requirements.json
generated/contest_requirements.md
generated/requirement_capability_match.json
generated/requirement_capability_match.md
```

Exit code:

- `0`: 산출물 생성, active must gap 없음
- `1`: structural 또는 IO 오류, 최종 산출물 미생성
- `2`: 산출물 생성, active must gap 존재

v0.11A Decision Ledger 단계는 v0.10B의 Contest Requirement 및 Requirement-Capability Match 결과에서
사람의 판단이 필요한 항목을 결정적으로 식별하고, 선택 입력인 `decision_intake.json`을 검증해 append-only
Decision Ledger를 생성합니다. 이 단계는 `factory/run_factory.py` 흐름에 자동 결합되지 않으며
`contest_overrides.yaml`, ContestSpec, Requirement, Match 결과, Capability Registry, solver source를 수정하지 않습니다.

Decision Intake 최상위 형식:

```json
{
  "schema_version": "v0.11A",
  "artifact_type": "decision_intake",
  "source_digests": {
    "contest_requirements": "sha256:...",
    "requirement_capability_match": "sha256:...",
    "capability_registry": "sha256:..."
  },
  "decisions": [],
  "notes": []
}
```

Decision entry는 `dec.<requirement-stem>.rNNN` 형식의 `decision_id`, `requirement_id`,
`expected_subject_digest`, `actor`, `decision_status`, `action`, 선택 evidence/condition/supersedes 정보를 담습니다.
`actor`는 intake에서 `human` 또는 `ai`만 허용하며, `deterministic`은 intake가 없는 required/not-required ledger
상태를 만들 때만 사용합니다. `ai`는 `proposed`만 가능하고, `human`은 `pending`, `confirmed`, `rejected`만
가능합니다. `confirmed`와 `rejected`는 human만 사용할 수 있습니다.

`action`은 `no_action`, `use_existing_capability`, `implement_missing_capability`, `confirm_value`, `accept_risk`,
`wait_for_information`, `waive_requirement`, `reject_requirement` 중 하나입니다. `pending`은 항상 `no_action`이며,
`confirm_value`는 non-empty known value를 기록만 합니다. confirmed decision도 ContestSpec이나
`contest_overrides.yaml`에 값을 자동 적용하지 않습니다.

Authoritative decision은 다음 조건을 모두 만족할 때만 true입니다.

- `actor == human`
- `decision_status == confirmed`
- decision의 subject digest가 현재 requirement/match 전체 record digest와 일치
- supersession conflict가 없음
- action semantic validation 통과

subject digest는 현재 requirement record 전체와 동일 `requirement_id`의 match record 전체를 canonical JSON으로
직렬화한 SHA-256입니다. source artifact digest mismatch는 warning으로 남기지만 전체 결정을 stale로 만들지는 않습니다.
각 decision의 `expected_subject_digest`가 현재 subject digest와 다르면 해당 current decision은 `stale`입니다.

Supersession은 append-only history입니다. 새 revision은 같은 requirement의 이전 decision을 `supersedes`로 가리킬 수
있고, 낮거나 같은 revision, 자기 자신, 다른 requirement, cycle은 structural error입니다. 복수 unsuperseded leaf가
남으면 자동 선택하지 않고 `conflicting`으로 기록합니다.

독립 CLI:

```bash
python factory/run_decision_ledger.py \
  --requirements generated/contest_requirements.json \
  --matches generated/requirement_capability_match.json \
  --capabilities generated/capability_registry.json \
  --output generated
```

선택 intake:

```bash
python factory/run_decision_ledger.py \
  --requirements generated/contest_requirements.json \
  --matches generated/requirement_capability_match.json \
  --capabilities generated/capability_registry.json \
  --intake /private/path/decision_intake.json \
  --output generated
```

생성 산출물:

```text
generated/decision_intake_template.json
generated/decision_ledger.json
generated/decision_ledger.md
```

Exit code:

- `0`: 산출물 생성, unresolved required/stale/conflicting decision 없음
- `1`: structural 또는 IO 오류, 최종 산출물 미생성
- `2`: 산출물 생성, unresolved required 또는 stale/conflicting decision 존재

`follow_up_required_count > 0`만으로 exit 2가 되지는 않습니다. Exit 0은 Decision Ledger disposition이
완전하다는 뜻일 뿐, 구현 완료, Human Approval, solver 성능 또는 최종 제출 준비 완료를 뜻하지 않습니다.

v0.11B Human Approval Summary + Local Readiness Gate 단계는 Contest Requirement, Requirement-Capability Match,
Decision Ledger, Capability Registry, 선택 `validation_report.json`, 선택 `human_approval_intake.json`을 결합해
현재 저장된 로컬 제출 후보의 기계적 blocker와 명시적 Human Approval 상태를 분리해서 보고합니다.

승인 범위는 오직 `local_submission_candidate`입니다. `approved`는 현재 로컬 artifact가 구성된 readiness checks를
통과했고 현재 readiness digest에 대한 명시적 human approval이 있다는 뜻입니다. 공식 대회 규칙 확인, 공식 제출 허용,
리더보드 점수, solver 성능, 법률/IP 검토, 최종 온라인 제출 성공을 뜻하지 않습니다.

Machine Readiness와 Human Approval은 분리됩니다.

- active must capability gap은 Human Approval이나 `accept_risk`, `waive_requirement`, `reject_requirement` decision으로 우회할 수 없습니다.
- Decision이 `confirmed`여도 `implement_missing_capability`, `confirm_value`, `wait_for_information` 후속 작업이 남으면 readiness blocker입니다.
- Validation Report pass는 제출 파일 구조 검증일 뿐이며 solver gap이나 accuracy를 덮어쓰지 않습니다.
- Human Approval은 machine readiness blocker를 덮어쓰지 않습니다.

Human Approval Intake 최상위 형식:

```json
{
  "schema_version": "v0.11B",
  "artifact_type": "human_approval_intake",
  "source_digests": {
    "contest_requirements": "sha256:...",
    "requirement_capability_match": "sha256:...",
    "decision_ledger": "sha256:...",
    "capability_registry": "sha256:...",
    "validation_report": null
  },
  "readiness_digest": "sha256:...",
  "approvals": [],
  "notes": []
}
```

Approval entry는 `approval.local_submission_candidate.rNNN` 형식이고 `actor`는 `human`만 허용합니다.
`approval_status`는 `pending`, `approved`, `rejected`, `conditional`입니다. `approved`와 `rejected`는 non-empty
rationale과 빈 conditions가 필요하고, `conditional`은 non-empty rationale과 최소 1개 condition이 필요합니다.
조건이 붙은 approved는 허용하지 않습니다.

Readiness digest는 현재 input artifact digest, machine readiness checks 전체, validation report 존재 여부 및 정규화된
validation 상태를 canonical JSON digest로 계산합니다. Human approval history 자체는 digest에 포함하지 않고,
approval entry의 `expected_readiness_digest`가 현재 digest와 다르면 stale approval입니다.

Overall Gate 상태는 다음 중 하나입니다.

- `blocked`: machine readiness blocker 존재
- `awaiting_human_approval`: reviewable이지만 current approval 없음
- `approved`: reviewable이고 current approved approval 존재
- `rejected`: current rejected approval 존재
- `conditional_approval`: current conditional approval 존재
- `stale_approval`: current approval leaf의 readiness digest가 stale
- `conflicting_approval`: 복수 unsuperseded approval leaf 존재

독립 CLI:

```bash
python factory/run_human_approval.py \
  --requirements generated/contest_requirements.json \
  --matches generated/requirement_capability_match.json \
  --decision-ledger generated/decision_ledger.json \
  --capabilities generated/capability_registry.json \
  --validation-report generated/final_harness/outputs/validation_report.json \
  --approval-intake /private/path/human_approval_intake.json \
  --output generated
```

`--validation-report`와 `--approval-intake`는 선택입니다. Local readiness approval에는 validation report가 필요하므로
누락되면 blocker가 됩니다. Output artifact에는 CLI의 절대 입력 경로, 사용자명, WSL mount path, 생성 시각을 기록하지 않습니다.

생성 산출물:

```text
generated/human_approval_intake_template.json
generated/human_approval_summary.json
generated/human_approval_summary.md
```

Exit code:

- `0`: 산출물 생성, Overall Gate가 `approved`
- `1`: structural 또는 IO 오류, 최종 산출물 미생성
- `2`: 산출물 생성, Overall Gate가 `approved`가 아님

v0.12 Submission Handoff Package 단계는 `approved` 상태의 `local_submission_candidate`를 사람이 전달하고 확인할 수
있도록 deterministic package로 묶는다. 이 단계는 v0.11B Human Approval 뒤의 독립 단계이며 `run_factory.py`에 자동
통합되지 않는다. Dacon/SCPC 로그인, 브라우저 자동화, submit API 호출, 파일 업로드, solver 실행, 재학습을 수행하지 않는다.

`approved`와 `frozen`은 다르다. `approved`는 Human Approval Summary가 현재 readiness digest를 승인했다는 뜻이고,
`frozen`은 package candidate digest가 별도 Human Freeze Confirmation과 일치한다는 뜻이다. Freeze Confirmation은
machine readiness blocker나 Human Approval blocker를 덮어쓸 수 없다.

Candidate Digest는 다음 값을 canonical JSON으로 묶은 SHA-256이다.

- package에 들어가는 substantive entry의 실제 byte digest와 size
- approval readiness digest
- current approval ID
- validation report source digest

Freeze Confirmation intake는 `freeze.local_submission_candidate.rNNN` entry를 append-only로 기록한다. `confirmed`는
non-empty rationale과 현재 candidate digest 일치를 요구하며, stale digest, rejected leaf, 복수 leaf conflict를 각각
`stale`, `rejected`, `conflicting` handoff status로 분리한다.

독립 CLI:

```bash
python factory/run_submission_handoff.py \
  --submission generated/final_harness/outputs/submission.csv \
  --validation-report generated/final_harness/outputs/validation_report.json \
  --approval-summary generated/human_approval_summary.json \
  --decision-ledger generated/decision_ledger.json \
  --requirements generated/contest_requirements.json \
  --matches generated/requirement_capability_match.json \
  --capabilities generated/capability_registry.json \
  --output generated
```

선택 Freeze Confirmation:

```bash
python factory/run_submission_handoff.py \
  --submission generated/final_harness/outputs/submission.csv \
  --validation-report generated/final_harness/outputs/validation_report.json \
  --approval-summary generated/human_approval_summary.json \
  --decision-ledger generated/decision_ledger.json \
  --requirements generated/contest_requirements.json \
  --matches generated/requirement_capability_match.json \
  --capabilities generated/capability_registry.json \
  --freeze-confirmation /private/path/freeze_confirmation.json \
  --output generated
```

생성 산출물:

```text
generated/submission_handoff_manifest.json
generated/submission_handoff.md
generated/freeze_confirmation_template.json
generated/submission_handoff_package/
generated/submission_handoff_package.zip
```

Package allowlist는 `submission/submission.csv`, sanitized validation evidence, governance JSON, requirements/match,
capability registry, `HANDOFF.md`, `freeze_manifest.json`, 선택 `governance/freeze_confirmation.json`만 허용한다.
raw validation report는 로컬 절대 경로, test/sample path, message/details를 포함할 수 있어 package에 넣지 않고
`sanitized_validation_evidence`로 축약한다. CLI 절대 입력 경로는 manifest/package에 기록하지 않는다.

ZIP은 Python 표준 라이브러리 `zipfile`의 `ZIP_STORED`만 사용하며 entry name 정렬, timestamp
`1980-01-01 00:00:00`, Unix regular file mode `0o100644`, 빈 comment/extra field로 결정적으로 생성한다.

Exit code:

- `0`: handoff status가 `frozen`
- `1`: structural 또는 IO 오류, 최종 산출물 미생성
- `2`: artifact 생성, handoff status가 `frozen`이 아님

v0.13 Manual Submission Receipt Intake + Post-Submission Audit 단계는 frozen handoff candidate가 사람이 실제
플랫폼에 수동 제출된 뒤, 제출 사실과 receipt metadata를 append-only intake로 기록하고 현재 frozen package에 다시
결합한다. 이 단계는 온라인 제출을 수행하지 않으며 Dacon/SCPC 로그인, 브라우저 자동화, submit API 호출, 파일 업로드,
OCR, screenshot 내용 판독, receipt 자연어 추론, solver 실행/학습을 수행하지 않는다.

`frozen`과 `submitted`는 다르다. `frozen`은 local handoff package byte가 Human Freeze Confirmation과 일치한다는 뜻이고,
`submitted` 계열 platform status는 사람이 입력한 receipt metadata일 뿐이다. Post-submission audit는 실제 제출 보존본
`submitted_file`의 byte가 package 안의 `submission/submission.csv` 및 manifest submission entry SHA-256/size와 정확히
일치하는지 확인한다. Platform status가 `accepted`, `scored`, `rejected` 중 무엇이든 byte binding mismatch는 audit
`blocked`다.

Receipt intake 최상위 형식:

```json
{
  "schema_version": "v0.13",
  "artifact_type": "submission_receipt_intake",
  "scope": "local_submission_candidate",
  "source_digests": {
    "handoff_manifest": "sha256:...",
    "handoff_archive": "sha256:..."
  },
  "candidate_digest": "sha256:...",
  "submission_sha256": "sha256:...",
  "evidence_files": [],
  "receipts": [],
  "notes": []
}
```

Receipt status와 platform status는 분리된다. Receipt status는 `pending`, `recorded`, `retracted`만 허용하고,
platform status는 `unknown`, `submitted`, `processing`, `accepted`, `scored`, `rejected`, `failed`, `cancelled`를
그대로 보존한다. `submitted_at`은 timezone offset이 있는 ISO-8601/RFC3339 문자열이어야 하며 현재 시간을 자동 생성하지
않는다. `scored`일 때만 score object를 허용하고, score value는 float로 변환하지 않는다.

Receipt evidence file은 intake 파일의 parent directory 기준 relative path로만 선언한다. Audit는 evidence file이 symlink가
아닌 regular file이고 size > 0인지 확인한 뒤 `evidence_id`, filename, media type, description, SHA-256, size만
`submission_receipt_evidence_index.json`에 기록한다. Raw evidence file은 `generated/`로 복사하지 않고, OCR/semantic
parsing도 수행하지 않는다.

독립 CLI:

```bash
python factory/run_post_submission_audit.py \
  --handoff-manifest generated/submission_handoff_manifest.json \
  --handoff-archive generated/submission_handoff_package.zip \
  --submitted-file /private/submission/submission.csv \
  --receipt-intake /private/submission/submission_receipt_intake.json \
  --output generated
```

`--receipt-intake`는 선택이다. Receipt가 없으면 artifact binding은 계속 진행되고 audit status는 `awaiting_receipt`가 된다.

생성 산출물:

```text
generated/submission_receipt_template.json
generated/submission_receipt_evidence_index.json
generated/post_submission_audit.json
generated/post_submission_audit.md
```

Exit code:

- `0`: audit status가 `complete`
- `1`: structural 또는 IO 오류, 최종 산출물 미생성
- `2`: artifact 생성, audit status가 `complete`가 아님

`complete`는 수동 제출 receipt metadata와 실제 submitted file byte가 현재 frozen handoff candidate에 정확히 결합되었다는
뜻이다. 플랫폼 합격, 점수 유효성, 규칙 준수, 최종 순위, 법률/IP 적합성을 뜻하지 않는다.

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
contests/scpc_2026_round1/        # gitignored
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

실제 공식 자료와 제한 자료는 기본적으로 repo 밖 private workspace에 보관합니다.

```text
/mnt/c/Dev/scpc-ai-private/scpc_2026_preannouncement
```

repo 내부에서 테스트해야 한다면 `/contests/` 아래에 두며, 이 경로는 Git에서 제외됩니다. 공개 저장소에는
실제 train/test/evaluation data, 공식 제한 자료, contest-specific solver, private prompts, 제출 이력,
API key, 본선용 비공개 코드를 넣지 않습니다. 공개된 사전 안내 원문은 저장할 수 있지만 기본 운영은
local/private workspace를 권장합니다.

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

v0.9B부터 text 문서는 기존 `document_excerpt`를 유지하면서 전체 원문을 4000자 단위
`document_chunks`로 나눕니다. chunk는 overlap 없이 `char_start` inclusive, `char_end` exclusive 범위를
사용하며, chunk text를 순서대로 이어 붙이면 원문 전체가 복원됩니다. Evidence Index는 각 chunk를
`file:<relative_path>:document_chunk:<char_start>:<char_end>` key의 별도 Evidence Record로 승격합니다.
manifest의 role, visibility, origin은 사람이 선언한 metadata이므로 Evidence observed value에 섞지 않습니다.

### Contest Package manifest

Contest Package는 선택 파일인 `contest_package.json`으로 공식 source를 선언할 수 있습니다.

```json
{
  "schema_version": "v0.9B",
  "contest": {
    "name": "2026 SCPC AI Challenge",
    "phase": "preannouncement",
    "platform": "Dacon"
  },
  "sources": [
    {
      "path": "raw/official_notice.txt",
      "role": "official_notice",
      "source_kind": "document",
      "visibility": "public",
      "origin": "Dacon contest guide export"
    }
  ],
  "declared_unknowns": [
    "problem.evaluation_metric",
    "rules.external_api_allowed"
  ]
}
```

`path`, `role`, `source_kind`, `visibility`는 source 필수 필드입니다. `source_kind`는 `document`, `image`,
`data`, `config`, `archive`, `unknown` 중 하나이고, `visibility`는 `public`, `restricted`, `private` 중
하나입니다. source path는 contest root 기준 POSIX 상대 경로만 허용하며 absolute path, Windows drive path,
`..` traversal, 중복 path, manifest 자신을 source로 등록하는 경우는 실패합니다.

`declared_unknowns`는 공식 페이지가 “추후 공개”로 둔 항목을 dotted string으로 기록하는 선언입니다.
이 선언은 값을 추정하거나 승인하지 않습니다.

### Contest Package Coverage

Coverage report는 기존 산출물을 입력으로 사용하는 독립 CLI입니다.

```bash
python factory/run_contest_package_coverage.py \
  --contest /mnt/c/Dev/scpc-ai-private/scpc_2026_preannouncement \
  --artifacts generated \
  --output generated
```

생성 산출물:

```text
generated/contest_package_coverage.json
generated/contest_package_coverage.md
```

상태 의미:

- `captured`: manifest source가 파일, input scan, inventory Evidence와 연결됨
- `modeled_confirmed`: 현재 ContestSpec에 non-unknown 값이 있음
- `modeled_unknown`: 현재 ContestSpec에 unknown 값이 유지됨
- `not_modeled`: 현재 ContestSpec에 직접 필드가 없음
- `missing_source`: manifest source가 scan/evidence와 연결되지 않음
- `conflicting`: 공식 unknown 선언이 human override 없이 non-unknown 값으로 들어감

Coverage는 source coverage, core field coverage, declared unknown coverage, high-risk unknowns,
not-modeled topics를 보고합니다. code-share policy, round schedule, finalist deliverables 같은 항목은
이번 버전에서 ContestSpec에 추가하지 않고 `not_modelled`가 아니라 `not_modeled` 상태로 보고만 합니다.

### `contest_overrides.yaml`

대회 시작 후 사람이 확인한 결정은 contest 폴더 안의 `contest_overrides.yaml`에 기록합니다. 지원 항목은 다음과 같습니다.

```yaml
rules:
  allowed_language: Python
  external_api_allowed: false
  external_data_allowed: false
  pretrained_model_allowed: unknown
  internet_allowed: false
  manual_labeling_allowed: false

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
