"""Registry and coordinator for deterministic rule engines."""

from __future__ import annotations

import logging
from typing import Optional

from app.github.diff_parser import ParsedDiff
from app.rules.dependency_scanner import DependencyScanner
from app.rules.secret_scanner import SecretScanner
from app.rules.terraform_risk import TerraformRiskAnalyzer
from app.schemas.review_finding import ReviewFinding

logger = logging.getLogger("pr_review_agent.rules.rule_registry")


class DeterministicRuleRegistry:
    """Coordinates deterministic security scanners before AI analysis."""

    def __init__(
        self,
        secret_scanner: Optional[SecretScanner] = None,
        terraform_analyzer: Optional[TerraformRiskAnalyzer] = None,
        dependency_scanner: Optional[DependencyScanner] = None,
    ):
        self.secret_scanner = secret_scanner or SecretScanner()
        self.terraform_analyzer = terraform_analyzer or TerraformRiskAnalyzer()
        self.dependency_scanner = dependency_scanner or DependencyScanner()

    def run_all_checks(self, parsed_diff: ParsedDiff) -> list[ReviewFinding]:
        """Execute all deterministic rules against parsed diff changes.

        Args:
            parsed_diff: Parsed diff containing valid changed lines and added line contents.

        Returns:
            List of ReviewFinding objects produced by deterministic rules.
        """
        findings: list[ReviewFinding] = []

        logger.info("Executing deterministic secret scanning...")
        secret_findings = self.secret_scanner.scan_diff_lines(parsed_diff.added_lines_content)
        findings.extend(secret_findings)

        logger.info("Executing deterministic Terraform risk analysis...")
        tf_findings = self.terraform_analyzer.scan_diff_lines(parsed_diff.added_lines_content)
        findings.extend(tf_findings)

        logger.info("Executing deterministic dependency & supply chain scanning...")
        dep_findings = self.dependency_scanner.scan_diff_lines(parsed_diff.added_lines_content)
        findings.extend(dep_findings)

        logger.info("Deterministic checks complete: %d findings discovered.", len(findings))
        return findings
