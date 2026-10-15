"""Changed-line validator ensuring comments only target modified lines in the PR diff."""

from __future__ import annotations

import logging
from typing import Tuple

from app.github.diff_parser import ParsedDiff
from app.schemas.review_finding import ReviewFinding

logger = logging.getLogger("pr_review_agent.guardrails.diff_line_validator")


class DiffLineValidator:
    """Enforces that inline comments are only attached to lines modified in the PR."""

    def validate_findings(
        self,
        findings: list[ReviewFinding],
        parsed_diff: ParsedDiff,
    ) -> tuple[list[ReviewFinding], list[ReviewFinding]]:
        """Filter findings to retain only those targeting actual changed lines.

        Args:
            findings: Candidate review findings from deterministic checks and AI.
            parsed_diff: Parsed unified diff containing valid line numbers.

        Returns:
            Tuple of (valid_findings, rejected_findings).
        """
        valid_findings: list[ReviewFinding] = []
        rejected_findings: list[ReviewFinding] = []

        for finding in findings:
            target_file = finding.file
            target_line = finding.line

            # Check if file was part of the PR changes
            if target_file not in parsed_diff.valid_changed_lines:
                logger.warning(
                    "Guardrail Violation: Finding targets file '%s' not present in PR changed files.",
                    target_file,
                )
                rejected_findings.append(finding)
                continue

            # Check if line was an actual addition or modification in the new file
            valid_lines = parsed_diff.valid_changed_lines[target_file]
            if target_line not in valid_lines:
                logger.warning(
                    "Guardrail Violation: Finding targets line %s:%d, which was not modified in this PR. "
                    "(Valid changed lines for this file: %s)",
                    target_file,
                    target_line,
                    sorted(list(valid_lines))[:10],
                )
                rejected_findings.append(finding)
                continue

            valid_findings.append(finding)

        logger.info(
            "Changed-line validation: %d valid, %d rejected.",
            len(valid_findings),
            len(rejected_findings),
        )
        return valid_findings, rejected_findings
