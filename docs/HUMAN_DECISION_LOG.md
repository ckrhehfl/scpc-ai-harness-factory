# Human Decision Log

사람의 판단이 필요한 항목을 기록한다. 추후 본선 발표 또는 코드 검증 시 “왜 그렇게 했는지”를 설명하기 위한 근거로 사용한다.

대회 시작 후 확정된 결정은 contest 폴더의 `contest_overrides.yaml`에도 함께 기록한다. Factory는 이 파일을 읽어
`ContestSpec`, `GapReport`, `HarnessBlueprint`에 override 적용 근거를 남긴다.

## Decision 001

### 상황

외부 LLM API 사용 가능 여부가 아직 불명확하다.

### 선택지

A. 외부 API solver를 기본으로 넣는다.  
B. 로컬/규칙 기반 solver만 사용한다.  
C. 외부 API solver는 optional adapter로만 만들고 기본 config에서는 비활성화한다.

### 결정

C

### 이유

대회 규칙 공개 전에는 외부 API 사용 가능 여부가 확정되지 않았으므로, 최종 하네스 기본 실행 경로에 포함하지 않는다.

### 영향

- `templates/base_harness/src/solver.py`는 규칙 기반 baseline으로 유지한다.
- 외부 API solver는 추후 규칙 확인 후 별도 추가한다.

---

## Decision 002

### 상황

GitHub PR 자동화/리뷰픽스 자동화를 이 프로젝트에 포함할지 여부.

### 선택지

A. 포함한다.  
B. 포함하지 않고 GitHub는 저장소/백업으로만 사용한다.

### 결정

B

### 이유

현재 목표는 대회 대응용 Meta-Harness Factory MVP이다. GitHub 자동화는 외부 시스템 의존도가 높고 범위를 폭발시킨다.

### 영향

- PR 자동화, 자동 리뷰픽스, 자동 머지는 P0 범위에서 제외한다.
- 리뷰는 실행 확인, pytest, 문서-코드 일치성 확인으로 대체한다.
