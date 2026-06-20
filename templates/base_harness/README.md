# Base Harness Template

이 템플릿은 factory가 `generated/final_harness`로 복사하는 최소 실행 하네스입니다.

```text
run.py
→ src/loader.py
→ src/solver.py
→ src/verifier.py
→ src/submitter.py
→ outputs/submission.csv
```

현재 solver는 모든 답을 `1`로 내는 baseline입니다. 실제 대회 시작 후 문제 유형에 맞게 `src/solver.py`를 교체하거나 확장합니다.
