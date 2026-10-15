"""Unit tests for deterministic Terraform risk analyzer."""

import pytest
from app.rules.terraform_risk import TerraformRiskAnalyzer
from app.schemas.review_finding import SeverityLevel, ReviewCategory


@pytest.fixture
def analyzer():
    return TerraformRiskAnalyzer()


def test_open_ingress_cidr_detected(analyzer):
    lines = {
        ("infra/security.tf", 15): 'cidr_blocks = ["0.0.0.0/0"]',
    }
    findings = analyzer.scan_diff_lines(lines)
    assert len(findings) == 1
    assert findings[0].rule_id == "TF_OPEN_INGRESS_ALL"
    assert findings[0].severity == SeverityLevel.HIGH
    assert findings[0].category == ReviewCategory.INFRASTRUCTURE


def test_public_s3_acl_detected(analyzer):
    lines = {
        ("modules/storage/bucket.tf", 8): 'acl = "public-read"',
    }
    findings = analyzer.scan_diff_lines(lines)
    assert len(findings) == 1
    assert findings[0].rule_id == "TF_S3_PUBLIC_ACL"
    assert findings[0].severity == SeverityLevel.CRITICAL


def test_disabled_public_access_block(analyzer):
    lines = {
        ("infra/s3.tf", 24): "block_public_policy = false",
    }
    findings = analyzer.scan_diff_lines(lines)
    assert len(findings) == 1
    assert findings[0].rule_id == "TF_S3_PUBLIC_BLOCK_DISABLED"


def test_disabled_encryption_detected(analyzer):
    lines = {
        ("infra/ebs.tf", 42): "encrypted = false",
    }
    findings = analyzer.scan_diff_lines(lines)
    assert len(findings) == 1
    assert findings[0].rule_id == "TF_DISABLED_ENCRYPTION"


def test_iam_wildcard_detected(analyzer):
    lines = {
        ("infra/iam.tf", 30): 'actions = ["*"]',
    }
    findings = analyzer.scan_diff_lines(lines)
    assert len(findings) == 1
    assert findings[0].rule_id == "TF_IAM_WILDCARD_ACTION"


def test_public_rds_detected(analyzer):
    lines = {
        ("infra/db.tf", 19): "publicly_accessible = true",
    }
    findings = analyzer.scan_diff_lines(lines)
    assert len(findings) == 1
    assert findings[0].rule_id == "TF_RDS_PUBLIC_ACCESS"
    assert findings[0].severity == SeverityLevel.CRITICAL


def test_non_terraform_files_ignored(analyzer):
    # Same content in python or markdown file must not be flagged by Terraform analyzer
    lines = {
        ("docs/notes.md", 5): 'cidr_blocks = ["0.0.0.0/0"]',
        ("script.py", 10): 'acl = "public-read"',
    }
    findings = analyzer.scan_diff_lines(lines)
    assert len(findings) == 0


def test_safe_terraform_not_flagged(analyzer):
    lines = {
        ("infra/network.tf", 12): 'cidr_blocks = ["10.0.0.0/16"]',
        ("infra/storage.tf", 18): 'acl = "private"',
        ("infra/storage.tf", 19): "block_public_acls = true",
        ("infra/db.tf", 22): "publicly_accessible = false",
    }
    findings = analyzer.scan_diff_lines(lines)
    assert len(findings) == 0
