"""Executive summary and risk score generator for Pull Request discussions."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

from app.schemas.review_finding import ReviewFinding, SeverityLevel, ReviewCategory

logger = logging.getLogger("pr_review_agent.review.summary_builder")


@dataclass(frozen=True)
class PRRiskAssessment:
    """Calculated risk assessment score and badge for a PR."""

    level: str  # "CLEAN", "LOW", "MEDIUM", "HIGH", "CRITICAL"
    badge: str
    numeric_score: int  # 0 (completely safe) to 100 (critical danger)
    description: str


@dataclass(frozen=True)
class PRComplexityAssessment:
    """Calculated PR size and review effort complexity."""

    size_tag: str  # "XS", "S", "M", "L", "XL"
    label: str
    badge: str
    estimated_effort: str
    recommendation: str


class SummaryBuilder:
    """Builds structured executive summaries and risk scores for PR conversation threads."""

    @staticmethod
    def calculate_complexity(total_files: int, total_changed_lines: int) -> PRComplexityAssessment:
        """Categorize PR size and estimate human review complexity."""
        if total_changed_lines <= 20 and total_files <= 2:
            return PRComplexityAssessment(
                size_tag="XS",
                label="Extra Small",
                badge="🟢 **XS (Extra Small)**",
                estimated_effort="~5 minutes",
                recommendation="Low cognitive load. Fast turnaround expected.",
            )
        elif total_changed_lines <= 80 and total_files <= 5:
            return PRComplexityAssessment(
                size_tag="S",
                label="Small",
                badge="🟢 **S (Small)**",
                estimated_effort="~15 minutes",
                recommendation="Ideal PR size for quick, focused peer review.",
            )
        elif total_changed_lines <= 250 and total_files <= 12:
            return PRComplexityAssessment(
                size_tag="M",
                label="Medium",
                badge="🟡 **M (Medium)**",
                estimated_effort="~30-45 minutes",
                recommendation="Moderate scope. Check test coverage and component boundaries.",
            )
        elif total_changed_lines <= 600 and total_files <= 25:
            return PRComplexityAssessment(
                size_tag="L",
                label="Large",
                badge="🟠 **L (Large)**",
                estimated_effort="~1-2 hours",
                recommendation="Substantial PR. Reviewers should verify architecture and integration points.",
            )
        else:
            return PRComplexityAssessment(
                size_tag="XL",
                label="Extra Large",
                badge="🔴 **XL (Extra Large)**",
                estimated_effort="~2+ hours",
                recommendation="High risk of review fatigue and overlooked bugs. Strongly recommend splitting into smaller, independent PRs.",
            )

    @staticmethod
    def summarize_components(file_list: Sequence[str]) -> list[str]:
        """Classify and summarize changed repository areas."""
        categories: set[str] = set()
        for f in file_list:
            lower = f.lower()
            if "test" in lower or lower.startswith("tests/"):
                categories.add("🧪 Tests & QA")
            elif lower.endswith((".tf", ".tfvars", ".tf.json")):
                categories.add("☁️ Infrastructure / Terraform")
            elif lower.endswith(("requirements.txt", "package.json", "pipfile", "go.mod", "pyproject.toml")):
                categories.add("📦 Dependencies & Packages")
            elif "docker" in lower or ".github" in lower:
                categories.add("⚙️ CI/CD & Containers")
            elif lower.endswith((".py", ".js", ".ts", ".go", ".java", ".rs")):
                categories.add("💻 Core Application Logic")
            elif lower.endswith((".md", ".rst", ".txt")):
                categories.add("📄 Documentation")
            else:
                categories.add("📁 Project Assets / Config")
        return sorted(categories)

    @staticmethod
    def calculate_risk(findings: Sequence[ReviewFinding]) -> PRRiskAssessment:
        """Calculate the overall security and quality risk score based on findings.

        Scoring formula:
        - Critical finding: +40 points each (capped at 100)
        - High finding: +25 points each
        - Medium finding: +10 points each
        - Low finding: +3 points each
        """
        if not findings:
            return PRRiskAssessment(
                level="CLEAN",
                badge="🟢 **PASS: CLEAN**",
                numeric_score=0,
                description="No hardcoded secrets, infrastructure risks, or critical vulnerabilities detected.",
            )

        score = 0
        has_critical = False
        has_high = False

        for f in findings:
            if f.severity == SeverityLevel.CRITICAL:
                score += 40
                has_critical = True
            elif f.severity == SeverityLevel.HIGH:
                score += 25
                has_high = True
            elif f.severity == SeverityLevel.MEDIUM:
                score += 10
            elif f.severity == SeverityLevel.LOW:
                score += 3

        score = min(100, score)

        if has_critical or score >= 75:
            return PRRiskAssessment(
                level="CRITICAL",
                badge="🚨 **CRITICAL RISK**",
                numeric_score=score,
                description="Critical security vulnerabilities or hardcoded credentials detected. Requires immediate remediation before merging.",
            )
        elif has_high or score >= 45:
            return PRRiskAssessment(
                level="HIGH",
                badge="⚠️ **HIGH RISK**",
                numeric_score=score,
                description="High-severity issues identified. Detailed review and remediation recommended.",
            )
        elif score >= 20:
            return PRRiskAssessment(
                level="MEDIUM",
                badge="🟡 **MEDIUM RISK**",
                numeric_score=score,
                description="Moderate correctness or testing gaps identified. Verify suggestions before merging.",
            )
        else:
            return PRRiskAssessment(
                level="LOW",
                badge="ℹ️ **LOW RISK**",
                numeric_score=score,
                description="Minor maintainability or non-blocking observations noted.",
            )

    def build_summary_markdown(
        self,
        pr_number: int,
        repo: str,
        head_sha: str,
        model_name: str,
        findings: Sequence[ReviewFinding],
        total_files: int,
        total_changed_lines: int,
        gemini_status: str = "Active",
        file_list: Optional[Sequence[str]] = None,
    ) -> str:
        """Construct a clean, professional GitHub PR summary comment in Markdown."""
        risk = self.calculate_risk(findings)
        complexity = self.calculate_complexity(total_files, total_changed_lines)

        # Count findings by severity
        crit_count = sum(1 for f in findings if f.severity == SeverityLevel.CRITICAL)
        high_count = sum(1 for f in findings if f.severity == SeverityLevel.HIGH)
        med_count = sum(1 for f in findings if f.severity == SeverityLevel.MEDIUM)
        low_count = sum(1 for f in findings if f.severity == SeverityLevel.LOW)

        lines: list[str] = [
            f"## 🤖 GitHub PR-Review Agent: Executive Summary",
            f"",
            f"### Security & Quality Assessment: {risk.badge}",
            f"> **Risk Score:** `{risk.numeric_score}/100` | {risk.description}",
            f"",
            f"| Metric | Inspection Details |",
            f"| :--- | :--- |",
            f"| **Target PR** | `#{pr_number}` on `{repo}` |",
            f"| **Commit Revision** | `{head_sha[:8]}` |",
            f"| **PR Complexity** | {complexity.badge} ({complexity.estimated_effort}) |",
            f"| **Files & Lines Inspected** | `{total_files}` files (`{total_changed_lines}` modified lines) |",
            f"| **AI Review Engine** | Google Gemini (`{model_name}`) — Status: `{gemini_status}` |",
            f"| **Deterministic Security** | Secret Scanner, Terraform Analyzer, & Dependency Scanner (`Active`) |",
            f"| **Findings Published** | **{len(findings)}** (🚨 `{crit_count}` Critical, ⚠️ `{high_count}` High, 🔍 `{med_count}` Medium, ℹ️ `{low_count}` Low) |",
            f"",
        ]

        # Add High-Level Component Summary
        if file_list:
            components = self.summarize_components(file_list)
            if components:
                lines.extend([
                    f"### 📝 High-Level Change Summary",
                    f"- **Estimated Review Effort:** `{complexity.estimated_effort}` — {complexity.recommendation}",
                    f"- **Impacted Domains:** {', '.join(components)}",
                    f"",
                ])

        if not findings:
            lines.extend([
                f"### ✅ Verification Checklist",
                f"- [x] **No Secrets Committed**: Validated against AWS, GitHub, Slack, Private Keys, and API credentials.",
                f"- [x] **IaC Security**: Verified Terraform configs have no open `0.0.0.0/0` ingress or public buckets.",
                f"- [x] **Dependency Safety**: Checked package manifests for known CVEs and wildcard versions.",
                f"- [x] **Code Quality**: No obvious logic regressions or missing tests detected.",
                f"- [x] **Guardrails**: All boundary and changed-line filters passed with 0 violations.",
                f"",
                f"---",
                f"*Automated first-pass review by GitHub PR-Review Agent with Guardrails.*",
            ])
            return "\n".join(lines)

        # Table of findings
        lines.extend([
            f"### 📋 Key Findings Overview",
            f"",
            f"| Severity | Category | File & Line | Summary |",
            f"| :--- | :--- | :--- | :--- |",
        ])

        severity_icons = {
            SeverityLevel.CRITICAL: "🚨 Critical",
            SeverityLevel.HIGH: "⚠️ High",
            SeverityLevel.MEDIUM: "🔍 Medium",
            SeverityLevel.LOW: "ℹ️ Low",
        }

        for f in findings:
            sev_badge = severity_icons.get(f.severity, f.severity.value)
            clean_title = f.title.replace("|", "/")
            lines.append(f"| {sev_badge} | `{f.category.value}` | `{f.file}:{f.line}` | {clean_title} |")

        lines.extend([
            f"",
            f"> 💡 **Note:** Detailed inline remediation guidance has been posted directly on the changed lines above.",
            f"",
            f"### 🛡️ Guardrails Audit Summary",
            f"- **Secret Redaction**: Enforced (all detected credentials scrubbed from logs and prompts).",
            f"- **Diff Containment**: Enforced (100% of comments target verified modified lines).",
            f"- **Prompt Injection Containment**: Active (untrusted diff isolation delimiters enforced).",
            f"",
            f"---",
            f"*Automated first-pass review by GitHub PR-Review Agent with Guardrails. Please review and address flagged comments before merging.*",
        ])

        return "\n".join(lines)
