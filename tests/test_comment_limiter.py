"""Unit tests for comment limiter and priority ordering."""

import pytest
from app.guardrails.comment_limiter import CommentLimiter
from app.schemas.review_finding import ReviewFinding, SeverityLevel, ReviewCategory


def make_finding(file: str, line: int, severity: SeverityLevel, confidence: float, title: str) -> ReviewFinding:
    return ReviewFinding(
        file=file,
        line=line,
        severity=severity,
        category=ReviewCategory.CORRECTNESS,
        title=title,
        suggestion="Remediation suggestion.",
        confidence=confidence,
    )


def test_comment_limiter_caps_count():
    limiter = CommentLimiter(max_comments=3, min_confidence=0.50)
    findings = [
        make_finding("a.py", 1, SeverityLevel.LOW, 0.9, "Low 1"),
        make_finding("a.py", 2, SeverityLevel.MEDIUM, 0.9, "Med 1"),
        make_finding("a.py", 3, SeverityLevel.HIGH, 0.9, "High 1"),
        make_finding("a.py", 4, SeverityLevel.CRITICAL, 0.95, "Crit 1"),
        make_finding("a.py", 5, SeverityLevel.HIGH, 0.85, "High 2"),
    ]
    limited = limiter.limit_findings(findings)
    assert len(limited) == 3
    # Top 3 should be: Crit 1 (critical), High 1 (high, 0.9), High 2 (high, 0.85)
    assert limited[0].title == "Crit 1"
    assert limited[1].title == "High 1"
    assert limited[2].title == "High 2"


def test_confidence_threshold_filtering():
    limiter = CommentLimiter(max_comments=5, min_confidence=0.75)
    findings = [
        make_finding("b.py", 10, SeverityLevel.HIGH, 0.90, "Confident High"),
        make_finding("b.py", 20, SeverityLevel.CRITICAL, 0.60, "Low Confidence Crit"),
        make_finding("b.py", 30, SeverityLevel.MEDIUM, 0.70, "Low Confidence Med"),
    ]
    limited = limiter.limit_findings(findings)
    assert len(limited) == 1
    assert limited[0].title == "Confident High"


def test_empty_findings_handled_gracefully():
    limiter = CommentLimiter(max_comments=5)
    assert limiter.limit_findings([]) == []
