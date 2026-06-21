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

Important constraints:

- Do not assume that unknown rules are allowed.
- Do not add runtime LLM API calls.
- Do not optimize the solver in this step.
- Treat all suggestions as candidates only.
- The human must confirm and encode decisions in contest_overrides.yaml before the factory treats them as final.
