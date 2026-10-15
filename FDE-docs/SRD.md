# Software & Security Requirements Document (SRD)
## Project: GitHub PR-Review Agent with Guardrails
**Document Version:** 1.0.0  
**Target Audience:** Forward Deployed Engineers (FDEs), Application Security Engineers, Compliance Officers, QA Automation Teams  

---

## 1. Functional Requirements (FR)

| Req ID | Requirement Title | Detailed Specification | Acceptance Criteria |
| :--- | :--- | :--- | :--- |
| **FR-01** | **Deterministic Secret Scanning** | Must detect AWS keys, GitHub tokens, Slack tokens, private keys, and high-entropy passwords on all added diff lines. | 100% detection rate on synthetic secret test suite; 0 leaks unflagged. |
| **FR-02** | **Secret Redaction** | Must replace detected secrets in diffs, prompts, logs, and comments with `[REDACTED_...]` masks. | Zero raw credentials logged or sent in outbound network payloads. |
| **FR-03** | **Terraform IaC Risk Analysis** | Must flag security group `0.0.0.0/0` ingress, public S3 ACLs, disabled public access blocks, disabled volume encryption, and wildcard IAM policies. | Flagged findings must include actionable remediation and category `infrastructure`. |
| **FR-04** | **Dependency & CVE Scanning** | Must scan package manifests (`requirements.txt`, `package.json`, `Pipfile`, `go.mod`) for published CVEs and wildcard/unpinned versions. | Must flag known CVEs (e.g. `requests < 2.31.0`) with category `security`. |
| **FR-05** | **Google Gemini AI Code Review** | Must invoke Google Gemini with structured JSON output enforcing `REVIEW_FINDINGS_JSON_SCHEMA`. | Schema validation passes with 0 malformed responses. |
| **FR-06** | **Diff Line Containment Guardrail** | Must cross-reference finding target lines against `valid_changed_lines`. | Rejects 100% of comments targeting unchanged, context, or deleted lines. |
| **FR-07** | **Comment Limiting & Prioritization** | Must cap published comments at `MAX_COMMENTS_PER_PR` (default: 5), prioritizing by severity rank and confidence score. | Exactly $\le 5$ comments published even if 20+ issues are detected. |
| **FR-08** | **Overlapping Finding Deduplication** | Must merge findings on the same file within $\pm 2$ lines, favoring deterministic rules over AI suggestions. | No duplicate or contradictory comments on the same code block. |
| **FR-09** | **One-Click GitHub Suggested Changes** | Findings with replacement code must format comments with native GitHub ```` ```suggestion ```` blocks. | Renders as an interactive diff widget on GitHub PRs. |
| **FR-10** | **PR Complexity & Sizing** | Must categorize PR size into `XS`, `S`, `M`, `L`, `XL` and estimate human review turnaround time based on changed lines and files. | Calculated complexity badge displayed in executive summary. |
| **FR-11** | **Executive Summary & Risk Scoring** | Must post a conversation-level discussion comment with an overall security risk gauge (0–100) and component breakdown. | Summary comment posted on PR thread unless `POST_SUMMARY_COMMENT=false`. |
| **FR-12** | **Stale PR Detection** | Must verify the PR head commit SHA immediately prior to publishing comments. | If a new commit was pushed during analysis, aborts with `StalePullRequestError`. |

---

## 2. Software Security Requirements (SSR)

The agent adheres strictly to the **OWASP Top 10 for Large Language Models (LLM)**:

| Security ID | OWASP LLM Vulnerability | Security Requirement & Enforcement Mechanism |
| :--- | :--- | :--- |
| **SSR-01** | **LLM01: Prompt Injection** | Diffs are isolated using unforgeable boundary delimiters (`===BEGIN_UNTRUSTED_DIFF_PAYLOAD===`). Delimiter occurrences inside diffs are escaped. Structured JSON schema forbids command execution. |
| **SSR-02** | **LLM02: Insecure Output Handling**| Model output is never executed in shell or eval environments. Responses are validated against `jsonschema` Draft 2020-12 and sanitized for HTML/script tags before posting. |
| **SSR-03** | **LLM06: Sensitive Information Disclosure** | Raw API keys and tokens are redacted locally *before* code is transmitted to external LLM APIs or written to application logs. |
| **SSR-04** | **LLM09: Overreliance & Hallucination** | The Changed-Line Validator strictly enforces that AI comments can only appear on lines actively modified in the PR. Comments on non-existent lines are dropped. |
| **SSR-05** | **Principle of Least Privilege** | GitHub Actions workflow grants only `contents: read` and `pull-requests: write`. No `contents: write`, `admin: write`, or merge capabilities exist. |
| **SSR-06** | **Container Security Hardening** | Dockerfile executes under dedicated unprivileged non-root user `appuser` (`UID: 10001`, `GID: 10001`). File system permissions are read-only where applicable. |
| **SSR-07** | **Log Scrubbing** | `SensitiveDataFilter` masks all environment secrets (`GITHUB_TOKEN`, `GEMINI_API_KEY`, `LANGCHAIN_API_KEY`) from logs and exception stack traces. |
| **SSR-08** | **Fork PR Isolation** | GitHub Actions workflow uses standard `pull_request` event, preventing fork PRs from accessing sensitive organization secrets. |

---

## 3. Non-Functional Requirements (NFR)

| Req ID | Category | Metric / Constraint | Verification Method |
| :--- | :--- | :--- | :--- |
| **NFR-01** | **Reliability & Resilience** | Partial failure tolerance: If Gemini fails/times out, deterministic checks still publish. | Unit tests in `test_review_orchestrator.py` simulate API failure. |
| **NFR-02** | **Deterministic Scan Speed** | Secret, IaC, and dependency checks complete in $< 200\text{ ms}$. | Benchmarked in `evals/evaluator.py`. |
| **NFR-03** | **End-to-End Latency** | Full PR review cycle completes in $< 15\text{ seconds}$ on standard PRs. | Verified via LangSmith tracing and workflow logs. |
| **NFR-04** | **Offline Testability** | 100% of unit and integration tests execute offline without real API tokens or network access. | `pytest` runs using mocked fixtures (`respx`, `pytest-mock`). |
| **NFR-05** | **Test Coverage** | Code coverage across core packages $\ge 90\%$. | Enforced via `pytest --cov=app`. |
| **NFR-06** | **Portability** | Operates identically in GitHub Actions, Docker, Kubernetes, or local CLI. | Verified across Windows (PowerShell) and Linux (Docker). |

---

## 4. Requirements Traceability Matrix (RTM)

| Requirement ID | Implementation Module | Automated Test File | Status |
| :--- | :--- | :--- | :---: |
| **FR-01, FR-02** | `app/rules/secret_scanner.py` | `tests/test_secret_scanner.py` | ✅ Verified |
| **FR-03** | `app/rules/terraform_risk.py` | `tests/test_terraform_risk.py` | ✅ Verified |
| **FR-04** | `app/rules/dependency_scanner.py` | `tests/test_dependency_scanner.py` | ✅ Verified |
| **FR-05, SSR-02**| `app/guardrails/schema_validator.py` | `tests/test_schema_validator.py` | ✅ Verified |
| **FR-06, SSR-04**| `app/guardrails/diff_line_validator.py` | `tests/test_diff_line_validator.py`| ✅ Verified |
| **FR-07** | `app/guardrails/comment_limiter.py` | `tests/test_comment_limiter.py` | ✅ Verified |
| **FR-08** | `app/guardrails/duplicate_filter.py` | `tests/test_review_orchestrator.py` | ✅ Verified |
| **FR-09** | `app/schemas/review_finding.py` | `tests/test_schema_validator.py` | ✅ Verified |
| **FR-10, FR-11**| `app/review/summary_builder.py` | `tests/test_summary_builder.py` | ✅ Verified |
| **FR-12** | `app/github/review_publisher.py` | `tests/test_review_orchestrator.py` | ✅ Verified |
| **SSR-01** | `app/guardrails/injection_defense.py` | `tests/test_injection_defense.py` | ✅ Verified |
| **SSR-05** | `.github/workflows/pr-review.yml` | `tests/test_github_permissions.py` | ✅ Verified |
| **SSR-06** | `Dockerfile` | Static analysis / Docker build | ✅ Verified |
| **SSR-07** | `app/config/settings.py` | `tests/test_langsmith_tracing.py` | ✅ Verified |
