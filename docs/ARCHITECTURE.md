# Architecture

## 전체 구조

```text
Contest Folder
  contest_package.json (optional, v0.9B)
  description.md
  rules.md
  evaluation.md
  contest_overrides.yaml (optional)
  train.csv
  test.csv
  sample_submission.csv
        ↓
factory/run_factory.py
        ↓
Spec Builder
  + contest_overrides.yaml 반영
        ↓
generated/contest_spec.yaml
        ↓
Gap Analyzer
        ↓
generated/gap_report.md
        ↓
Blueprint Generator
        ↓
generated/harness_blueprint.yaml
generated/harness_blueprint.md
        ↓
Harness Generator
        ↓
generated/final_harness/
        ↓
Final Harness Run
        ↓
outputs/submission.csv
outputs/validation_report.json
outputs/validation_report.md
```

## 모듈 설명

### 1. `factory/contest_reader.py`

대회 폴더 안의 파일 목록과 텍스트 문서, CSV 메타데이터를 읽는다. 선택 파일인 `contest_overrides.yaml`이 있으면
지원되는 작은 YAML subset으로 읽는다.

### 2. `factory/spec_builder.py`

읽은 정보를 `contest_spec` 딕셔너리로 정리한다. 현재 MVP에서는 규칙 기반으로 문제 유형을 추정한다.
`contest_overrides.yaml`에 기록된 사람이 확인한 규칙, 평가 지표, 출력 제약, solver 정책은 `unknowns` 계산 전에 반영한다.

### 3. `factory/gap_analyzer.py`

공장이 필요로 하는 필수 정보와 현재 spec을 비교해 확인 완료/빈칸/위험/사람 확인 필요 항목을 생성한다.
override로 해결된 항목은 불명확 항목 대신 적용 완료 항목으로 표시한다.

### 4. `factory/blueprint_generator.py`

`ContestSpec`과 `GapReport`를 기준으로 실제 하네스 생성 전에 사용할 설계도인 `HarnessBlueprint`를 만든다.
task type, 입력/출력 컬럼 요약, 추천 템플릿, loader/solver/verifier/submitter 요구사항, 사람 확인 필요 항목과 위험을 정리한다.
override 적용 항목도 남겨 final harness 생성 전 결정 근거를 확인할 수 있게 한다.

### 5. `factory/harness_generator.py`

`harness_blueprint`를 선택적으로 참고해 final harness 설정에 추천 템플릿, verifier 요구사항, 사람 확인 필요 항목, 위험 정보를 남긴다.
`templates/base_harness`를 `generated/final_harness`로 복사하고, `configs/default.json`을 현재 spec에 맞춰 작성한다.
verifier가 제출 파일을 검증할 수 있도록 `test.csv`, `sample_submission.csv`, required columns, id/target column, value constraints를
final harness 설정에 포함한다.

### 6. `templates/base_harness`

실제 대회용 하네스의 최소 구조다.

```text
run.py
src/loader.py
src/solver.py
src/verifier.py
src/submitter.py
src/logger.py
configs/default.json
```

`src/verifier.py`는 solver가 만든 `submission.csv`를 파일 단위로 다시 읽어 `sample_submission.csv`의 컬럼 순서,
`test.csv`의 row count/id 목록, 필수 컬럼, 빈 id/target, 중복 id, `allowed_labels` 제약을 검사한다.
검증 결과는 `outputs/validation_report.json`과 사람이 읽기 쉬운 `outputs/validation_report.md`로 저장된다.

### 7. `factory/ai_problem_analyzer.py`

입력 스캔 결과, 현재 `ContestSpec`, `GapReport`, `HarnessBlueprint` 요약을 바탕으로 사람이 외부 AI 도구에
붙여넣을 프롬프트를 생성한다. 이 단계는 offline-only이며 LLM API를 호출하지 않는다.

### 8. `factory/ai_analysis_intake.py`

사람이 저장한 AI 응답 Markdown에서 `## Machine-readable Analysis Payload` heading 뒤의 첫 `json` fenced code block만
표준 라이브러리 `json`으로 파싱한다. 필수 필드와 override 후보를 검증하고, 지원되지 않는 path, 낮은 confidence,
`unknown` 값, 중복 path, 기존 `contest_overrides.yaml`과 충돌하는 값은 실제 proposed override에서 제외한다.
실제 `contest_overrides.yaml`, `ContestSpec`, `HarnessBlueprint`는 수정하지 않는다.

### 9. `factory/run_ai_analysis_review.py`

AI 응답 intake를 독립 실행하는 CLI다. `factory/run_factory.py` 흐름에 결합하지 않고 다음 검토 산출물만 생성한다.

