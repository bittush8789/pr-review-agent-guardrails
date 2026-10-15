"""Unit tests for PR Executive Summary and Risk Score generation."""

import pytest
from app.review.summary_builder import SummaryBuilder
from app.schemas.review_finding import ReviewFinding, SeverityLevel, ReviewCategory


@pytest.fixture
def builder():
    return SummaryBuilder()


def test_calculate_risk_clean_pr(builder):
    assessment = builder.calculate_risk([])
    assert assessment.level == "CLEAN"
    assert assessment.numeric_score == 0
    assert "🟢" in assessment.badge
    assert "No hardcoded secrets" in assessment.description


def test_calculate_risk_critical_finding(builder):
    finding = ReviewFinding(
        file="src/auth.py",
        line=10,
        severity=SeverityLevel.CRITICAL,
        category=ReviewCategory.SECURITY,
        title="Hardcoded AWS Secret",
        suggestion="Remove secret immediately.",
        confidence=0.99,
    )
    assessment = builder.calculate_risk([finding])
    assert assessment.level == "CRITICAL"
    assert assessment.numeric_score >= 40
    assert "🚨" in assessment.badge


def test_calculate_risk_high_finding(builder):
    finding = ReviewFinding(
        file="infra/main.tf",
        line=22,
        severity=SeverityLevel.HIGH,
        category=ReviewCategory.INFRASTRUCTURE,
        title="Open Ingress 0.0.0.0/0",
        suggestion="Restrict CIDR block.",
        confidence=0.92,
    )
    assessment = builder.calculate_risk([finding])
    assert assessment.level in {"HIGH", "CRITICAL"}
    assert "⚠️" in assessment.badge or "🚨" in assessment.badge


def test_build_summary_markdown_clean(builder):
    markdown = builder.build_summary_markdown(
        pr_number=42,
        repo="owner/repo",
        head_sha="abcdef1234567890",
        model_name="gemini-3.8-flash",
        findings=[],
        total_files=3,
        total_changed_lines=50,
    )
    assert "## 🤖 GitHub PR-Review Agent: Executive Summary" in markdown
    assert "🟢 **PASS: CLEAN**" in markdown
    assert "Verification Checklist" in markdown
    assert "No Secrets Committed" in markdown


def test_build_summary_markdown_with_findings(builder):
    findings = [
        ReviewFinding(
            file="app/db.py",
            line=15,
            severity=SeverityLevel.HIGH,
            category=ReviewCategory.CORRECTNESS,
            title="SQL Injection Risk",
            suggestion="Use parameter binding.",
            confidence=0.95,
        )
    ]
    markdown = builder.build_summary_markdown(
        pr_number=42,
        repo="owner/repo",
        head_sha="abcdef1234567890",
        model_name="gemini-3.8-flash",
        findings=findings,
        total_files=1,
        total_changed_lines=10,
    )
    assert "Key Findings Overview" in markdown
    assert "app/db.py:15" in markdown
    assert "SQL Injection Risk" in markdown
    assert "Guardrails Audit Summary" in markdown
