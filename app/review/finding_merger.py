"""Merger for combining deterministic and AI-generated review findings."""

from __future__ import annotations

import logging
from typing import Sequence

from app.schemas.review_finding import ReviewFinding

logger = logging.getLogger("pr_review_agent.review.finding_merger")


class FindingMerger:
    """Merges deterministic rule findings with validated AI findings."""

    def merge(
        self,
        deterministic_findings: Sequence[ReviewFinding],
        ai_findings: Sequence[ReviewFinding],
    ) -> list[ReviewFinding]:
        """Combine deterministic and AI findings into a unified candidate list.

        Args:
            deterministic_findings: Findings produced by deterministic regex/IaC engines.
            ai_findings: Findings produced by Gemini and validated through guardrails.

        Returns:
            Combined list of findings with preserved metadata.
        """
        merged: list[ReviewFinding] = []

        # Deterministic findings are added first
        for finding in deterministic_findings:
            merged.append(finding)

        # AI findings are added next
        for finding in ai_findings:
            merged.append(finding)

        logger.info(
            "Merged findings: %d deterministic + %d AI = %d total candidates.",
            len(deterministic_findings),
            len(ai_findings),
            len(merged),
        )
        return merged