```text
generated/ai_analysis_candidates.json
generated/ai_analysis_review.md
generated/contest_overrides.proposed.yaml
generated/code_agent_task_plan.md
```

### 10. `factory/code_agent_prompt_builder.py`

v0.7 후보 JSON과 현재 factory 산출물을 읽어 `Code Agent Work Package`를 만든다.
입력은 CLI 인자와 output 디렉터리의 고정 산출물로 제한하며, AI 응답에 포함된 임의 경로나 명령은 실행하지 않는다.
task file 후보는 안전하지 않은 절대 경로, `..`, `.git/`, `generated/`, `runs/`, `.venv/`, secret/env 경로를
allowed 목록에서 제외하고 warning으로 남긴다.

생성 산출물:

```text
generated/code_agent_implementation_prompt.md
generated/code_agent_context.json
```

이 단계는 offline-only이며 Codex, shell command, git, LLM API, source 수정 기능을 자동 실행하지 않는다.

### 11. `factory/run_code_agent_prompt.py`

Code Agent Work Package를 독립 실행하는 CLI다. `factory/run_factory.py`나
`factory/run_ai_analysis_review.py` 흐름에 강제로 결합하지 않는다.

### 11A. `factory/evidence_model.py`

v0.9A Evidence Record와 Evidence Index의 공통 계약을 검증한다. canonical JSON을 기준으로
`ev_` + 16자리 lowercase hex 형식의 안정적인 `evidence_id`를 만들고, 필수 필드, 안전한 contest 상대 경로,
JSON 직렬화 가능성, 중복 ID, deterministic record ordering을 검사한다.

이 모델은 scanner 산출물의 절대 경로, output directory, 생성 시각, 배열 순번, 로컬 머신 경로를 ID 계산에
포함하지 않는다.

### 11B. `factory/evidence_index_builder.py`

`generated/input_scan_report.json`의 `files` 항목을 읽어 검토용 Evidence Index로 정규화한다.
모든 파일에는 inventory Evidence를 만들고, 있으면 CSV/JSON/JSONL preview, document excerpt,
document chunk, preview error를 별도 Evidence로 만든다.

`absolute_path`, `role_candidates`, `file_kind`는 Evidence observed value로 승격하지 않는다. 이 모듈은
입력 파싱과 전체 검증이 끝난 뒤에만 `generated/evidence_index.json`과 `generated/evidence_index.md`를
저장한다.

### 11C. `factory/run_evidence_index.py`

Evidence Index를 독립 실행하는 CLI다.

```bash
python factory/run_evidence_index.py \
  --input-scan generated/input_scan_report.json \
  --output generated
```

이 단계는 `factory/run_factory.py` 흐름에 자동 결합되지 않는다. `ContestSpec`, `GapReport`,
`HarnessBlueprint`, `contest_overrides.yaml`, AI analysis candidates, final harness source를 수정하지 않고
LLM API, shell command, git, subprocess를 실행하지 않는다.

### 11D. `factory/contest_package_manifest.py`

v0.9B Contest Package의 선택 파일인 `contest_package.json`을 읽고 검증한다. manifest는 contest name/phase,
source path/role/source_kind/visibility/origin, declared_unknowns를 담는다. source path는 contest root 기준
POSIX 상대 경로만 허용하고 absolute path, Windows drive path, `..` traversal, 중복 path, 누락 파일,
manifest 자신을 source로 등록하는 경우를 거부한다.

manifest가 없으면 기존 mock contest 흐름을 깨지 않도록 `None`과 빈 source map으로 처리한다. manifest가
있는데 malformed이면 조용히 무시하지 않고 실패한다.

### 11E. `factory/input_scanner.py` v0.9B 확장

Input Scanner는 manifest source map이 있으면 scan file item에 `declared_source` metadata를 붙인다.
이 metadata는 사람이 선언한 role/visibility/origin이며 `role_candidates`나 `file_kind`를 덮어쓰지 않는다.

문서 파일은 기존 `document_excerpt`를 유지하면서 전체 원문을 4000자 단위 `document_chunks`로 추가한다.
chunk는 생성 시각 없이 deterministic하고, `char_start` inclusive / `char_end` exclusive 범위를 사용한다.

### 11F. `factory/contest_package_coverage.py`

Contest Package coverage report를 만든다. 입력은 contest root, `contest_package.json`,
`generated/input_scan_report.json`, `generated/evidence_index.json`, `generated/contest_spec.json`이다.
출력은 다음 두 파일이다.

```text
generated/contest_package_coverage.json
generated/contest_package_coverage.md
```

