# Evaluation Methodology

## 1. Purpose and Philosophy

Automated review tools frequently suffer from two common failure modes:
1. **Alert Fatigue (Low Precision)**: Developers are flooded with trivial, speculative, or false-positive comments, causing them to ignore automated reviews entirely.
2. **Blind Spots (Low Recall)**: Dangerous vulnerabilities, hardcoded secrets, or subtle logic inversions pass undetected into production.

The evaluation methodology provides a rigorous, repeatable process to benchmark both the deterministic scanners and the Gemini AI reviewer against a curated dataset of representative Pull Requests.

---

## 2. Dataset Architecture

The benchmark dataset ([`evals/datasets/labelled_prs.json`](file:///d:/GitHub%20PR-review%20agent%20with%20guardrails/evals/datasets/labelled_prs.json)) includes eight diverse test scenarios:

1. **Clean Code Changes (`PR-001`)**: Tests true negative behavior. The reviewer should generate zero comments.
2. **Deterministic Hardcoded Secrets (`PR-002`)**: Verifies that regex and entropy checks identify credentials with 100% recall.
3. **Risky Infrastructure Changes (`PR-003`)**: Verifies detection of open security groups (`0.0.0.0/0`) and public S3 ACLs.
4. **Missing Unit Tests (`PR-004`)**: Tests AI detection of new, complex financial calculation logic lacking test coverage.
5. **Logic and Correctness Bugs (`PR-005`)**: Tests AI detection of logic inversions (`<` vs `>`) in token validation.
6. **Adversarial Prompt Injections (`PR-006`)**: Verifies that injection attempts in code comments fail to force approvals or break delimiters.
7. **False-Positive Traps (`PR-007`)**: Verifies that placeholder strings (`replace_with_your_api_key`) and template variables are NOT flagged.
8. **Diff Edge Cases (`PR-008`)**: Tests handling of binary assets and zero-length diffs without errors.

---

## 3. Mathematical Metric Definitions

### 3.1 Precision
$$\text{Precision} = \frac{\text{True Positives}}{\text{True Positives} + \text{False Positives}}$$
- Measures the accuracy of published comments.
- **Target Threshold**: $\ge 85\%$. High precision prevents reviewer fatigue.

### 3.2 Recall
$$\text{Recall} = \frac{\text{True Positives}}{\text{True Positives} + \text{False Negatives}}$$
- Measures coverage of expected issues.
- **Target Threshold**: $\ge 90\%$ for security and infrastructure risks.

### 3.3 F1 Score
$$\text{F1} = 2 \times \frac{\text{Precision} \times \text{Recall}}{\text{Precision} + \text{Recall}}$$
- Harmonic balance between precision and recall.

### 3.4 False Positive Rate (FPR)
$$\text{FPR} = \frac{\text{False Positives}}{\text{False Positives} + \text{True Negatives}}$$
- Rate at which clean or safe changes are erroneously flagged.
- **Target Threshold**: $\le 10\%$.

### 3.5 Invalid Comment Rate
$$\text{Invalid Comment Rate} = \frac{\text{Comments on Unchanged Lines or Non-Existent Files}}{\text{Total Published Comments}}$$
- Measures guardrail compliance.
- **Target Threshold**: **Strictly 0.00%**. Any comment on an unchanged line is a guardrail failure.

---

## 4. True Positive Matching Criteria

When comparing predicted findings to ground-truth labels, a predicted finding is scored as a **True Positive** if:

1. **Exact File Match**: The predicted `file` must match the ground-truth file path string.
2. **Line Window Tolerance**: The predicted `line` must fall within $\pm 2$ lines of the ground-truth line. This accounts for minor formatting differences between hunk headers and implementation lines.
3. **Category Match**: The predicted category (`security`, `infrastructure`, `correctness`, `testing`, `maintainability`) must match the ground-truth category.
4. **Severity Match**: The predicted severity must match the ground-truth severity level.
5. **Title Keyword**: If specified in the dataset sample, the predicted `title` must contain the designated keyword (case-insensitive).

---

## 5. Benchmarking Separation: Deterministic vs. AI

The evaluation runner ([`evals/evaluator.py`](file:///d:/GitHub%20PR-review%20agent%20with%20guardrails/evals/evaluator.py)) reports deterministic rule performance separately from combined (deterministic + AI) performance:

- **Deterministic Evaluation**: Runs without requiring external network access or API keys. Tests pure regex and AST-style parsing speed and accuracy.
- **Combined Evaluation**: Tests the full pipeline including Gemini model inferences, schema validation, and line filtering.

---

## 6. Tuning and Optimization Guidelines

- If **Precision is low**: Increase `CONFIDENCE_THRESHOLD` (e.g., from `0.70` to `0.85`), refine regex patterns to exclude common test variable names, or tune system instructions to discourage speculative feedback.
- If **Recall is low**: Lower `CONFIDENCE_THRESHOLD`, expand secret regex definitions, or adjust line window tolerances.
- If **Comment limits truncate critical findings**: Increase `MAX_COMMENTS_PER_PR` or refine the sorting algorithm in `CommentLimiter`.
