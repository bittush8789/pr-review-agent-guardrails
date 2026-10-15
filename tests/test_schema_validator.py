"""Unit tests for schema validation guardrails."""

import json
import pytest
from app.guardrails.schema_validator import SchemaValidator
from app.schemas.review_finding import SeverityLevel, ReviewCategory


@pytest.fixture
def validator():
    return SchemaValidator()


def test_valid_json_payload_parsing(validator):
    payload = {
        "findings": [
            {
                "file": "src/auth.py",
                "line": 42,
                "severity": "high",
                "category": "security",
                "title": "Missing authorization check",
                "suggestion": "Validate caller permissions before returning the resource.",
                "confidence": 0.94,
            }
        ]
    }
    findings = validator.validate_raw_response(payload)
    assert len(findings) == 1
    f = findings[0]
    assert f.file == "src/auth.py"
    assert f.line == 42
    assert f.severity == SeverityLevel.HIGH
    assert f.category == ReviewCategory.SECURITY
    assert f.title == "Missing authorization check"
    assert f.confidence == 0.94


def test_markdown_code_fence_unwrapping(validator):
    raw_str = (
        "```json\n"
        '{\n  "findings": [\n'
        '    {\n      "file": "app/db.py",\n      "line": 10,\n'
        '      "severity": "critical",\n      "category": "correctness",\n'
        '      "title": "SQL Injection",\n'
        '      "suggestion": "Use parameterized queries.",\n'
        '      "confidence": 0.99\n    }\n'
        "  ]\n}\n"
        "```"
    )
    findings = validator.validate_raw_response(raw_str)
    assert len(findings) == 1
    assert findings[0].file == "app/db.py"


def test_invalid_severity_rejected(validator):
    payload = {
        "findings": [
            {
                "file": "src/app.py",
                "line": 5,
                "severity": "catastrophic",  # Invalid
                "category": "security",
                "title": "Bad severity",
                "suggestion": "Fix it.",
                "confidence": 0.9,
            }
        ]
    }
    findings = validator.validate_raw_response(payload)
    assert len(findings) == 0


def test_invalid_category_rejected(validator):
    payload = {
        "findings": [
            {
                "file": "src/app.py",
                "line": 5,
                "severity": "low",
                "category": "aesthetic_formatting",  # Invalid
                "title": "Bad category",
                "suggestion": "Fix it.",
                "confidence": 0.8,
            }
        ]
    }
    findings = validator.validate_raw_response(payload)
    assert len(findings) == 0


def test_out_of_range_confidence_rejected(validator):
    payload = {
        "findings": [
            {
                "file": "src/app.py",
                "line": 5,
                "severity": "medium",
                "category": "correctness",
                "title": "Out of range",
                "suggestion": "Fix it.",
                "confidence": 1.5,  # Exceeds 1.0
            }
        ]
    }
    findings = validator.validate_raw_response(payload)
    assert len(findings) == 0


def test_path_traversal_rejected(validator):
    payload = {
        "findings": [
            {
                "file": "../../etc/shadow",
                "line": 1,
                "severity": "critical",
                "category": "security",
                "title": "Path Traversal in AI finding",
                "suggestion": "Never allow path traversal.",
                "confidence": 0.95,
            },
            {
                "file": "/absolute/path/file.py",
                "line": 1,
                "severity": "critical",
                "category": "security",
                "title": "Absolute path",
                "suggestion": "Must be relative.",
                "confidence": 0.95,
            },
        ]
    }
    findings = validator.validate_raw_response(payload)
    assert len(findings) == 0


def test_missing_required_fields_rejected(validator):
    payload = {
        "findings": [
            {
                "file": "src/app.py",
                "line": 5,
                # missing severity, category, title, suggestion
                "confidence": 0.9,
            }
        ]
    }
    findings = validator.validate_raw_response(payload)
    assert len(findings) == 0


def test_suggested_code_in_schema_and_markdown(validator):
    payload = {
        "findings": [
            {
                "file": "terraform/s3.tf",
                "line": 10,
                "severity": "critical",
                "category": "infrastructure",
                "title": "Public S3 ACL",
                "suggestion": "Set bucket to private.",
                "confidence": 0.98,
                "suggested_code": '  acl = "private"',
            }
        ]
    }
    findings = validator.validate_raw_response(payload)
    assert len(findings) == 1
    f = findings[0]
    assert f.suggested_code == '  acl = "private"'
    markdown = f.format_markdown_comment()
    assert "```suggestion" in markdown
    assert 'acl = "private"' in markdown