manifest source와 scan/evidence 연결, document chunk Evidence ID, image inventory Evidence ID,
ContestSpec core field의 confirmed/unknown/not-modeled 상태, declared_unknowns 보존 여부,
high-risk unknowns, not-modeled topics를 보고한다. 공식 source text, manifest, AI response를
`contest_overrides.yaml`로 자동 승격하지 않는다.

### 11G. `factory/run_contest_package_coverage.py`

Contest Package coverage를 독립 실행하는 CLI다.

```bash
python factory/run_contest_package_coverage.py \
  --contest /mnt/c/Dev/scpc-ai-private/scpc_2026_preannouncement \
  --artifacts generated \
  --output generated
```

이 단계는 `factory/run_factory.py` 흐름에 자동 결합되지 않는다.

### 11H. `capabilities/registry.json`

v0.10A Capability Registry source다. Maintainer가 현재 factory와 base harness가 제공하는 좁은 능력을
stable `cap.<scope>.<stable_name>` ID로 선언한다. 각 record는 scope, category, declared status, provides token,
inputs/outputs, implementation evidence, test evidence, dependencies, risk gates, limitations, tags를 담는다.

이 파일은 Contest Requirement가 아니며, 특정 대회 요구사항과 capability를 자동 매칭하지 않는다.
외부 API 실행, Dacon crawling/upload, OCR, Human Approval Summary, 자동 git/Codex 실행 능력은 등록하지 않는다.

### 11I. `factory/capability_model.py`

Capability Registry의 schema와 정적 evidence 규칙을 검증한다. 허용 scope/category/status, capability ID,
provides token, dependency 존재/순환, evidence path 안전성을 확인한다.

Evidence path는 repository root 기준 POSIX 상대 경로만 허용하고 absolute path, Windows drive path, `..`,
`.git/`, `generated/`, `runs/`, `.venv/`, `contests/`, env/secret/credential 경로, directory, repository 밖으로
resolve되는 symlink를 거부한다.

Python evidence file은 import하지 않고 표준 라이브러리 `ast`로 parse해서 top-level `FunctionDef`,
`AsyncFunctionDef`, `ClassDef` symbol 존재만 확인한다. 이 검증은 symbol 존재를 확인할 뿐 동작 의미를
증명하지 않는다.

### 11J. `factory/capability_registry_builder.py`와 `factory/run_capability_registry.py`

`capability_registry_builder.py`는 source registry를 로드하고 repository evidence audit을 수행한 뒤
계산 상태를 붙인다.

```text
verification_status: verified | incomplete | not_applicable
matching_eligibility: eligible | limited | ineligible
```

생성 output은 capability ID 순서로 정렬하고 생성 시각, 절대 repository path, 로컬 사용자명을 포함하지 않는다.
동일 입력에서는 byte-for-byte deterministic한 JSON/Markdown을 생성한다.

독립 CLI:

```bash
python factory/run_capability_registry.py \
  --registry capabilities/registry.json \
  --repo-root . \
  --output generated
```

Exit code:

```text
0: registry 생성, incomplete capability 없음
1: structural/IO 오류, output 생성 안 함
2: registry 생성, incomplete capability 존재
```

이 단계는 `factory/run_factory.py`와 자동 결합되지 않으며 ContestSpec, GapReport, HarnessBlueprint,
final harness, `contest_overrides.yaml`을 수정하지 않는다.

### 11K. `factory/requirement_model.py`

v0.10B Contest Requirement와 Requirement-Capability Match artifact의 공통 계약을 검증한다.
Requirement ID, origin/domain/type/priority/provenance/applicability/risk enum, required token 형식,
source ref, Evidence ID, summary count, deterministic ordering을 검사한다.

Capability requirement는 최소 하나의 exact token을 가져야 하며, constraint/prohibition/unresolved 항목은
token 없이도 표현할 수 있다. 이 모델은 Human Approval이나 공식 규칙 승인을 표현하지 않는다.

### 11L. `factory/contest_requirement_builder.py`

`contest_spec.json`, `evidence_index.json`, 선택 `contest_package_coverage.json`에서
`contest_requirements.json`과 `contest_requirements.md`를 만든다.

생성 범위:

- test.csv loading, prediction row emission
- task-specific solver requirement
- submission CSV writing, column order, schema/row/id/target verification
- local validation report factory policy
- governance constraint/prohibition/unresolved requirements
- coverage high-risk unknown과 not-modeled topic requirements

이 단계는 structured artifact만 읽는다. `description.md`, `rules.md`, `evaluation.md`, document chunk text,
UI 이미지 의미를 파싱해 requirement를 자동 확정하지 않는다.

### 11M. `factory/requirement_capability_matcher.py`

