"""Unit tests for deterministic secret scanner and redaction mechanisms."""

import pytest
from app.rules.secret_scanner import SecretScanner, calculate_entropy
from app.schemas.review_finding import SeverityLevel, ReviewCategory


@pytest.fixture
def scanner():
    return SecretScanner()


def test_aws_access_key_detection(scanner):
    line = 'client = boto3.client("s3", aws_access_key_id="AKIA1234567890ABCDEF")'
    findings = scanner.scan_line("src/storage.py", 14, line)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.file == "src/storage.py"
    assert finding.line == 14
    assert finding.severity == SeverityLevel.CRITICAL
    assert finding.category == ReviewCategory.SECURITY
    assert finding.rule_id == "SEC_AWS_ACCESS_KEY"
    assert "AKIA1234567890ABCDEF" not in finding.title
    assert "AKIA1234567890ABCDEF" not in finding.suggestion


def test_github_token_detection(scanner):
    line = 'token = "ghp_111122223333444455556666777788889999"'
    findings = scanner.scan_line("src/ci.py", 22, line)
    assert len(findings) == 1
    assert findings[0].rule_id == "SEC_GITHUB_TOKEN"
    assert findings[0].severity == SeverityLevel.CRITICAL


def test_private_key_header_detection(scanner):
    line = "-----BEGIN RSA PRIVATE KEY-----"
    findings = scanner.scan_line("certs/server.pem", 1, line)
    assert len(findings) == 1
    assert findings[0].rule_id == "SEC_PRIVATE_KEY"


def test_hardcoded_password_detection(scanner):
    line = 'db_password = "K8#mQ9$zV2!wL5@x"'
    findings = scanner.scan_line("config.py", 10, line)
    assert len(findings) == 1
    assert findings[0].rule_id == "SEC_HARDCODED_PASSWORD"


def test_langsmith_key_detection(scanner):
    line = 'os.environ["LANGCHAIN_API_KEY"] = "lsv2_pt_a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8"'
    findings = scanner.scan_line("src/trace.py", 12, line)
    assert len(findings) == 1
    assert findings[0].rule_id == "SEC_LANGSMITH_KEY"
    assert findings[0].severity == SeverityLevel.CRITICAL
    assert "lsv2_pt_" not in findings[0].title
    assert "lsv2_pt_" not in findings[0].suggestion


def test_placeholder_passwords_are_ignored(scanner):
    placeholders = [
        'password = "replace_with_your_api_key"',
        'password = "CHANGEME_NOW"',
        'password = "dummy_password"',
        'password = "${DATABASE_PASSWORD}"',
        'password = "my_secret_token"',
    ]
    for line in placeholders:
        findings = scanner.scan_line("config.py", 5, line)
        assert len(findings) == 0, f"Failed for placeholder: {line}"


def test_low_entropy_strings_ignored_for_passwords(scanner):
    low_entropy_lines = [
        'password = "aaaaaaaaaaaa"',
        'password = "123412341234"',
    ]
    for line in low_entropy_lines:
        findings = scanner.scan_line("config.py", 8, line)
        assert len(findings) == 0, f"False positive on low entropy: {line}"


def test_redact_text_masks_all_credentials(scanner):
    raw_text = (
        'auth = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.e30.t-IDcSemACt8x4iTmc6UBD"\n'
        'key = "AKIA1111222233334444"\n'
        'gh_token = "ghp_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"\n'
        'ls_key = "lsv2_pt_11223344556677889900aabbccddeeff1122"\n'
    )
    redacted = scanner.redact_text(raw_text)

    assert "AKIA1111222233334444" not in redacted
    assert "ghp_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789" not in redacted
    assert "lsv2_pt_11223344556677889900aabbccddeeff1122" not in redacted
    assert "[REDACTED_SEC_AWS_ACCESS_KEY]" in redacted
    assert "[REDACTED_SEC_GITHUB_TOKEN]" in redacted
    assert "[REDACTED_SEC_LANGSMITH_KEY]" in redacted


def test_scan_diff_lines_mapping(scanner):
    diff_lines = {
        ("app/auth.py", 45): 'secret_key = "aB3!9kL#0pQ@8xZ1"',
        ("app/clean.py", 12): 'return x + y',
    }
    findings = scanner.scan_diff_lines(diff_lines)
    assert len(findings) == 1
    assert findings[0].file == "app/auth.py"
    assert findings[0].line == 45
