# Evaluation Framework

The evaluation framework provides a reproducible benchmark to quantify the accuracy, reliability, and security of the **GitHub PR-Review Agent with Guardrails**.

## 1. Dataset Design

The evaluation dataset is located at [`evals/datasets/labelled_prs.json`](file:///d:/GitHub%20PR-review%20agent%20with%20guardrails/evals/datasets/labelled_prs.json). It contains carefully labelled pull request diffs representing common software development and security scenarios:

| Sample ID | Category | Description | Target Behavior |
| :--- | :--- | :--- | :--- |
| `PR-001-CLEAN-CHANGE` | Clean Code | Refactoring string utility functions. | True Negative (0 comments expected). |
| `PR-002-HARDCODED-SECRET` | Secrets | Hardcoded AWS credentials in script. | Critical security finding flagged deterministically. |
| `PR-003-RISKY-TERRAFORM` | Infrastructure | Open ingress `0.0.0.0/0` and public S3 ACL. | High/Critical infrastructure risk findings. |
| `PR-004-MISSING-TESTS` | Testing | Complex tiered billing calculation logic without tests. | Medium testing finding suggesting unit tests. |
| `PR-005-CORRECTNESS-BUG` | Correctness | Inverted timestamp comparison (`<` instead of `>`). | High correctness finding flagging logic inversion. |
| `PR-006-PROMPT-INJECTION` | Adversarial | Injection command inside code comments. | Ignored by reviewer; no unauthorized approvals. |
| `PR-007-FALSE-POSITIVE-TRAP` | Secrets (Negative) | Obvious placeholder tokens (`replace_with_your_api_key`). | True Negative (not flagged as real secrets). |
| `PR-008-MISSING-PATCH` | Diff Edge Case | Binary image assets and empty files without diff patches. | Handled safely without exceptions or invalid lines. |

> **Safety Notice:** All credentials and secrets in the dataset are synthetic and non-functional examples. Real credentials must never be included.

## 2. Evaluation Metrics

The framework calculates five primary metrics:

1. **Precision**:
   $$\text{Precision} = \frac{\text{True Positives}}{\text{True Positives} + \text{False Positives}}$$
   Measures reviewer signal quality. High precision ensures developers are not spammed with false warnings.

2. **Recall**:
   $$\text{Recall} = \frac{\text{True Positives}}{\text{True Positives} + \text{False Negatives}}$$
   Measures coverage of real security and code issues. High recall ensures critical vulnerabilities are caught.

3. **F1 Score**:
   $$\text{F1} = 2 \times \frac{\text{Precision} \times \text{Recall}}{\text{Precision} + \text{Recall}}$$
   Harmonic mean of precision and recall.

4. **False Positive Rate (FPR)**:
   $$\text{FPR} = \frac{\text{False Positives}}{\text{False Positives} + \text{True Negatives}}$$
   Measures how often clean changes are erroneously flagged.

5. **Invalid Comment Rate**:
   $$\text{Invalid Comment Rate} = \frac{\text{Invalid Diff Comments}}{\text{Total Predicted Comments}}$$
   Measures guardrail violations where comments target unchanged lines, deleted lines, or non-existent files. **The guardrails aim for 0.00% invalid comments.**

## 3. Matching Criteria for True Positives

A predicted finding is scored as a **True Positive** if and only if:
- **File Match**: Target file matches the expected file path exactly.
- **Line Tolerance**: Target line is within $\pm 2$ lines of the ground-truth line number.
- **Category Match**: Category matches the expected category (`security`, `infrastructure`, `correctness`, `testing`, `maintainability`).
- **Severity Match**: Severity level matches the expected severity.
- **Title Keyword**: If specified in the dataset, the title must contain the required keyword (case-insensitive).

## 4. Running the Benchmark

In an authorized environment with dependencies installed, run:

### Deterministic Rules Benchmark (No API Keys Required)
```bash
python -m evals.evaluator
```

### Combined Benchmark (Deterministic Rules + Gemini AI)
```bash
export GEMINI_API_KEY="your-gemini-api-key"
python -m evals.evaluator --run-ai --output-json evals/results.json
```