Contest Requirement의 `required_tokens`와 audited Capability Registry의 `provides` token을 정확히 비교한다.
substring, prefix/suffix, fuzzy, case-insensitive, AI 의미 유사도, alias matching은 없다.

Matcher는 provider capability의 transitive dependency와 risk gate도 다시 검사한다. dependency가 limited이면
match는 partial이 될 수 있고, ineligible/missing/cycle dependency 또는 blocked risk gate는 blocked로 보고한다.
constraint/prohibition/unresolved requirement는 token matcher가 준수를 증명할 수 없으므로 `not_evaluated`로 남긴다.

### 11N. `factory/run_requirement_match.py`

Requirement Contract와 Capability Match를 독립 실행하는 CLI다.

```bash
python factory/run_requirement_match.py \
  --contest-spec generated/contest_spec.json \
  --evidence-index generated/evidence_index.json \
  --capabilities generated/capability_registry.json \
  --coverage generated/contest_package_coverage.json \
  --output generated
```

`--coverage`는 선택이다. CLI는 모든 입력의 structural validation을 산출물 저장 전에 끝낸다.

Exit code:

```text
0: 산출물 생성, active must gap 없음
1: structural/IO 오류, 최종 산출물 미생성
2: 산출물 생성, active must gap 존재
```

이 단계도 `factory/run_factory.py`에 자동 결합되지 않으며 ContestSpec, GapReport, HarnessBlueprint,
final harness, `contest_overrides.yaml`, private contest package를 수정하지 않는다.

### 11O. `capabilities/registry.json` v0.10B records

v0.10B는 두 factory capability를 추가한다.

- `cap.factory.contest_requirement_generation`
- `cap.factory.requirement_capability_matching`

두 capability 모두 구현/test evidence symbol을 static audit 대상으로 등록한다. Registry는 여전히 capability 선언이며
Contest Requirement 자체나 official rule approval이 아니다.

### 11P. `factory/decision_model.py`

v0.11A Decision Intake와 Decision Ledger의 공통 계약을 검증한다. canonical JSON digest는
`json.dumps(sort_keys=True, ensure_ascii=False, separators=(",", ":"))` 결과의 UTF-8 SHA-256이며,
digest 형식은 `sha256:<64 lowercase hex>`다.

subject digest는 현재 requirement record 전체와 동일 `requirement_id`의 match record 전체만으로 계산한다.
생성 시각, 로컬 경로, 배열 순번은 digest input에 추가하지 않는다.

Decision Intake validator는 다음을 structural contract로 본다.

- `decision_id`: `dec.<requirement-stem>.rNNN`, revision은 001 이상
- `actor`: `human` 또는 `ai`; `deterministic`은 intake에 허용하지 않음
- `decision_status`: `pending`, `proposed`, `confirmed`, `rejected`
- `ai`는 `proposed`만 가능, `human`은 `pending`, `confirmed`, `rejected`만 가능
- `pending`은 `no_action`, null value, empty selected capabilities
- `confirmed`/`proposed`/`rejected`는 non-empty rationale과 non-`no_action`
- `confirm_value`는 null/empty/`unknown`이 아닌 value 필요
- supersession revision/order/cycle 검사

이 모델은 actor identity 인증이나 rationale의 진실성은 증명하지 않는다.

### 11Q. `factory/decision_ledger_builder.py`

v0.10B 산출물인 `contest_requirements.json`, `requirement_capability_match.json`과 audited
`capability_registry.json`, 선택 `decision_intake.json`을 결합해 append-only Decision Ledger를 만든다.

Decision 상태는 Requirement 상태 및 Capability Match 상태와 분리된다. 예를 들어 사람이 `wait_for_information`을
confirmed로 결정해도 Requirement의 `applicability`가 자동으로 confirmed가 되지 않고, match 결과도 바뀌지 않는다.

Decision Required reason code:

- `active_must_gap`: `priority == must`, `applicability == active`, match가 `partial|unmet|blocked`
- `pending_red`: red risk pending requirement
- `conflicting_provenance`: provenance가 conflicting
- `red_not_modeled`: red risk not-modeled requirement
- `active_red_not_evaluated`: red active requirement인데 match가 not_evaluated

Ledger resolution status는 `not_required`, `pending`, `proposed`, `confirmed`, `rejected`, `stale`, `conflicting`이다.
복수 current leaf 또는 semantic conflict가 있으면 `conflicting`, current leaf digest가 현재 subject와 다르면 `stale`이다.
intake가 없고 decision이 필요하면 `pending`, 필요 없으면 `not_required`다.

Authoritative는 human confirmed, current subject digest, supersession conflict 없음, semantic validation 통과일 때만 true다.
AI proposal과 pending template은 authoritative가 아니다.

