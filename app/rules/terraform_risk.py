"""Deterministic Terraform risk analyzer for detecting risky infrastructure patterns."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

from app.schemas.review_finding import ReviewFinding, ReviewCategory, SeverityLevel

logger = logging.getLogger("pr_review_agent.rules.terraform_risk")


@dataclass(frozen=True)
class TerraformRule:
    """Definition of a Terraform risk detection rule."""

    rule_id: str
    name: str
    pattern: re.Pattern
    severity: SeverityLevel
    confidence: float
    title: str
    suggestion: str
    suggested_code: Optional[str] = None


class TerraformRiskAnalyzer:
    """Analyzes Terraform (.tf, .tfvars) diff changes for risky infrastructure configurations."""

    RULES: list[TerraformRule] = [
        TerraformRule(
            rule_id="TF_OPEN_INGRESS_ALL",
            name="Open Ingress to 0.0.0.0/0",
            pattern=re.compile(
                r"""(?:cidr_blocks\s*=\s*\[[^\]]*"0\.0\.0\.0/0"[^\]]*\]|cidr_blocks\s*=\s*\[[^\]]*"::/0"[^\]]*\])""",
                re.IGNORECASE,
            ),
            severity=SeverityLevel.HIGH,
            confidence=0.90,
            title="Security Group allows unrestricted ingress from 0.0.0.0/0",
            suggestion="Restrict ingress traffic to specific authorized CIDR blocks or security group references instead of opening access to the entire Internet.",
            suggested_code='    cidr_blocks = ["10.0.0.0/16"]  # Restrict to internal VPC CIDR',
        ),
        TerraformRule(
            rule_id="TF_S3_PUBLIC_ACL",
            name="Public S3 Bucket ACL",
            pattern=re.compile(
                r"""acl\s*=\s*["'](?:public-read|public-read-write)["']""",
                re.IGNORECASE,
            ),
            severity=SeverityLevel.CRITICAL,
            confidence=0.95,
            title="S3 Bucket configured with public ACL",
            suggestion="Remove public ACLs ('public-read', 'public-read-write'). Use private ACLs and enforce AWS S3 Public Access Blocks.",
            suggested_code='  acl = "private"',
        ),
        TerraformRule(
            rule_id="TF_S3_PUBLIC_BLOCK_DISABLED",
            name="Disabled S3 Public Access Block",
            pattern=re.compile(
                r"""(?:block_public_acls|block_public_policy|ignore_public_acls|restrict_public_buckets)\s*=\s*false""",
                re.IGNORECASE,
            ),
            severity=SeverityLevel.HIGH,
            confidence=0.92,
            title="S3 Public Access Block disabled",
            suggestion="Enable all S3 Public Access Block controls by setting block_public_acls, block_public_policy, ignore_public_acls, and restrict_public_buckets to true.",
            suggested_code='  block_public_acls       = true\n  block_public_policy     = true\n  ignore_public_acls      = true\n  restrict_public_buckets = true',
        ),
        TerraformRule(
            rule_id="TF_DISABLED_ENCRYPTION",
            name="Disabled Storage/Volume Encryption",
            pattern=re.compile(
                r"""(?:encrypted\s*=\s*false|kms_key_id\s*=\s*""|storage_encrypted\s*=\s*false)""",
                re.IGNORECASE,
            ),
            severity=SeverityLevel.HIGH,
            confidence=0.90,
            title="Resource encryption explicitly disabled",
            suggestion="Enable encryption at rest (set encrypted = true) using AWS KMS or cloud-native encryption keys.",
            suggested_code='  encrypted = true',
        ),
        TerraformRule(
            rule_id="TF_IAM_WILDCARD_ACTION",
            name="Unrestricted IAM Wildcard Permissions",
            pattern=re.compile(
                r"""(?:actions\s*=\s*\[[^\]]*"\*"[^\]]*\]|"Action"\s*:\s*"\*")""",
                re.IGNORECASE,
            ),
            severity=SeverityLevel.HIGH,
            confidence=0.88,
            title="IAM policy grants unrestricted wildcard action ('*')",
            suggestion="Apply the principle of least privilege. Grant only specific API actions required by the workload instead of '*'.",
        ),
        TerraformRule(
            rule_id="TF_RDS_PUBLIC_ACCESS",
            name="Publicly Accessible Database",
            pattern=re.compile(
                r"""publicly_accessible\s*=\s*true""",
                re.IGNORECASE,
            ),
            severity=SeverityLevel.CRITICAL,
            confidence=0.95,
            title="Database instance configured with public accessibility",
            suggestion="Set publicly_accessible = false. Database instances should reside within private VPC subnets with no public IP address.",
            suggested_code='  publicly_accessible = false',
        ),
    ]

    def is_terraform_file(self, filename: str) -> bool:
        """Check if filename represents a Terraform configuration or variables file."""
        lower = filename.lower()
        return lower.endswith(".tf") or lower.endswith(".tfvars") or lower.endswith(".tf.json")

    def scan_diff_lines(self, added_lines: dict[tuple[str, int], str]) -> list[ReviewFinding]:
        """Scan added diff lines within Terraform files for potential risk patterns.

        Args:
            added_lines: Mapping of (filename, line_number) -> text_content.

        Returns:
            List of ReviewFinding objects.
        """
        findings: list[ReviewFinding] = []

        for (filename, line_num), content in added_lines.items():
            if not self.is_terraform_file(filename):
                continue

            for rule in self.RULES:
                if rule.pattern.search(content):
                    finding = ReviewFinding(
                        file=filename,
                        line=line_num,
                        severity=rule.severity,
                        category=ReviewCategory.INFRASTRUCTURE,
                        title=rule.title,
                        suggestion=rule.suggestion,
                        confidence=rule.confidence,
                        source=f"deterministic:terraform_risk:{rule.rule_id}",
                        rule_id=rule.rule_id,
                        suggested_code=rule.suggested_code,
                    )
                    findings.append(finding)

        logger.debug("TerraformRiskAnalyzer found %d risks in diff.", len(findings))
        return findings
