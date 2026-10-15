"""Unit tests for deterministic dependency and supply chain vulnerability scanner."""

import pytest
from app.rules.dependency_scanner import DependencyScanner, parse_version_tuple
from app.schemas.review_finding import SeverityLevel, ReviewCategory


@pytest.fixture
def scanner():
    return DependencyScanner()


def test_parse_version_tuple():
    assert parse_version_tuple("2.31.0") == (2, 31, 0)
    assert parse_version_tuple("5.4") == (5, 4)
    assert parse_version_tuple("v4.17.21") == (4, 17, 21)


def test_vulnerable_requests_cve_detected(scanner):
    added_lines = {
        ("requirements.txt", 12): "requests==2.25.1",
    }
    findings = scanner.scan_diff_lines(added_lines)
    assert len(findings) == 1
    f = findings[0]
    assert f.file == "requirements.txt"
    assert f.line == 12
    assert f.rule_id == "CVE-2023-32681"
    assert f.severity == SeverityLevel.HIGH
    assert f.category == ReviewCategory.SECURITY
    assert "requests>=2.31.0" in f.suggested_code


def test_safe_requests_version_not_flagged(scanner):
    added_lines = {
        ("requirements.txt", 12): "requests>=2.31.0",
    }
    findings = scanner.scan_diff_lines(added_lines)
    assert len(findings) == 0


def test_vulnerable_pyyaml_cve_detected(scanner):
    added_lines = {
        ("requirements.txt", 5): "pyyaml==5.3.1",
    }
    findings = scanner.scan_diff_lines(added_lines)
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "CVE-2020-14343"
    assert f.severity == SeverityLevel.CRITICAL
    assert "pyyaml>=5.4" in f.suggested_code


def test_vulnerable_npm_lodash_detected(scanner):
    added_lines = {
        ("package.json", 18): '    "lodash": "^4.17.15",',
    }
    findings = scanner.scan_diff_lines(added_lines)
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "CVE-2021-23337"
    assert f.severity == SeverityLevel.CRITICAL
    assert '"^4.17.21"' in f.suggested_code


def test_wildcard_unpinned_dependency_flagged(scanner):
    added_lines = {
        ("package.json", 20): '    "express": "*",',
    }
    findings = scanner.scan_diff_lines(added_lines)
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "DEP_UNPINNED_WILDCARD"
    assert f.severity == SeverityLevel.HIGH
    assert f.suggested_code is not None


def test_insecure_http_url_detected(scanner):
    added_lines = {
        ("requirements.txt", 7): "my-internal-pkg @ http://insecure.internal.repo/pkg-1.0.tar.gz",
    }
    findings = scanner.scan_diff_lines(added_lines)
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "DEP_INSECURE_HTTP_URL"
    assert f.severity == SeverityLevel.HIGH
    assert "https://" in f.suggested_code


def test_non_manifest_files_ignored(scanner):
    added_lines = {
        ("app/main.py", 10): "requests==2.25.1",
    }
    findings = scanner.scan_diff_lines(added_lines)
    assert len(findings) == 0