`implement_missing_capability`, `confirm_value`, `wait_for_information`은 confirmed decision이어도 후속 구현 또는 공식
정보 확인이 필요하므로 `follow_up_required`로 계산한다. `use_existing_capability`, `accept_risk`,
`waive_requirement`, `reject_requirement`는 ledger 상 disposition 완료로 분류하지만 최종 제출 준비 완료를 의미하지 않는다.

생성 산출물:

```text
generated/decision_intake_template.json
generated/decision_ledger.json
generated/decision_ledger.md
```

Template은 `decision_required == true`이고 `resolution_status != confirmed`인 record만 대상으로 pending entry를 만든다.
current leaf가 하나 있으면 다음 revision과 `supersedes`를 자동 설정한다. 복수 leaf conflict는 자동 선택하지 않고
warning만 남긴다.

### 11R. `factory/run_decision_ledger.py`

Decision Ledger를 독립 실행하는 CLI다.

```bash
python factory/run_decision_ledger.py \
  --requirements generated/contest_requirements.json \
  --matches generated/requirement_capability_match.json \
  --capabilities generated/capability_registry.json \
  --intake /private/path/decision_intake.json \
  --output generated
```

`--intake`는 선택이다. CLI는 원본 input artifact를 수정하지 않고, output artifact에는 절대 input path나 생성 시각을
포함하지 않는다.

Exit code:

```text
0: 산출물 생성, unresolved required/stale/conflicting decision 없음
1: structural/IO 오류, 최종 산출물 미생성
2: 산출물 생성, unresolved required 또는 stale/conflicting decision 존재
```

`follow_up_required_count > 0`만으로 exit 2가 되지는 않는다. Exit 0은 Decision Ledger disposition이 완전하다는 뜻이며,
Human Approval, solver 성능, 구현 완료, 최종 제출 준비 완료를 뜻하지 않는다.

이 단계는 v0.10B 뒤의 독립 단계이며 `factory/run_factory.py`에 통합하지 않는다. ContestSpec, Requirement,
Requirement-Capability Match, Capability Registry, `contest_overrides.yaml`, final harness source, private contest package를
수정하지 않는다.

### 11S. `capabilities/registry.json` v0.11A records

v0.11A는 두 factory capability를 추가한다.

- `cap.factory.decision_intake_validation`
- `cap.factory.decision_ledger_generation`

두 capability 모두 구현/test evidence symbol을 static audit 대상으로 등록한다. Registry는 Decision Ledger 기능을
선언하지만 Human Approval Summary나 최종 go/no-go 판정 capability는 포함하지 않는다.

### 11T. `factory/approval_model.py`

v0.11B Human Approval Intake와 Human Approval Summary의 공통 계약을 검증한다. 승인 범위는
`local_submission_candidate` 하나로 제한하고, approval entry ID는
`approval.local_submission_candidate.rNNN` 형식만 허용한다.

Human Approval actor는 `human`만 허용한다. `pending`, `approved`, `rejected`, `conditional` 상태를 구분하며,
`approved`와 `rejected`는 non-empty rationale과 빈 conditions를 요구한다. 조건이 있는 approval은
`conditional`이어야 하며 approval granted가 아니다.

Supersession은 append-only history다. 동일 scope의 기존 approval만 supersede할 수 있고, unknown ID, 자기 자신,
낮거나 같은 revision, cycle은 structural error다. 복수 unsuperseded leaf는 자동 선택하지 않고 conflict 상태로 남긴다.

`build_readiness_digest`는 기존 `factory.decision_model.canonical_json_digest`를 재사용한다. Digest input은 현재
source artifact digest, machine readiness checks 전체, validation report 존재 여부 및 정규화된 validation 상태다.
Human approval history 자체는 readiness digest에 포함하지 않는다.

### 11U. `factory/human_approval_builder.py`

Decision Ledger 뒤의 독립 Local Readiness Gate builder다. 입력은 `contest_requirements.json`,
`requirement_capability_match.json`, `decision_ledger.json`, `capability_registry.json`, 선택 `validation_report.json`,
선택 `human_approval_intake.json`이다.

이 builder는 다음 상태를 섞지 않는다.

- Requirement 상태
- Capability Match 상태
- Decision Ledger 상태
- Machine Readiness 상태
- Human Approval 상태
- Overall Gate 상태

Machine Readiness checks는 active must gap, unresolved/stale/conflicting/follow-up decision, Ledger source/subject drift,
required capability health, validation report presence/pass/warnings를 계산한다. active must gap은 Human Approval이나
Decision으로 우회할 수 없다. confirmed `implement_missing_capability`, `confirm_value`, `wait_for_information`은
follow-up blocker로 남는다.

