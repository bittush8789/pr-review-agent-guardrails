"""Unit tests for changed-line validation guardrail."""

import pytest
from app.github.diff_parser import ParsedDiff
from app.guardrails.diff_line_validator import DiffLineValidator
from app.schemas.review_finding import ReviewFinding, SeverityLevel, ReviewCategory


@pytest.fixture
def validator():
    return DiffLineValidator()


@pytest.fixture
def parsed_diff():
    diff = ParsedDiff()
    # auth.py modified lines 10, 11, 12
    diff.valid_changed_lines["src/auth.py"] = {10, 11, 12}
    # config.py has no valid right-side lines (e.g. deleted or unchanged)
    diff.valid_changed_lines["src/config.py"] = set()
    return diff


def test_changed_line_accepted(validator, parsed_diff):
    finding = ReviewFinding(
        file="src/auth.py",
        line=11,
        severity=SeverityLevel.HIGH,
        category=ReviewCategory.SECURITY,
        title="Valid modified line",
        suggestion="Fix issue.",
        confidence=0.9,
    )
    valid, rejected = validator.validate_findings([finding], parsed_diff)
    assert len(valid) == 1
    assert len(rejected) == 0


def test_unchanged_line_rejected(validator, parsed_diff):
    finding = ReviewFinding(
        file="src/auth.py",
        line=50,  # Line 50 is not in {10, 11, 12}
        severity=SeverityLevel.HIGH,
        category=ReviewCategory.SECURITY,
        title="Unchanged line target",
        suggestion="Fix issue.",
        confidence=0.9,
    )
    valid, rejected = validator.validate_findings([finding], parsed_diff)
    assert len(valid) == 0
    assert len(rejected) == 1
    assert rejected[0].line == 50


def test_unknown_file_rejected(validator, parsed_diff):
    finding = ReviewFinding(
        file="src/unknown_unrelated_file.py",
        line=1,
        severity=SeverityLevel.CRITICAL,
        category=ReviewCategory.CORRECTNESS,
        title="File not in PR",
        suggestion="Fix issue.",
        confidence=0.95,
    )
    valid, rejected = validator.validate_findings([finding], parsed_diff)
    assert len(valid) == 0
    assert len(rejected) == 1


def test_file_with_no_usable_lines_rejected(validator, parsed_diff):
    finding = ReviewFinding(
        file="src/config.py",
        line=1,
        severity=SeverityLevel.MEDIUM,
        category=ReviewCategory.MAINTAINABILITY,
        title="Deleted file target",
        suggestion="Fix issue.",
        confidence=0.8,
    )
    valid, rejected = validator.validate_findings([finding], parsed_diff)
    assert len(valid) == 0
    assert len(rejected) == 1
