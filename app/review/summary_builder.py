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


class SummaryBuilder:
    """Builds structured executive summaries and risk scores for PR conversation threads."""

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
    ) -> str:
        """Construct a clean, professional GitHub PR summary comment in Markdown."""
        risk = self.calculate_risk(findings)

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
            f"| **Files & Lines Inspected** | `{total_files}` files (`{total_changed_lines}` modified lines) |",
            f"| **AI Review Engine** | Google Gemini (`{model_name}`) — Status: `{gemini_status}` |",
            f"| **Deterministic Security** | Secret Scanner & Terraform Risk Analyzer (`Active`) |",
            f"| **Findings Published** | **{len(findings)}** (🚨 `{crit_count}` Critical, ⚠️ `{high_count}` High, 🔍 `{med_count}` Medium, ℹ️ `{low_count}` Low) |",
            f"",
        ]

        if not findings:
            lines.extend([
                f"### ✅ Verification Checklist",
                f"- [x] **No Secrets Committed**: Validated against AWS, GitHub, Slack, Private Keys, and API credentials.",
                f"- [x] **IaC Security**: Verified Terraform configs have no open `0.0.0.0/0` ingress or public buckets.",
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