Required capability health는 active must satisfied match의 matched/dependency capability와 authoritative
`use_existing_capability` decision의 selected capability만 검사한다. 관련 없는 planned/ineligible capability는 전체 gate를
막지 않는다.

Validation Report는 구조와 count 일관성을 검증하지만 summary에는 `present`, `passed`, count, 실패 check name만 복사한다.
message/details/path 계열 값은 절대 경로를 포함할 수 있으므로 Human Approval Summary로 복사하지 않는다.

생성 산출물:

```text
generated/human_approval_intake_template.json
generated/human_approval_summary.json
generated/human_approval_summary.md
```

Machine readiness가 blocked이면 approval template에는 entry를 만들지 않는다. Reviewable이고 approval history가 없으면
`approval.local_submission_candidate.r001` pending entry를 만든다. pending/stale/conditional leaf가 있으면 다음 revision과
`supersedes`를 설정한다. current approved/rejected leaf 또는 conflict는 자동으로 새 entry를 만들지 않는다.

### 11V. `factory/run_human_approval.py`

Human Approval Summary를 독립 실행하는 CLI다.

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

Exit code:

```text
0: 산출물 생성, Overall Gate == approved
1: structural/IO 오류, 최종 산출물 미생성
2: 산출물 생성, Overall Gate != approved
```

Exit 0은 local readiness approval일 뿐이며 공식 제출 허용, solver 성능, 리더보드 점수, 법률/IP 검토, 온라인 제출 성공을
뜻하지 않는다. 이 단계는 `factory/run_factory.py`에 통합하지 않고, ContestSpec, Requirement, Match, Decision Ledger,
Capability Registry, `contest_overrides.yaml`, final harness source, private contest package를 수정하지 않는다.

### 11W. `capabilities/registry.json` v0.11B records

v0.11B는 두 factory capability를 추가한다.

- `cap.factory.human_approval_intake_validation`
- `cap.factory.local_readiness_gate_generation`

두 capability 모두 구현/test evidence symbol을 static audit 대상으로 등록한다. Registry는 local readiness gate 기능을
선언하지만 official contest acceptance, Human identity authentication, solver quality, legal/IP review, online submission
success를 증명하지 않는다.

### 11X. `factory/handoff_model.py`

v0.12 Submission Handoff와 Human Freeze Confirmation의 공통 계약을 검증한다. Handoff scope는
`local_submission_candidate` 하나로 제한하고, freeze confirmation ID는 `freeze.local_submission_candidate.rNNN`만
허용한다. `actor`는 `human`만 허용하며 `pending`, `confirmed`, `rejected` 상태를 구분한다.

Confirmed/rejected confirmation은 non-empty rationale이 필요하다. Supersession은 append-only history이며 동일 scope의
기존 confirmation만 supersede할 수 있다. unknown ID, 자기 자신, 낮거나 같은 revision, cycle은 structural error다.
복수 unsuperseded leaf는 자동 선택하지 않고 conflict 상태로 남긴다.

이 모듈은 파일 byte SHA-256 (`sha256:<64 lowercase hex>`)과 package path 안전성도 검증한다. Package path는 POSIX
relative path만 허용하며 absolute path, Windows drive path, `..`, `.`, empty segment, backslash, NUL을 거부한다.

### 11Y. `factory/submission_handoff_builder.py`

v0.11B Human Approval Summary 뒤의 독립 handoff builder다. 입력은 `submission.csv`, `validation_report.json`,
`human_approval_summary.json`, `decision_ledger.json`, `contest_requirements.json`, `requirement_capability_match.json`,
`capability_registry.json`, 선택 `freeze_confirmation_intake.json`이다.

이 builder는 다음 상태 계층을 섞지 않는다.

- Human Approval Summary status
- Handoff Preflight status
- Package Candidate status
- Freeze Confirmation status
- Final Handoff status

Preflight는 Human Approval Summary가 approved인지, machine readiness가 reviewable인지, human approval이 authoritative
및 granted인지, source digest가 현재 input artifact의 canonical digest와 일치하는지, readiness digest가 재계산 결과와
일치하는지 확인한다. Submission 파일은 symlink가 아닌 regular `.csv`, size > 0, UTF-8/UTF-8-SIG header read 가능,
최소 1개 column을 요구한다. Validation report는 `passed == true`, `error_count == 0`, report의 submission path가 현재
CLI submission과 resolve 기준으로 일치해야 한다.

Validation report에는 submission byte digest가 없으므로 snapshot consistency는 보수적으로만 검사한다. Report가
`required_columns_present.details.submission_columns` 또는 `row_count_matches_test.details.submission_row_count`를 제공하면
현재 CSV header/row count와 정확히 일치해야 한다. Detail이 없으면 warning이며, exact byte binding은 candidate digest와
freeze confirmation이 담당한다.

