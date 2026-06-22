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
외부 API 실행, Dacon crawling/upload, OCR, Decision Ledger, Human Approval Summary, 자동 git/Codex 실행 능력은
등록하지 않는다.

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

### 12. `factory/experiment_manager.py`

factory 실행 이력을 `runs/run_001` 형태로 저장한다.

## 설계 원칙

- 먼저 작동하는 end-to-end를 만든다.
- solver 성능보다 구조/재현성/규칙 안전을 우선한다.
- GitHub 자동화는 P0에서 제외한다.
- 외부 LLM/API는 optional adapter로만 둔다.
