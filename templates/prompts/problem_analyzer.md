# AI Problem Analyzer Prompt

You are analyzing an SCPC AI Challenge contest folder for Meta-Harness Factory v0.6.
Do not produce a final contest submission. Do not write solver code. Your job is to propose design candidates that a human will review.

Contest path: `{{CONTEST_PATH}}`

# Source Documents

{{CONTEST_DOCUMENTS}}

# Input Scan Report

{{INPUT_SCAN_REPORT}}

# CSV Preview

{{CSV_PREVIEWS}}

# Current Factory Artifacts

{{CURRENT_ARTIFACTS_SUMMARY}}

# Required Output

Return a structured analysis with these sections:

1. Problem type candidates
2. Input structure interpretation
3. Output structure interpretation
4. Evaluation metric candidates
5. Rule-risk analysis
6. Candidate judgment for API / external data / internet / pretrained model usage
7. Required harness modules
8. Solver candidates, keeping the current baseline path intact
9. Decisions a human must confirm
10. Candidate ContestSpec updates
11. Candidate HarnessBlueprint updates
12. Code Agent Task Plan

At the very end of your response, include this exact heading followed by one JSON fenced code block:

## Machine-readable Analysis Payload

```json
{
  "problem_type_candidates": [
    {
      "value": "classification",
      "confidence": "high",
      "evidence": ["train.csv에 label 컬럼이 존재한다."]
    }
  ],
  "input_structure": {
    "summary": "입력 구조 설명",
    "files": ["train.csv", "test.csv"]
  },
  "output_structure": {
    "summary": "출력 구조 설명",
    "required_columns": ["id", "label"]
  },
  "evaluation_metric_candidates": [
    {
      "value": "accuracy",
      "confidence": "high",
      "evidence": ["evaluation.md에 accuracy라고 명시되어 있다."]
    }
  ],
  "rule_risks": [
    {
      "item": "external_api",
      "risk": "final runtime에서 외부 API 금지",
      "evidence": "rules.md"
    }
  ],
  "usage_candidates": {
    "external_api_allowed": {
      "value": false,
      "confidence": "high",
      "evidence": "rules.md"
    },
    "external_data_allowed": {
      "value": false,
      "confidence": "high",
      "evidence": "rules.md"
    },
    "internet_allowed": {
      "value": false,
      "confidence": "high",
      "evidence": "rules.md"
    },
    "pretrained_model_allowed": {
      "value": "unknown",
      "confidence": "low",
      "evidence": "명시되지 않음"
    }
  },
  "required_harness_modules": [
    {
      "name": "loader",
      "reason": "CSV 입력 로드"
    }
  ],
  "solver_candidates": [
    {
      "name": "local_baseline",
      "status": "candidate",
      "reason": "외부 API 없이 실행 가능"
    }
  ],
  "human_decisions": [
    {
      "item": "rules.pretrained_model_allowed",
      "reason": "공식 규칙 확인 필요"
    }
  ],
  "contest_spec_updates": [],
  "harness_blueprint_updates": [],
  "candidate_overrides": [
    {
      "path": "problem.task_type",
      "value": "classification",
      "confidence": "high",
      "evidence": "train/test/sample schema"
    }
  ],
  "code_agent_tasks": [
    {
      "title": "Add classification loader candidate",
      "priority": "P1",
      "files": ["templates/base_harness/src/loader.py"],
      "acceptance_criteria": [
        "기존 CSV loader 경로가 유지된다.",
        "테스트가 통과한다."
      ]
    }
  ]
}
```

Important constraints:

- Do not assume that unknown rules are allowed.
- Do not add runtime LLM API calls.
- Do not optimize the solver in this step.
- Treat all suggestions as candidates only.
- The human must confirm and encode decisions in contest_overrides.yaml before the factory treats them as final.