Package는 directory scan으로 자동 수집하지 않고 고정 allowlist만 작성한다.

```text
submission/submission.csv
evidence/validation_evidence.json
governance/human_approval_summary.json
governance/decision_ledger.json
requirements/contest_requirements.json
requirements/requirement_capability_match.json
capabilities/capability_registry.json
HANDOFF.md
freeze_manifest.json
governance/freeze_confirmation.json  # optional
```

Raw validation report는 package에 넣지 않는다. `submission_path`, `test_csv_path`, `sample_submission_csv_path`,
message/details 계열 값에 로컬 절대 경로나 민감한 구조가 들어갈 수 있기 때문이다. Package에는
`sanitized_validation_evidence`만 들어가며 check name, passed, severity만 보존한다.

Candidate Digest는 substantive package entry만 포함한다. `HANDOFF.md`, `freeze_manifest.json`,
`freeze_confirmation.json`은 순환 digest를 피하기 위해 제외한다. Submission CSV는 원본 byte를 그대로 복사하고, JSON package
artifact는 `json.dumps(..., ensure_ascii=False, sort_keys=True, indent=2) + "\n"` UTF-8 byte로 직렬화한다.

Handoff status 우선순위는 preflight blocker `blocked`, 복수 confirmation leaf `conflicting`, stale digest `stale`,
rejected leaf `rejected`, current human confirmed `frozen`, 그 외 `prepared`다. `frozen`만 최종 handoff로 인정한다.

### 11Z. `factory/run_submission_handoff.py`

Submission Handoff를 독립 실행하는 CLI다. `factory/run_factory.py`에 통합하지 않는다.

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

Preflight blocked이면 manifest/Markdown/template만 쓰고 stale `submission_handoff_package/` 및
`submission_handoff_package.zip`은 제거한다. Package는 임시 directory에서 완성한 뒤 교체한다.

ZIP은 Python 표준 라이브러리 `zipfile`만 사용하고 `ZIP_STORED`, sorted entry names, timestamp
`1980-01-01 00:00:00`, `create_system=3`, Unix regular file mode `0o100644`, 빈 comment/extra field를 사용한다.
같은 입력과 같은 handoff 상태에서는 ZIP byte가 동일해야 한다.

Exit code:

```text
0: handoff status == frozen
1: structural/IO 오류
2: artifact 생성, frozen이 아님
```

이 단계는 Dacon/SCPC 로그인, 파일 업로드, submit API 호출, 브라우저 자동화, solver 실행, 재학습을 수행하지 않는다.
Frozen은 local handoff byte 동결만 의미하며 official contest acceptance, solver quality, legal/IP review, online
submission success를 보장하지 않는다.

### 11AA. `capabilities/registry.json` v0.12 records

v0.12는 두 factory capability를 추가한다.

- `cap.factory.freeze_confirmation_validation`
- `cap.factory.submission_handoff_package_generation`

두 capability 모두 구현/test evidence symbol을 static audit 대상으로 등록한다. Registry total은 25이며 checked-in audit에서
25개 모두 verified/eligible이어야 한다.

### 11AB. `factory/receipt_model.py`

v0.13 Manual Submission Receipt Intake의 공통 계약을 검증한다. Scope는 `local_submission_candidate` 하나로 제한하고,
receipt ID는 `receipt.local_submission_candidate.rNNN`만 허용한다. `actor`는 `human`만 허용한다.

Receipt status는 `pending`, `recorded`, `retracted`로 제한된다. Platform status는 별도 계층이며 `unknown`, `submitted`,
`processing`, `accepted`, `scored`, `rejected`, `failed`, `cancelled` 값을 그대로 보존한다. `recorded` receipt는
platform token, submission identifier, timezone offset이 있는 submitted_at, basename uploaded filename, non-empty
rationale을 요구한다. `scored`일 때만 score object를 허용하며 score value는 문자열로 보존한다.

Supersession은 append-only history다. 동일 scope의 기존 receipt만 supersede할 수 있고 unknown ID, 자기 자신,
낮거나 같은 revision, cycle은 structural error다. 복수 unsuperseded leaf는 자동 선택하지 않는다.

Evidence declaration은 `receipt_ev.*` ID와 POSIX relative path만 허용한다. Absolute path, Windows drive path, `..`, `.`,
empty segment, backslash, NUL은 거부한다.

### 11AC. `factory/post_submission_audit.py`

v0.12 Submission Handoff 뒤의 독립 audit builder다. 입력은 frozen `submission_handoff_manifest.json`,
`submission_handoff_package.zip`, 사람이 실제 플랫폼에 업로드했다고 주장하는 local preserved `submitted_file`, 선택
`submission_receipt_intake.json`이다.

이 builder는 다음 상태 계층을 섞지 않는다.

- Handoff status
- Artifact binding status
- Receipt record status
- Platform status
- Post-submission audit status

Artifact binding은 frozen handoff manifest, archive safety, freeze manifest binding, submitted file byte binding을
검증한다. Archive는 symlink가 아닌 `.zip` regular file이어야 하고, duplicate filename, directory entry, non-stored entry,
allowlist mismatch, path traversal을 blocker로 보고한다. Allowlist는 v0.12 package paths 10개로 고정된다.

Manifest candidate entry마다 ZIP entry byte SHA-256과 size를 다시 계산한다. `freeze_manifest.json`은 manifest의
candidate digest, approval readiness digest, current approval ID, freeze confirmation status/ID, candidate entries와
일치해야 한다. `submitted_file`은 symlink가 아닌 non-empty `.csv` regular file이어야 하며, 다음 세 값이 정확히 같아야 한다.

```text
submitted_file SHA-256
ZIP submission/submission.csv SHA-256
manifest role=submission entry SHA-256
```

Receipt state는 leaf receipt 기준으로 `not_provided`, `pending`, `recorded`, `retracted`, `stale`, `conflicting`을 계산한다.
Leaf의 expected candidate digest 또는 expected submission SHA-256이 현재 input과 다르면 stale이다. Source digest mismatch는
warning으로 보존한다.

Evidence index는 declared evidence file의 digest와 size만 기록한다. Relative path, base directory, absolute path, OCR text,
raw evidence content는 output에 포함하지 않는다. Recorded receipt가 evidence를 참조했는데 파일이 missing/symlink/invalid이면
audit blocker다. Recorded receipt가 evidence를 참조하지 않는 것은 허용하되 warning으로 남긴다.

생성 산출물:

```text
generated/submission_receipt_template.json
generated/submission_receipt_evidence_index.json
generated/post_submission_audit.json
generated/post_submission_audit.md
```

`submission_receipt_template.json`은 artifact binding이 matched이고 receipt history가 없으면 r001 pending entry를 제안한다.
Pending 또는 stale leaf가 있으면 다음 revision으로 supersedes template을 만든다. Recorded/retracted current leaf 또는 conflict는
자동 template entry를 만들지 않는다.

### 11AD. `factory/run_post_submission_audit.py`

Post-submission audit를 독립 실행하는 CLI다. `factory/run_factory.py`에 통합하지 않는다.

```bash
python factory/run_post_submission_audit.py \
  --handoff-manifest generated/submission_handoff_manifest.json \
  --handoff-archive generated/submission_handoff_package.zip \
  --submitted-file /private/submission/submission.csv \
  --receipt-intake /private/submission/submission_receipt_intake.json \
  --output generated
```

`--receipt-intake`는 선택이다. Receipt evidence는 intake 파일 parent directory 기준으로 resolve하며 별도 evidence root option을
두지 않는다.

Output은 임시 directory에서 4개 artifact를 모두 완성한 뒤 교체한다. Structural/IO error에서는 최종 artifact를 부분 생성하지
않고, 같은 입력에서는 byte-for-byte deterministic해야 한다. 생성 시각과 CLI 절대 경로는 output에 기록하지 않는다.

Exit code:

```text
0: audit status == complete
1: structural/IO 오류
2: artifact 생성, complete가 아님
```

이 단계는 실제 제출 자동화, 브라우저 로그인, 플랫폼 API 호출, receipt 자동 다운로드, screenshot OCR, receipt 자연어 해석,
leaderboard 조회, solver 성능 평가, 전자서명/신원 인증을 수행하지 않는다. Audit complete는 local byte와 manually declared
receipt metadata binding만 의미하며 official acceptance, score validity, compliance, final rank를 보장하지 않는다.

### 11AE. `capabilities/registry.json` v0.13 records

v0.13은 두 factory capability를 추가한다.

- `cap.factory.submission_receipt_validation`
- `cap.factory.post_submission_audit_generation`

두 capability 모두 구현/test evidence symbol을 static audit 대상으로 등록한다. Registry total은 27이며 checked-in audit에서
27개 모두 verified/eligible이어야 한다.

### 12. `factory/experiment_manager.py`

factory 실행 이력을 `runs/run_001` 형태로 저장한다.

## 설계 원칙

- 먼저 작동하는 end-to-end를 만든다.
- solver 성능보다 구조/재현성/규칙 안전을 우선한다.
- GitHub 자동화는 P0에서 제외한다.
- 외부 LLM/API는 optional adapter로만 둔다.
